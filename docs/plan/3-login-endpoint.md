# Login endpoint в API

## Проблема

Все API-эндпоинты защищены `Depends(get_current_user)`. Способов получить токен через API — нет.

**Текущее состояние:**
- Builtin auth: «токен» = `str(user_id)`, небезопасно
- Keycloak: токен получается напрямую от Keycloak, минуя API платформы
- Нет `/login`, `/token`, `/auth` endpoint'ов

## Подход

Вариант A — простой: добавить `/auth/login` для builtin auth (username + password → JWT)
Вариант B — правильный: добавить `/auth/login` (builtin) + `/auth/callback` (Keycloak redirect)

## Папка

`./3-login-endpoint/`
