[АРХИТЕКТУРА]

- Backend: FastAPI (Python 3.11+), REST + SSE/WebSocket, JWT/Keycloak
- Proxy: Caddy (динамический API, SSL, CSP, SRI)
- Services: Docker compose, Kopia (backup), Loki/Prometheus (partial)
- Current UI: NiceGUI (монолит, Python-driven)
- Target UI: Vite + React 18 + TS, SPA, @tanstack/react-query, zod, shadcn/ui
- Security: Zero-Trust validation, strict CSP, SRI, no eval/inline, no SSR in prod
[РОЛИ]
- Администратор,  Пользователь, Анонимный
[API КОНТРАКТЫ]
- /api/services, /api/services/{name}/deploy|stop|restart
- /api/logs/service/{name} [GET/POST search/stats]
- /api/backups/service/{name} [GET/POST backup/restore]
- /api/health [/health, /health/service/{name}]
- Auth: Keycloak OIDC/JWT
  
ВАЖНО: Проект должен находиться строго в _core/master/app/ui-v2/. Не создавай файлы в корне репозитория.
Выводи ТОЛЬКО полные файлы с путями относительно_core/master/app/ui-v2/
