# Диагностика недоступного сервиса — универсальная инструкция

> Для человека и ИИ. Скрипты **только читают**: не изменяют файлы, конфиги, контейнеры, сети и настройки ни на сервере, ни на клиенте. Выполняются лишь пробы: DNS, TCP, TLS, HTTP GET, `docker ps/inspect/logs/network inspect/ls/find/grep`.

## 0. Как пользоваться

**Человек:** читает раздел 2 (список проблем) → находит свой симптом → выполняет команды вручную из блока А (сервер) или Б (клиент).

**ИИ-протокол:**
1. Определить переменные из `service.yml` (раздел 1).
2. Запустить `diagnose-client.sh` — получить симптом (DNS / сеть / TLS / HTTP-код).
3. Запустить `diagnose-server.sh` — проверить цепочку Caddy → upstream → master.
4. Сопоставить вердикты со списком проблем (раздел 2) и типовыми вердиктами (раздел 6).
5. Предложить исправление пользователю; ничего не менять без подтверждения.

## 1. Переменные

| Переменная | Откуда взять | Пример |
|---|---|---|
| `SERVICE_NAME` | `service.yml` → `name` | `urfu-forms` |
| `SERVICE_DOMAIN` | итоговый URL: `auto_subdomain` → `{name}.{base_domain}`; `domain` → `routing[].domain`; `subfolder` → `{base_domain}{path}` | `urfu-forms.apps.urfu.online` |
| `BASE_DOMAIN` | `routing[].base_domain` (для auto_subdomain/subfolder) | `apps.urfu.online` |
| `CONTAINER_NAME` | `routing[].container_name` (совпадает с `container_name` в `docker-compose.yml`) | `urfu_forms_frontend` |
| `INTERNAL_PORT` | `routing[].internal_port` | `80` |
| `SERVICES_ROOT` | корень сервисов на сервере | `/apps/services` |
| `REFERENCE_DOMAIN` | домен заведомо работающего сервиса (для сравнения) | `course-archive-explorer.apps.urfu.online` |

Платформенные (обычно не меняются): `CADDY_CONTAINER=caddy`, `MASTER_CONTAINER=platform-master`, `PLATFORM_NETWORK=platform_network`, `MASTER_API_URL=http://localhost:8001`, `CADDY_ADMIN_URL=http://localhost:2019`.

## 2. Краткий список проблем

| # | Симптом | Вероятная причина | Где проверять |
|---|---|---|---|
| 1 | `ERR_NAME_NOT_RESOLVED` в браузере | Нет DNS-записи для поддомена | Б1 |
| 2 | `ERR_CONNECTION_REFUSED` / timeout | Firewall; клиент идёт на порт 80 (Caddy слушает только :443, `disable_redirects`); клиентский прокси | Б0, Б2, Б5 |
| 3 | SSL-ошибка / handshake висит | Сертификат не выдан: master отклонил домен (`/api/tls/validate` → 403) или ошибка ACME | А6, А7, А8 |
| 4 | `502 Bad Gateway` | Caddy не достучался до контейнера: нет в `platform_network`, неверное `container_name`/`internal_port`, приложение не слушает | А3, А5 |
| 5 | `403 Access Denied` от Caddy | `visibility: internal` (доступ только из приватных подсетей) | А1 |
| 6 | Маршрута нет вообще | Master не обнаружил сервис (нет/битый `service.yml`, не та директория) | А1, А4, А8 |
| 7 | Контейнеры не запущены / не задеплоены | Ошибка сборки или деплоя | А2 |
| 8 | Сайт открывается, но API падает | `CORS_ORIGINS` не содержит боевой домен; `KEYCLOAK_REDIRECT_URI` указывает на localhost | А10 |
| 9 | curl работает, браузер нет | Клиентский прокси/кэш/HSTS/расширения | Б0, Б7 |

## 3. Блок А — диагностика на сервере

Выполнять на хосте сервера, где есть доступ к Docker и проброшены порты Caddy admin (2019) и master (8001).

### А1. Манифест
```bash
cat /apps/services/public/<SERVICE_NAME>/service.yml   # или internal/
```
Проверить: `routing[].type`, `container_name` (обязателен!), `internal_port`, `visibility`. Пустой `container_name` → Caddy проксирует на `host.docker.internal` (legacy, сломано).

### А2. Контейнеры
```bash
docker compose --project-directory /apps/services/public/<SERVICE_NAME> ps
docker inspect -f '{{.State.Status}}' <CONTAINER_NAME>
```
Все контейнеры должны быть `Up`. Иначе — смотреть `docker compose ... logs`.

### А3. Docker-сеть
```bash
docker inspect -f '{{range $k,$_ := .NetworkSettings.Networks}}{{$k}} {{end}}' <CONTAINER_NAME>
docker network inspect platform_network --format '{{range .Containers}}{{.Name}} {{end}}'
```
В первой команде должна быть `platform_network`; во второй — и `<CONTAINER_NAME>`, и `caddy`. Нет сети → Caddy не разрешит имя контейнера → 502.

### А4. Маршрут загружен в Caddy
```bash
curl -s http://localhost:2019/config/ | grep -o '<SERVICE_DOMAIN>' | head -1
curl -s http://localhost:2019/config/ | grep -o '"dial":"<CONTAINER_NAME>:<INTERNAL_PORT>"'
```
Домена нет → master не перегенерировал конфиг: проверять discovery master (`docker logs platform-master`), валидность `service.yml`, расположение директории. Домен есть, но `dial` неверный → исправить `container_name`/`internal_port`.

### А5. Upstream изнутри сети Caddy
```bash
docker exec caddy sh -c "wget -S -T 5 -O /dev/null http://<CONTAINER_NAME>:<INTERNAL_PORT>/" 2>&1 | grep -m1 HTTP/
```
- `HTTP/1.1 2xx/3xx` → upstream жив.
- `bad address` → контейнер не в `platform_network` (А3).
- `Connection refused` → приложение не слушает `INTERNAL_PORT` внутри контейнера.
- `502` от Caddy при живом upstream → смотреть А8.

### А6. Master: разрешение on-demand TLS
```bash
curl -s -w '\nHTTP %{http_code}\n' "http://localhost:8001/api/tls/validate?domain=<SERVICE_DOMAIN>"
curl -s http://localhost:8001/api/tls/allowed | grep <SERVICE_DOMAIN>
```
`200` → Caddy может выпускать сертификат. `403` → master не знает домен (discovery не увидел сервис; рестарт master, логи). Master недоступен → проверять `docker ps` и маппинг портов.

### А7. Сертификат в хранилище Caddy
```bash
docker exec caddy find /data/caddy/certificates -maxdepth 2 -name '<SERVICE_DOMAIN>'
```
Пусто — сертификат ещё не выпускался (выпустится при первом HTTPS-запросе; первый запрос может занять несколько секунд). Запросы были, а сертификата нет → А8 (ошибки ACME/permission).

### А8. Логи Caddy
```bash
docker logs caddy --since 24h 2>&1 | grep -iE '<SERVICE_DOMAIN>|on_demand|acme|certificate|error' | tail -40
```
Искать: `permission denied` (А6), `acme: error` (проблемы выпуска), `dial tcp ... connect: refused` (А5).

### А9. Локальный HTTPS-тест в обход DNS
```bash
curl -sk --noproxy '*' --resolve '<SERVICE_DOMAIN>:443:127.0.0.1' \
  -o /dev/null -w '%{http_code}\n' -m 20 "https://<SERVICE_DOMAIN>/"
```
- `2xx/3xx/4xx` → вся серверная цепочка работает; проблема снаружи (DNS/клиент) → блок Б.
- `000` → TLS не поднимается: А6/А7/А8.
- `502` → А5.

### А10. CORS и redirect URI (если сайт открывается, но API падает)
```bash
grep -iE 'CORS_ORIGINS|REDIRECT_URI' /apps/services/public/<SERVICE_NAME>/docker-compose.yml
```
`CORS_ORIGINS` должен содержать `https://<SERVICE_DOMAIN>`; `KEYCLOAK_REDIRECT_URI` — боевой домен, не localhost.

## 4. Блок Б — диагностика на клиенте

### Б0. Прокси (частая ловушка)
`http_proxy`/`https_proxy` перехватывают curl — запрос уходит в локальный прокси, а не на сервер. Все HTTP-пробы делать в обход:
```bash
env | grep -i proxy                       # увидеть, задан ли прокси
curl --noproxy '*' ...                    # обход для curl
# openssl прокси не использует — идёт напрямую
```
Если машина ходит в интернет только через прокси — прямые пробы могут не работать; проверять с другой сети.

### Б1. DNS
```bash
getent hosts <SERVICE_DOMAIN>            # или: dig +short <SERVICE_DOMAIN>
getent hosts <REFERENCE_DOMAIN>          # сравнить с рабочим сервисом
```
Пусто → нет DNS-записи: добавить A-запись на IP сервера (или wildcard `*.apps.urfu.online`).

### Б2. TCP-доступность
```bash
timeout 5 bash -c 'exec 3<>/dev/tcp/<SERVICE_DOMAIN>/443' && echo "443 открыт"
timeout 5 bash -c 'exec 3<>/dev/tcp/<SERVICE_DOMAIN>/80'  || echo "80 закрыт (ожидаемо)"
```
443 закрыт → firewall/внешний LB. Порт 80 закрыт — **норма**: сервер слушает только `:443` (`automatic_https disable_redirects`).

### Б3. TLS
```bash
echo | openssl s_client -connect <SERVICE_DOMAIN>:443 -servername <SERVICE_DOMAIN> 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
echo | openssl s_client -connect <SERVICE_DOMAIN>:443 -servername <SERVICE_DOMAIN> 2>/dev/null \
  | grep -E 'Verify return code'
```
Handshake не проходит → сертификат не выдан → блок А (А6–А8). `Verify return code: 21` (unable to verify) → сертификат есть, но цепочка неполная (обычно лечится повторным запросом/временем).

### Б4. HTTPS без прокси
```bash
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' -m 20 "https://<SERVICE_DOMAIN>/"
curl -s --noproxy '*' -m 20 "https://<SERVICE_DOMAIN>/" | head -c 300   # тело для 403/502
```
- `2xx` → сервис работает; если браузер не открывает — проблема в браузере (Б7).
- `403` + тело `Access Denied` → сервис `internal` или master отклонил TLS-validate (А6).
- `502/504` → блок А (А5).
- `000` → сеть/firewall (Б2) или TLS (Б3).
- `4xx/5xx` от приложения → приложение отвечает, Caddy работает; разбирать логи приложения.

### Б5. HTTP на порту 80
```bash
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' -m 5 "http://<SERVICE_DOMAIN>/"
```
`000`/refused — ожидаемо (порт 80 не слушается). Всегда заходить по `https://`.

### Б6. Эталонное сравнение
```bash
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' "https://<REFERENCE_DOMAIN>/"
```
Эталон `200`, сервис `000` → сетевая проблема только для нового домена (DNS/белый список LB). Оба падают → клиентская сеть/прокси.

### Б7. Браузер
1. DevTools → Network: точный статус и текст ошибки.
2. Приватное окно (без расширений и кэша).
3. HSTS/кэш: `chrome://net-internals/#hsts` → Delete domain security policies.
4. Проверить, что браузер не использует системный прокси для этого домена.

## 5. Скрипты

| Скрипт | Где запускать | Что делает |
|---|---|---|
| `diagnose-client.sh` | на клиенте (рабочая машина) | DNS → TCP → TLS → HTTP без прокси → эталон → вердикт |
| `diagnose-server.sh` | на сервере (нужен Docker) | манифест → контейнеры → сеть → маршрут Caddy → upstream → master TLS → сертификат → логи → локальный HTTPS → CORS |

Оба: вывод со статусами `✔ OK / ✘ FAIL / ⚠ WARN`, пояснение после каждой проверки, итоговый вердикт. **Read-only.**

Запуск:
```bash
# Клиент:
SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
REFERENCE_DOMAIN=course-archive-explorer.apps.urfu.online \
  bash docs/diagnostics/diagnose-client.sh

# Сервер (минимум):
SERVICE_NAME=urfu-forms \
SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
  bash docs/diagnostics/diagnose-server.sh

# Сервер (полный набор, если автоопределение не сработало):
SERVICE_NAME=urfu-forms \
SERVICE_DOMAIN=urfu-forms.apps.urfu.online \
CONTAINER_NAME=urfu_forms_frontend \
INTERNAL_PORT=80 \
SERVICES_ROOT=/apps/services \
  bash docs/diagnostics/diagnose-server.sh
```

## 6. Типовые вердикты → действия

| Вердикт клиентского скрипта | Вердикт серверного | Действие |
|---|---|---|
| DNS FAIL | — | Добавить DNS-запись на IP сервера |
| TCP 443 FAIL | — | Открыть firewall / проверить внешний LB |
| TLS FAIL | validate 403 | Рестарт master / проверить `service.yml` и discovery |
| TLS FAIL | сертификата нет + ошибки ACME в логах | Смотреть логи Caddy; проверить доступность Let's Encrypt |
| HTTPS 502 | upstream FAIL | Добавить контейнер в `platform_network`, исправить `container_name`/`internal_port` |
| HTTPS 403 Access Denied | — | `visibility: internal` → перенести в `services/internal/` или сменить на public |
| HTTPS 2xx | всё OK | Сервис работает; проблема в браузере/прокси клиента (Б0, Б7) |
| HTTPS 2xx, но API падает | CORS/REDIRECT warn | Обновить `CORS_ORIGINS`, `KEYCLOAK_REDIRECT_URI` на боевой домен |
