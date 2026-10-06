#!/usr/bin/env bash
# =============================================================================
# diagnose-server.sh — серверная диагностика сервиса платформы apps-service-opus
#
# ТОЛЬКО ЧТЕНИЕ: скрипт не изменяет файлы, конфиги, контейнеры и сети.
# Выполняются команды чтения: docker ps/inspect/logs/network inspect, ls/find,
# grep и HTTP GET-пробы (curl/wget).
#
# ЗАПУСК (минимум — SERVICE_NAME и/или SERVICE_DOMAIN):
#   SERVICE_NAME=urfu-forms SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
#     bash diagnose-server.sh
#
# Полный набор (если автоопределение не сработает):
#   SERVICE_NAME=urfu-forms \
#   SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
#   CONTAINER_NAME=urfu_forms_frontend \
#   INTERNAL_PORT=80 \
#   SERVICES_ROOT=/apps/services \
#     bash diagnose-server.sh
#
# Требуется: bash, docker (доступ к docker.sock), curl, openssl.
# ============================================================================
set -u -o pipefail

# ------------------ Сервисозависимые переменные (env переопределяют) --------
SERVICE_NAME="${SERVICE_NAME:-}"
SERVICE_DOMAIN="${SERVICE_DOMAIN:-}"
# Базовый домен: по умолчанию берём PLATFORM_DOMAIN из /apps/.env платформы
BASE_DOMAIN="${BASE_DOMAIN:-}"
if [ -z "$BASE_DOMAIN" ] && [ -f /apps/.env ]; then
  BASE_DOMAIN=$(grep '^PLATFORM_DOMAIN=' /apps/.env | tail -1 | cut -d= -f2- | tr -d ' "')
fi
BASE_DOMAIN="${BASE_DOMAIN:-apps.urfu.online}"
CONTAINER_NAME="${CONTAINER_NAME:-}"
INTERNAL_PORT="${INTERNAL_PORT:-}"
SERVICES_ROOT="${SERVICES_ROOT:-/apps/services}"
SERVICE_DIR="${SERVICE_DIR:-}"

# ------------------ Платформенные константы ---------------------------------
CADDY_CONTAINER="${CADDY_CONTAINER:-caddy}"
MASTER_CONTAINER="${MASTER_CONTAINER:-platform-master}"
PLATFORM_NETWORK="${PLATFORM_NETWORK:-platform_network}"
MASTER_API_URL="${MASTER_API_URL:-http://localhost:8001}"
CADDY_ADMIN_URL="${CADDY_ADMIN_URL:-http://localhost:2019}"
LOG_SINCE="${LOG_SINCE:-24h}"

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

# Конфиг Caddy (admin API): с хоста или через docker exec. Печатает JSON в stdout.
caddy_admin_get() {
  local out=""
  if command -v curl >/dev/null 2>&1; then
    out=$(curl -s -m 5 "$CADDY_ADMIN_URL/config/" 2>/dev/null || true)
    [ -n "$out" ] && { printf '%s' "$out"; return 0; }
  fi
  out=$(docker exec "$CADDY_CONTAINER" sh -c "wget -qO- -T 5 http://127.0.0.1:2019/config/" 2>/dev/null || true)
  [ -n "$out" ] && { printf '%s' "$out"; return 0; }
  return 1
}

# Запрос к master API: с хоста, затем изнутри контейнера master (curl/python3).
# Результат: M_CODE, M_BODY. 0 — получили ответ.
M_CODE=""; M_BODY=""
master_api() {
  local path="$1" out=""
  M_CODE=""; M_BODY=""
  if command -v curl >/dev/null 2>&1; then
    out=$(curl -s -m 5 -w $'\n%{http_code}' "$MASTER_API_URL$path" 2>/dev/null || true)
    if [ -n "$out" ] && [ "${out##*$'\n'}" != "$out" ]; then
      M_CODE="${out##*$'\n'}"; M_BODY="${out%$'\n'*}"; return 0
    fi
  fi
  if docker exec "$MASTER_CONTAINER" sh -c 'command -v curl' >/dev/null 2>&1; then
    out=$(docker exec "$MASTER_CONTAINER" curl -s -m 5 -w $'\n%{http_code}' "http://localhost:8000$path" 2>/dev/null || true)
    if [ -n "$out" ] && [ "${out##*$'\n'}" != "$out" ]; then
      M_CODE="${out##*$'\n'}"; M_BODY="${out%$'\n'*}"; return 0
    fi
  fi
  if docker exec "$MASTER_CONTAINER" sh -c 'command -v python3' >/dev/null 2>&1; then
    out=$(docker exec "$MASTER_CONTAINER" python3 - "$path" <<'PY' 2>/dev/null || true
import sys, http.client
c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
c.request("GET", sys.argv[1])
r = c.getresponse()
print(r.status)
print(r.read().decode(errors="replace"))
PY
)
    if [ -n "$out" ]; then
      M_CODE=$(printf '%s' "$out" | head -n1)
      M_BODY=$(printf '%s' "$out" | tail -n +2)
      return 0
    fi
  fi
  return 1
}

# Флаги для итогового вердикта
FLAG_ROUTE=0; FLAG_DIAL=0; FLAG_UPSTREAM=0; FLAG_VALIDATE=0; FLAG_CERT=0; FLAG_LOCAL=0

# =============================================================================
section "ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА"

# Автоопределение переменных
[ -z "$SERVICE_DOMAIN" ] && [ -n "$SERVICE_NAME" ] && SERVICE_DOMAIN="${SERVICE_NAME}.${BASE_DOMAIN}"
if [ -z "$SERVICE_NAME" ] && [ -n "$SERVICE_DOMAIN" ]; then
  SERVICE_NAME="${SERVICE_DOMAIN%%.*}"
fi
if [ -z "$SERVICE_DOMAIN" ]; then
  echo "ОШИБКА: не задан SERVICE_DOMAIN (или SERVICE_NAME + BASE_DOMAIN)."
  echo "Пример: SERVICE_DOMAIN=urfu-forms.apps.urfu.online bash $0"
  exit 2
fi
if [ -z "$SERVICE_DIR" ]; then
  for d in "$SERVICES_ROOT/public/$SERVICE_NAME" "$SERVICES_ROOT/internal/$SERVICE_NAME"; do
    if [ -d "$d" ]; then SERVICE_DIR="$d"; break; fi
  done
fi
if [ -z "$CONTAINER_NAME" ] && [ -n "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/service.yml" ]; then
  CONTAINER_NAME=$(grep -m1 'container_name:' "$SERVICE_DIR/service.yml" 2>/dev/null \
    | sed 's/.*container_name:[[:space:]]*//' | tr -d "\"'" | xargs || true)
fi
if [ -z "$INTERNAL_PORT" ] && [ -n "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/service.yml" ]; then
  INTERNAL_PORT=$(grep -m1 'internal_port:' "$SERVICE_DIR/service.yml" 2>/dev/null \
    | sed 's/.*internal_port:[[:space:]]*//' | tr -dc '0-9' || true)
fi

info "Параметры диагностики:"
info "  SERVICE_NAME    = ${SERVICE_NAME:-<не задан>}"
info "  SERVICE_DOMAIN  = $SERVICE_DOMAIN"
info "  BASE_DOMAIN     = $BASE_DOMAIN"
info "  CONTAINER_NAME  = ${CONTAINER_NAME:-<не определён>}"
info "  INTERNAL_PORT   = ${INTERNAL_PORT:-<не определён>}"
info "  SERVICE_DIR     = ${SERVICE_DIR:-<не найден>}"
hint "Проверьте значения выше; при ошибке переопределите через переменные окружения."

step "Доступность Docker и инструментов"
if command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; then
  ok "docker доступен"
else
  fail "docker недоступен (нет прав на docker.sock или docker не установлен)"
  hint "Запустите от пользователя с правами на docker или через sudo."
fi
command -v curl >/dev/null 2>&1 && ok "curl доступен" || warn "curl не найден — часть проверок будет пропущена"
command -v openssl >/dev/null 2>&1 && ok "openssl доступен" || warn "openssl не найден — TLS-проверки будут пропущены"

# =============================================================================
section "СЕРВЕРНЫЕ ПРОВЕРКИ"

# --- А1: манифест ------------------------------------------------------------
step "Манифест service.yml"
if [ -n "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/service.yml" ]; then
  ok "манифест найден: $SERVICE_DIR/service.yml"
  VIS=$(grep -m1 'visibility:' "$SERVICE_DIR/service.yml" | sed 's/.*visibility:[[:space:]]*//' | tr -d '"' || true)
  RTYPE=$(grep -m1 'type:' "$SERVICE_DIR/service.yml" | sed 's/.*type:[[:space:]]*//' | tr -d '"' || true)
  info "visibility=$VIS, routing type=$RTYPE"
  if grep -q 'container_name:' "$SERVICE_DIR/service.yml"; then
    ok "в routing указан container_name: $CONTAINER_NAME"
  else
    fail "в routing НЕТ container_name — Caddy будет проксировать на host.docker.internal (legacy, сломано)"
    hint "Добавьте container_name в routing[] манифеста."
  fi
  [ "$VIS" = "internal" ] && hint "visibility=internal: доступ только из приватных подсетей; снаружи Caddy отдаёт 403 Access Denied."
else
  warn "манифест не найден (SERVICE_DIR=$SERVICE_DIR)"
  hint "Проверьте, что сервис лежит в $SERVICES_ROOT/{public,internal}/$SERVICE_NAME/ и содержит service.yml."
fi

# --- А2: контейнеры ----------------------------------------------------------
step "Контейнеры сервиса (docker compose ps)"
if [ -n "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/docker-compose.yml" ]; then
  PS_OUT=$(docker compose --project-directory "$SERVICE_DIR" ps 2>/dev/null || true)
  if [ -n "$PS_OUT" ]; then cmdout "$PS_OUT"; else warn "docker compose ps не дал вывода"; fi
else
  warn "docker-compose.yml не найден в $SERVICE_DIR"
fi
if [ -n "$CONTAINER_NAME" ]; then
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    ST=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME")
    [ "$ST" = "running" ] && ok "контейнер $CONTAINER_NAME: $ST" \
      || fail "контейнер $CONTAINER_NAME: $ST (ожидалось running)"
  else
    fail "контейнер $CONTAINER_NAME не найден"
    hint "Проверьте container_name в docker-compose.yml и в service.yml — они должны совпадать."
  fi
else
  warn "CONTAINER_NAME не определён — проверка статуса контейнера пропущена"
fi

# --- А3: docker-сеть ---------------------------------------------------------
step "Подключение к сети $PLATFORM_NETWORK"
if [ -n "$CONTAINER_NAME" ] && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  NETS=$(docker inspect -f '{{range $k,$_ := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CONTAINER_NAME" 2>/dev/null || true)
  info "сети контейнера: $NETS"
  case " $NETS " in
    *" $PLATFORM_NETWORK "*) ok "контейнер в сети $PLATFORM_NETWORK" ;;
    *) fail "контейнер НЕ в сети $PLATFORM_NETWORK — Caddy не сможет достучаться (502)"
       hint "Добавьте в docker-compose.yml: networks: [platform] + networks: { platform: { external: true, name: platform_network } }" ;;
  esac
fi
if docker inspect "$CADDY_CONTAINER" >/dev/null 2>&1; then
  CNETS=$(docker inspect -f '{{range $k,$_ := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CADDY_CONTAINER" 2>/dev/null || true)
  case " $CNETS " in
    *" $PLATFORM_NETWORK "*) ok "Caddy в сети $PLATFORM_NETWORK" ;;
    *) fail "Caddy НЕ в сети $PLATFORM_NETWORK" ;;
  esac
else
  fail "контейнер Caddy ($CADDY_CONTAINER) не найден"
fi

# --- А4: маршрут в Caddy ------------------------------------------------------
step "Маршрут $SERVICE_DOMAIN загружен в Caddy"
CADDY_CFG=$(caddy_admin_get || true)
if [ -z "$CADDY_CFG" ]; then
  fail "не удалось получить конфиг Caddy (admin API $CADDY_ADMIN_URL)"
  hint "Проверьте, что порт 2019 проброшен на хост (127.0.0.1:2019)."
else
  if printf '%s' "$CADDY_CFG" | grep -q "$SERVICE_DOMAIN"; then
    FLAG_ROUTE=1
    ok "домен $SERVICE_DOMAIN присутствует в конфиге Caddy"
  else
    fail "домена $SERVICE_DOMAIN нет в конфиге Caddy"
    hint "Master не перегенерировал конфиг: проверьте discovery (docker logs $MASTER_CONTAINER | grep -i $SERVICE_NAME), валидность service.yml."
  fi
  if [ -n "$CONTAINER_NAME" ] && [ -n "$INTERNAL_PORT" ]; then
    DIAL="$CONTAINER_NAME:$INTERNAL_PORT"
    if printf '%s' "$CADDY_CFG" | grep -q "\"dial\":\"$DIAL\""; then
      FLAG_DIAL=1
      ok "upstream в конфиге: dial $DIAL"
    else
      warn "не найден dial $DIAL — проверьте container_name/internal_port в service.yml и перегенерируйте конфиг"
    fi
  fi
fi

# --- А5: upstream изнутри сети Caddy ------------------------------------------
step "Доступность upstream из контейнера Caddy"
if [ -n "$CONTAINER_NAME" ] && [ -n "$INTERNAL_PORT" ] \
   && docker inspect "$CADDY_CONTAINER" >/dev/null 2>&1 \
   && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  RAW=$(docker exec "$CADDY_CONTAINER" sh -c "wget -S -T 5 -O /dev/null 'http://$CONTAINER_NAME:$INTERNAL_PORT/'" 2>&1 || true)
  CODE_LINE=$(printf '%s' "$RAW" | grep -m1 -o 'HTTP/[0-9.]* [0-9]*' || true)
  if [ -n "$CODE_LINE" ]; then
    case "$CODE_LINE" in
      *" 200"*|*" 204"*|*" 301"*|*" 302"*|*" 303"*|*" 307"*|*" 308"*)
        FLAG_UPSTREAM=1; ok "upstream отвечает: $CODE_LINE" ;;
      *)
        FLAG_UPSTREAM=1; warn "upstream ответил $CODE_LINE — это ответ самого приложения" ;;
    esac
  else
    case "$RAW" in
      *"bad address"*)
        fail "Caddy не резолвит имя $CONTAINER_NAME — контейнера нет в общей сети (см. проверку 3)" ;;
      *"Connection refused"*)
        fail "connection refused — приложение не слушает порт $INTERNAL_PORT внутри контейнера"
        hint "Проверьте, на каком порту реально работает приложение, и internal_port в service.yml." ;;
      *"timed out"*)
        fail "таймаут при подключении к upstream" ;;
      *)
        fail "upstream не отвечает: $(printf '%s' "$RAW" | tail -n1)" ;;
    esac
  fi
else
  warn "проверка пропущена (нет CONTAINER_NAME/INTERNAL_PORT или контейнера)"
fi

# --- А6: master — разрешение on-demand TLS -------------------------------------
step "Master API: /api/tls/validate для $SERVICE_DOMAIN"
if master_api "/api/tls/validate?domain=$SERVICE_DOMAIN"; then
  case "$M_CODE" in
    200) FLAG_VALIDATE=1; ok "master разрешает выпуск сертификата (HTTP 200): $(printf '%s' "$M_BODY" | head -c 120)" ;;
    403) fail "master ОТКЛОНЯЕТ домен (HTTP 403) — Caddy не сможет выпустить сертификат"
         hint "Проверьте: сервис обнаружен master'ом? service.yml валиден? Рестарт master: docker restart $MASTER_CONTAINER" ;;
    *)   warn "неожиданный ответ master: HTTP $M_CODE — $(printf '%s' "$M_BODY" | head -c 120)" ;;
  esac
else
  warn "master API недоступен (host: $MASTER_API_URL, и изнутри контейнера $MASTER_CONTAINER)"
  hint "Проверьте, что master запущен и порт 8001 проброшен на хост."
fi
if master_api "/api/tls/allowed"; then
  if printf '%s' "$M_BODY" | grep -q "$SERVICE_DOMAIN"; then
    ok "домен присутствует в /api/tls/allowed"
  else
    warn "домена нет в /api/tls/allowed — master не видит сервис"
  fi
fi

# --- А7: сертификат в хранилище Caddy -------------------------------------------
step "Сертификат для $SERVICE_DOMAIN в хранилище Caddy"
if docker inspect "$CADDY_CONTAINER" >/dev/null 2>&1; then
  CERT_PATH=$(docker exec "$CADDY_CONTAINER" sh -c "find /data/caddy/certificates -maxdepth 2 -name '$SERVICE_DOMAIN' 2>/dev/null" 2>/dev/null | head -n1 || true)
  if [ -n "$CERT_PATH" ]; then
    FLAG_CERT=1
    ok "сертификат выдан: $CERT_PATH"
  else
    warn "сертификат не найден — будет выпущен при первом HTTPS-запросе (займёт несколько секунд)"
    hint "Если HTTPS-запросы уже были, а сертификата нет — смотрите ошибки ACME в логах (проверка 8)."
  fi
fi

# --- А8: логи Caddy ---------------------------------------------------------------
step "Логи Caddy за $LOG_SINCE (фильтр: домен, TLS, ошибки)"
LOGS=$(docker logs "$CADDY_CONTAINER" --since "$LOG_SINCE" 2>&1 | grep -iE "$SERVICE_DOMAIN|on_demand|acme|certificate|error" | tail -n 30 || true)
if [ -n "$LOGS" ]; then
  cmdout "$LOGS"
  if printf '%s' "$LOGS" | grep -qi 'permission denied\|not authorized'; then
    fail "в логах отказ on-demand permission — см. проверку 6 (master /api/tls/validate)"
  elif printf '%s' "$LOGS" | grep -qi 'acme.*error\|certificate.*error'; then
    fail "в логах ошибки ACME/сертификатов"
  else
    info "критичных записей по фильтру не видно (оцените вывод самостоятельно)"
  fi
else
  info "подозрительных записей в логах не найдено"
fi

# --- А9: локальный HTTPS через Caddy (в обход DNS) ---------------------------------
step "Локальный HTTPS-тест: Caddy → upstream (в обход DNS и прокси)"
if command -v curl >/dev/null 2>&1; then
  CODE=$(curl -sk --noproxy '*' --resolve "$SERVICE_DOMAIN:443:127.0.0.1" \
    -o /dev/null -w '%{http_code}' -m 25 "https://$SERVICE_DOMAIN/" 2>/dev/null || true)
  case "$CODE" in
    000) fail "TLS handshake не проходит даже локально — см. проверки 6, 7, 8" ;;
    502|504) fail "Caddy вернул $CODE — upstream недоступен (см. проверку 5)" ;;
    "") fail "пустой ответ — проверьте curl/сеть на хосте" ;;
    *)
      FLAG_LOCAL=1
      ok "серверная цепочка Caddy→upstream работает через HTTPS (HTTP $CODE)"
      info "2xx/3xx = успех; 4xx/5xx = ответ самого приложения (проблема в приложении, не в платформе)"
      hint "Если здесь всё OK, а в браузере нет — проблема снаружи: DNS или клиентская сеть/прокси. Запустите diagnose-client.sh." ;;
  esac
fi

# --- А10: CORS и redirect URI --------------------------------------------------------
step "CORS_ORIGINS / REDIRECT_URI на боевой домен"
if [ -n "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/docker-compose.yml" ]; then
  CORS_LINE=$(grep -i 'CORS_ORIGINS' "$SERVICE_DIR/docker-compose.yml" | head -n1 || true)
  if [ -n "$CORS_LINE" ]; then
    if printf '%s' "$CORS_LINE" | grep -q "$SERVICE_DOMAIN"; then
      ok "CORS_ORIGINS содержит $SERVICE_DOMAIN"
    else
      warn "CORS_ORIGINS не содержит https://$SERVICE_DOMAIN — сайт откроется, но API-запросы из браузера будут блокированы CORS"
      info "текущее значение: $CORS_LINE"
    fi
  else
    info "CORS_ORIGINS в docker-compose.yml не задан (приложение может работать без CORS)"
  fi
  if grep -qi 'REDIRECT_URI' "$SERVICE_DIR/docker-compose.yml"; then
    R_LINE=$(grep -i 'REDIRECT_URI' "$SERVICE_DIR/docker-compose.yml" | head -n1 || true)
    if printf '%s' "$R_LINE" | grep -q 'localhost'; then
      warn "REDIRECT_URI указывает на localhost — авторизация через Keycloak на боевом домене не сработает"
      info "текущее значение: $R_LINE"
    else
      ok "REDIRECT_URI не указывает на localhost"
    fi
  fi
fi

# =============================================================================
section "ИТОГИ"
printf '  OK: %s   FAIL: %s   WARN: %s\n' "$PASS" "$FAIL" "$WARN"
echo
echo "Вердикт:"
if [ "$FLAG_ROUTE" -eq 0 ]; then
  echo "  ✘ Маршрут не загружен в Caddy → master не видит сервис."
  echo "    → Проверьте service.yml, расположение директории, логи master; рестарт master."
elif [ "$FLAG_UPSTREAM" -eq 0 ] && [ -n "$CONTAINER_NAME" ]; then
  echo "  ✘ Upstream недоступен из сети Caddy → 502 в браузере."
  echo "    → Добавьте контейнер в platform_network, проверьте container_name/internal_port."
elif [ "$FLAG_VALIDATE" -eq 0 ]; then
  echo "  ✘ Master отклоняет домен → сертификат не выпустится → SSL-ошибка у клиента."
  echo "    → Проверьте discovery master'а, рестарт: docker restart $MASTER_CONTAINER."
elif [ "$FLAG_LOCAL" -eq 0 ]; then
  echo "  ✘ Локальный HTTPS не проходит → проблема выпуска сертификата."
  echo "    → Смотрите ошибки ACME в логах Caddy (проверка 8)."
elif [ "$FLAG_LOCAL" -eq 1 ]; then
  echo "  ✔ Серверная цепочка работает. Проблема снаружи сервера:"
  echo "    DNS-запись, клиентская сеть/прокси/браузер. Запустите diagnose-client.sh на клиенте."
fi
exit 0
