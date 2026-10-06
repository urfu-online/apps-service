#!/usr/bin/env bash
# =============================================================================
# diagnose-client.sh — клиентская диагностика сервиса платформы
# apps-service-opus. Запускается НА КЛИЕНТСКОЙ МАШИНЕ (рабочий компьютер).
#
# ТОЛЬКО ЧТЕНИЕ: скрипт ничего не изменяет — только DNS/TCP/TLS/HTTP-пробы.
#
# ВАЖНО ПРО ПРОКСИ: если заданы http_proxy/https_proxy/all_proxy, curl ходит
# через локальный прокси и может врать про недоступность сервиса. Все HTTP-пробы
# выполняются в обход прокси (--noproxy '*'); openssl прокси не использует.
#
# ЗАПУСК:
#   SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
#   REFERENCE_DOMAIN=course-archive-explorer.apps.urfu.online \
#     bash diagnose-client.sh
#
# Минимум: SERVICE_DOMAIN. REFERENCE_DOMAIN — домен заведомо работающего сервиса.
# Требуется: bash, curl, openssl (getent/dig/nslookup — опционально).
# ============================================================================
set -u -o pipefail

# ------------------ Сервисозависимые переменные -----------------------------
SERVICE_DOMAIN="${SERVICE_DOMAIN:-}"
REFERENCE_DOMAIN="${REFERENCE_DOMAIN:-}"
SKIP_TCP_CHECK="${SKIP_TCP_CHECK:-0}"     # 1 — пропустить /dev/tcp (нестандартные оболочки)

# ------------------ Оформление и счётчики -----------------------------------
PASS=0; FAIL=0; WARN=0; STEP=0
if [ -t 1 ]; then
  R=$'\e[31m'; G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; D=$'\e[2m'; B=$'\e[1m'; N=$'\e[0m'
else
  R=""; G=""; Y=""; C=""; D=""; B=""; N=""
fi
section() { printf '\n%s\n' "${B}${C}━━━━ $* ━━━━${N}"; }
step()    { STEP=$((STEP+1)); printf '\n%s\n' "${B}${C}[$STEP] $*${N}"; }
ok()      { PASS=$((PASS+1)); printf '  %s✔ OK%s  %s\n'   "$G" "$N" "$*"; }
fail()    { FAIL=$((FAIL+1)); printf '  %s✘ FAIL%s %s\n' "$R" "$N" "$*"; }
warn()    { WARN=$((WARN+1)); printf '  %s⚠ WARN%s %s\n' "$Y" "$N" "$*"; }
info()    { printf '  %sℹ %s%s\n' "$D" "$*" "$N"; }
hint()    { printf '  %s→ %s%s\n' "$Y" "$*" "$N"; }
cmdout()  { printf '%s\n' "$1" | sed 's/^/    | /'; }

# ------------------ Вспомогательные функции ---------------------------------

# Разрешить имя в IPv4: getent → dig → nslookup
resolve_host() {
  local host="$1" ip=""
  if command -v getent >/dev/null 2>&1; then
    ip=$(getent ahostsv4 "$host" 2>/dev/null | awk '{print $1; exit}')
  fi
  if [ -z "$ip" ] && command -v dig >/dev/null 2>&1; then
    ip=$(dig +short A "$host" 2>/dev/null | grep -E '^[0-9.]+$' | tail -n1)
  fi
  if [ -z "$ip" ] && command -v nslookup >/dev/null 2>&1; then
    ip=$(nslookup "$host" 2>/dev/null | awk '/^Address [0-9]*:/ {print $3}' | grep -E '^[0-9.]+$' | tail -n1)
  fi
  printf '%s' "$ip"
}

# curl в обход прокси
hc() { curl --noproxy '*' "$@"; }

# Флаги для вердикта
DNS_IP=""; TCP443=0; TLS_OK=0; HTTP_CODE=""; REF_CODE=""

# =============================================================================
section "ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА"

if [ -z "$SERVICE_DOMAIN" ]; then
  echo "ОШИБКА: не задан SERVICE_DOMAIN."
  echo "Пример: SERVICE_DOMAIN=urfu-forms.apps.urfu.online bash $0"
  exit 2
fi

info "Параметры диагностики:"
info "  SERVICE_DOMAIN   = $SERVICE_DOMAIN"
info "  REFERENCE_DOMAIN = ${REFERENCE_DOMAIN:-<не задан>}"

step "Прокси-переменные окружения"
PROXY_LIST=""
for v in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY; do
  [ -n "${!v:-}" ] && PROXY_LIST="$PROXY_LIST $v=${!v}"
done
if [ -n "$PROXY_LIST" ]; then
  warn "обнаружен прокси:$PROXY_LIST"
  info "все HTTP-пробы ниже выполняются В ОБХОД прокси (--noproxy '*'); openssl всегда идёт напрямую"
  hint "Браузер при этом может продолжать ходить через прокси — учтите это при сравнении результатов."
else
  ok "прокси-переменные не заданы"
fi

command -v curl >/dev/null 2>&1 && ok "curl доступен" || fail "curl не найден"
command -v openssl >/dev/null 2>&1 && ok "openssl доступен" || warn "openssl не найден — TLS-проверка будет пропущена"

# =============================================================================
section "КЛИЕНТСКИЕ ПРОВЕРКИ"

# --- Б1: DNS ------------------------------------------------------------------
step "DNS: разрешение $SERVICE_DOMAIN"
DNS_IP=$(resolve_host "$SERVICE_DOMAIN")
if [ -n "$DNS_IP" ]; then
  ok "$SERVICE_DOMAIN → $DNS_IP"
else
  fail "домен $SERVICE_DOMAIN не разрешается (NXDOMAIN или нет записи)"
  hint "Добавьте A-запись на IP сервера платформы (или wildcard *.apps.urfu.online)."
fi
if [ -n "$REFERENCE_DOMAIN" ]; then
  REF_IP=$(resolve_host "$REFERENCE_DOMAIN")
  if [ -n "$REF_IP" ]; then
    ok "эталон $REFERENCE_DOMAIN → $REF_IP"
    if [ -n "$DNS_IP" ] && [ "$DNS_IP" != "$REF_IP" ]; then
      info "IP различаются — это может быть нормой (LB/GeoDNS); сверьте, что $DNS_IP — адрес сервера платформы"
    fi
  else
    warn "эталон $REFERENCE_DOMAIN тоже не разрешается — проблема с DNS у клиента в целом"
  fi
fi

# --- Б2: TCP -------------------------------------------------------------------
if [ "$SKIP_TCP_CHECK" != "1" ]; then
  step "TCP-доступность порта 443"
  if timeout 5 bash -c "exec 3<>/dev/tcp/$SERVICE_DOMAIN/443" 2>/dev/null; then
    TCP443=1
    ok "порт 443 открыт"
  else
    fail "порт 443 недоступен (firewall / внешний LB / нет маршрута)"
    hint "Если DNS ок, но 443 закрыт — проверьте firewall сервера и внешний балансировщик."
  fi
  step "TCP-доступность порта 80 (информационно)"
  if timeout 5 bash -c "exec 3<>/dev/tcp/$SERVICE_DOMAIN/80" 2>/dev/null; then
    info "порт 80 открыт (Caddy отвечает и по http, обычно с редиректом на https)"
  else
    info "порт 80 закрыт — часто ожидаемо: для localhost-сайтов Caddy не открывает :80 вообще"
    hint "Всегда заходить по https:// ; по http:// возможен connection refused."
  fi
fi

# --- Б3: TLS ---------------------------------------------------------------------
step "TLS-рукопожатие и сертификат $SERVICE_DOMAIN"
if command -v openssl >/dev/null 2>&1; then
  CERT_INFO=$(echo | openssl s_client -connect "$SERVICE_DOMAIN:443" -servername "$SERVICE_DOMAIN" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates 2>/dev/null || true)
  if [ -n "$CERT_INFO" ]; then
    TLS_OK=1
    ok "TLS handshake успешен, сертификат получен:"
    cmdout "$CERT_INFO"
  else
    fail "TLS handshake не удался — сертификат не выдан или соединение разорвано"
    hint "Проблема на сервере: запускайте diagnose-server.sh (проверки 6–8: master validate, сертификат, логи ACME)."
  fi
  VERIFY=$(echo | openssl s_client -connect "$SERVICE_DOMAIN:443" -servername "$SERVICE_DOMAIN" 2>/dev/null \
    | grep -m1 'Verify return code' || true)
  [ -n "$VERIFY" ] && info "$VERIFY"
fi

# --- Б4: HTTPS без прокси ------------------------------------------------------------
step "HTTP-запрос https://$SERVICE_DOMAIN (без прокси)"
if command -v curl >/dev/null 2>&1; then
  HTTP_CODE=$(hc -s -o /dev/null -w '%{http_code}' --connect-timeout 5 -m 25 "https://$SERVICE_DOMAIN/" 2>/dev/null || true)
  case "$HTTP_CODE" in
    000)
      fail "соединения нет (HTTP 000): сеть/firewall или TLS-ошибка (см. проверки выше)" ;;
    200|201|204|301|302|303|307|308)
      ok "сервис доступен: HTTP $HTTP_CODE"
      hint "Если браузер всё равно не открывает — проблема в браузере: кэш, HSTS, расширения, прокси браузера (см. итоги)." ;;
    403)
      BODY=$(hc -s -m 10 "https://$SERVICE_DOMAIN/" 2>/dev/null | head -c 200)
      if printf '%s' "$BODY" | grep -qi 'access denied'; then
        fail "403 Access Denied от Caddy: сервис internal ЛИБО master отклонил TLS-validate"
        hint "Проверьте visibility в service.yml и /api/tls/validate на сервере (diagnose-server.sh, проверка 6)."
      else
        warn "403 от самого приложения: $(printf '%s' "$BODY")"
      fi ;;
    404)
      warn "404 — Caddy работает, приложение отвечает 404 (маршрут приложения)" ;;
    502|504)
      fail "HTTP $HTTP_CODE — Caddy не достучался до контейнера сервиса"
      hint "Запустите diagnose-server.sh (проверка 5: upstream из сети Caddy)." ;;
    5??)
      fail "HTTP $HTTP_CODE — ошибка приложения"
      hint "Смотрите логи контейнеров сервиса: docker compose logs." ;;
    4??)
      warn "HTTP $HTTP_CODE — ответ приложения (Caddy работает)" ;;
    *)
      warn "неожиданный код: $HTTP_CODE" ;;
  esac
  # Заголовки ответа для анализа
  HDRS=$(hc -s -D - -o /dev/null -m 15 "https://$SERVICE_DOMAIN/" 2>/dev/null | head -n 12 || true)
  [ -n "$HDRS" ] && cmdout "$HDRS"
fi

# --- Б5: эталонное сравнение ------------------------------------------------------------
if [ -n "$REFERENCE_DOMAIN" ] && command -v curl >/dev/null 2>&1; then
  step "Эталонное сравнение: $REFERENCE_DOMAIN"
  REF_CODE=$(hc -s -o /dev/null -w '%{http_code}' --connect-timeout 5 -m 15 "https://$REFERENCE_DOMAIN/" 2>/dev/null || true)
  if [ "$REF_CODE" != "000" ] && [ -n "$REF_CODE" ]; then
    ok "эталон отвечает: HTTP $REF_CODE"
    if [ "$HTTP_CODE" = "000" ]; then
      fail "эталон работает, а $SERVICE_DOMAIN нет — проблема специфична для нового домена (DNS/LB)"
    fi
  else
    warn "эталон тоже недоступен — проблема в клиентской сети/прокси, а не в сервисе"
    hint "Проверьте доступность сервера из другой сети (мобильный интернет) или через VPN в обход прокси."
  fi
fi

# =============================================================================
section "ИТОГИ"
printf '  OK: %s   FAIL: %s   WARN: %s\n' "$PASS" "$FAIL" "$WARN"
echo
echo "Вердикт:"
if [ -z "$DNS_IP" ]; then
  echo "  ✘ DNS не разрешает домен → добавить A-запись на сервер платформы."
elif [ "$TCP443" -eq 0 ] && [ "$SKIP_TCP_CHECK" != "1" ]; then
  echo "  ✘ Порт 443 недоступен → firewall/внешний LB."
elif [ "$TLS_OK" -eq 0 ]; then
  echo "  ✘ TLS не поднимается → на сервере не выпущен сертификат или master отклонил домен."
  echo "    → Запустите diagnose-server.sh на сервере (проверки 6–8)."
elif [ "$HTTP_CODE" = "000" ]; then
  echo "  ✘ HTTPS-запрос не проходит при живом TLS → клиентская сеть/прокси."
elif [ "$HTTP_CODE" = "502" ] || [ "$HTTP_CODE" = "504" ]; then
  echo "  ✘ Caddy не достучался до контейнера → diagnose-server.sh, проверка 5."
elif [ "$HTTP_CODE" = "403" ]; then
  echo "  ✘ 403 от Caddy → visibility=internal или отказ TLS-validate → diagnose-server.sh, проверка 6."
elif [ "${HTTP_CODE#2}" != "$HTTP_CODE" ] || [ "${HTTP_CODE#3}" != "$HTTP_CODE" ]; then
  echo "  ✔ Сервис доступен извне (HTTP $HTTP_CODE). Если браузер не открывает:"
  echo "    приватное окно, очистка кэша, chrome://net-internals/#hsts (Delete domain security"
  echo "    policies для домена), отключить прокси/расширения браузера для *.urfu.online."
  if [ -n "$REF_CODE" ] && [ "$REF_CODE" = "000" ]; then
    echo "    ⚠ Эталон с этой машины тоже недоступен — сначала проверьте клиентскую сеть/прокси."
  fi
else
  echo "  ℹ Приложение отвечает HTTP $HTTP_CODE — Caddy работает, разбирайтесь с приложением."
fi
# Код выхода: 0 — без FAIL (WARN допустимы), 1 — есть FAIL.
[ "$FAIL" -gt 0 ] && exit 1
exit 0
