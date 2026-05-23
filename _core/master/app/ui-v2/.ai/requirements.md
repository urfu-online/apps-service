[ФУНКЦИОНАЛ]

1. Dashboard: статус сервисов, health, алерты, quick actions
2. Services: список, фильтры, deploy/stop/restart, service.yml preview
3. Logs: streaming (SSE/WS), поиск, экспорт, фильтры по level/service/time
4. Backups: список снапшотов Kopia, ручной backup, restore с подтверждением, retention policy
[NON-FUNC]

- CSP: script-src 'self', style-src 'self', frame-ancestors 'none', no unsafe-inline/eval
- Все API-ответы валидируются через zod перед попаданием в state
- Роутинг защищён по ролям из Положения
- Деплой: статика в /dist, Caddy отдаёт с immutable cache, index.html no-cache
