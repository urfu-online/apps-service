#!/usr/bin/env bash
# =============================================================================
# diagnose-all.sh — массовая диагностика: пройтись по всем сервисам платформы
#
# Для каждого сервиса из SERVICES_ROOT запускает diagnose-server.sh (только
# чтение), собирает счётчики OK/FAIL/WARN и печатает итоговую таблицу.
# Полный вывод каждого сервиса сохраняется в отдельный лог.
#
# ЗАПУСК:
#   bash diagnose-all.sh                       # все сервисы из /apps/services
#   ONLY=support bash diagnose-all.sh          # один сервис
#   VERBOSE=1 bash diagnose-all.sh             # полный вывод в консоль дублируется
#   SERVICES_ROOT=/apps/services bash diagnose-all.sh
#
# Код выхода: 0 — ни одного FAIL; 1 — есть хотя бы один FAIL.
# Требуется: bash, docker, см. diagnose-server.sh.
# =============================================================================
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIAGNOSE="$SCRIPT_DIR/diagnose-server.sh"
SERVICES_ROOT="${SERVICES_ROOT:-/apps/services}"
ONLY="${ONLY:-}"
VERBOSE="${VERBOSE:-0}"

RUN_TS=$(date +%Y%m%d-%H%M%S)
OUT_DIR="/tmp/diagnose-all-$RUN_TS"
mkdir -p "$OUT_DIR"

if [ ! -f "$DIAGNOSE" ]; then
  echo "ОШИБКА: не найден $DIAGNOSE"
  exit 2
fi

if [ -t 1 ]; then
  G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; D=$'\e[2m'; N=$'\e[0m'
else
  G=""; R=""; Y=""; C=""; B=""; D=""; N=""
fi

echo "${B}${C}━━━━ Диагностика всех сервисов ($SERVICES_ROOT) ━━━━${N}"
echo "  Логи прогонов: $OUT_DIR"

# Собираем список сервисов: имя берём из name: манифеста (оно не всегда
# совпадает с именем директории — это норма).
declare -a NAMES=() DIRS=()
for d in "$SERVICES_ROOT"/public/*/ "$SERVICES_ROOT"/internal/*/; do
  [ -f "$d/service.yml" ] || continue
  name=$(grep -m1 '^name:' "$d/service.yml" | sed 's/.*name:[[:space:]]*//' | tr -d "\"'" | xargs || true)
  [ -z "$name" ] && name=$(basename "$d")
  if [ -n "$ONLY" ] && [ "$name" != "$ONLY" ]; then continue; fi
  NAMES+=("$name")
  DIRS+=("${d%/}")
done

if [ "${#NAMES[@]}" -eq 0 ]; then
  echo "Сервисы не найдены в $SERVICES_ROOT (или фильтр ONLY=$ONLY ничего не дал)."
  exit 2
fi

echo "  Найдено сервисов: ${#NAMES[@]}"
echo

TOTAL_FAIL=0
declare -a SUMMARY=()

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  dir="${DIRS[$i]}"
  log_file="$OUT_DIR/$name.log"

  printf '%s▶ %s%s %s(%s)%s\n' "$B$C" "$name" "$N" "$D" "$dir" "$N"

  SERVICE_NAME="$name" SERVICE_DIR="$dir" bash "$DIAGNOSE" >"$log_file" 2>&1
  rc=$?

  # Счётчики и вердикт из вывода диагностики
  counters=$(grep -m1 -oE 'OK: [0-9]+ +FAIL: [0-9]+ +WARN: [0-9]+' "$log_file" || echo "OK: ? FAIL: ? WARN: ?")
  verdict=$(grep -m1 -E '^  [✘✔ℹ]' "$log_file" | sed 's/^ *//' || true)
  ok_n=$(echo "$counters" | grep -oE 'OK: [0-9?]+' | grep -oE '[0-9?]+')
  fail_n=$(echo "$counters" | grep -oE 'FAIL: [0-9?]+' | grep -oE '[0-9?]+')
  warn_n=$(echo "$counters" | grep -oE 'WARN: [0-9?]+' | grep -oE '[0-9?]+')

  if [ "$rc" -ne 0 ] && [ "${fail_n:-?}" != "0" ]; then
    printf '  %sFAIL%s  OK:%s FAIL:%s WARN:%s — %s\n' "$R" "$N" "$ok_n" "$fail_n" "$warn_n" "${verdict:-<см. лог>}"
    printf '  %s→ лог: %s%s\n' "$Y" "$log_file" "$N"
    TOTAL_FAIL=$((TOTAL_FAIL+1))
    SUMMARY+=("FAIL|$name|OK:$ok_n FAIL:$fail_n WARN:$warn_n")
  elif [ "${warn_n:-0}" != "0" ]; then
    printf '  %sWARN%s OK:%s FAIL:%s WARN:%s — %s\n' "$Y" "$N" "$ok_n" "$fail_n" "$warn_n" "${verdict:-}"
    SUMMARY+=("WARN|$name|OK:$ok_n FAIL:$fail_n WARN:$warn_n")
  else
    printf '  %sOK%s   OK:%s FAIL:%s WARN:%s\n' "$G" "$N" "$ok_n" "$fail_n" "$warn_n"
    SUMMARY+=("OK|$name|OK:$ok_n FAIL:$fail_n WARN:$warn_n")
  fi

  if [ "$VERBOSE" = "1" ]; then
    sed 's/^/    /' "$log_file"
  fi
  echo
done

echo "${B}${C}━━━━ ИТОГОВАЯ ТАБЛИЦА ━━━━${N}"
printf '  %-6s %-28s %s\n' "СТАТУС" "СЕРВИС" "СЧЁТЧИКИ"
for row in "${SUMMARY[@]}"; do
  st="${row%%|*}"; rest="${row#*|}"
  name="${rest%%|*}"; cnt="${rest#*|}"
  case "$st" in
    OK)   col="$G" ;;
    FAIL) col="$R" ;;
    *)    col="$Y" ;;
  esac
  printf "  ${col}%-6s${N} %-28s %s\n" "$st" "$name" "$cnt"
done
echo
echo "  Полные логи: $OUT_DIR"
if [ "$TOTAL_FAIL" -gt 0 ]; then
  echo "  ✘ Сервисов с FAIL: $TOTAL_FAIL из ${#NAMES[@]}"
  exit 1
fi
echo "  ✔ FAIL нет. WARN — см. логи/таблицу выше."
exit 0
