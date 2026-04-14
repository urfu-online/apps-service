---
description: Синхронизировать GitHub Issues с docs/plan/
---
## /sync-issues

Сравнивай GitHub Issues с таблицей задач в `@{docs/plan/README.md}`.

### Шаг 1: Получи актуальные issues

Выполни:
```
!{gh issue list --repo urfu-online/apps-service --limit 100 --json number,title,labels,state,closedAt}
```

### Шаг 2: Прочитай локальный план

Прочитай `@{docs/plan/README.md}` — таблицу задач с номерами issues, статусами и приоритетами.

### Шаг 3: Найди расхождения

Сравни по номерам issues (#цифра):

| Сценарий | Что сообщить |
|---|---|
| Issue **open** на GitHub, нет в plan | «Новый issue #N — нет в docs/plan/» |
| Задача есть в plan, нет на GitHub | «Задача #N в plan, нет issue на GitHub» |
| Issue **closed** на GitHub, в plan **⬜** | «Issue #N закрыт, но в plan не помечен ✅» |
| Issue **open** на GitHub, в plan **✅** | «Issue #N открыт, но в plan помечен ✅» |

### Шаг 4: Покажи отчёт

Выведи таблицу:

```
| Что | Issue | Подробности |
|-----|-------|-------------|
```

Если расхождений нет — скажи «✓ Всё синхронизировано».

### Шаг 5: Предложи действия

Для каждого расхождения предложи действие:
- **Новый issue** → «Создать запись в docs/plan/README.md?»
- **Нет issue** → «Создать issue на GitHub?»
- **Статус рассинхрон** → «Обновить статус в docs/plan/README.md?»

Выполняй только после подтверждения пользователя.

> **AI не закрывает issues** — закрытие делает только пользователь.
