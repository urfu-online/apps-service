# План имплементации LogManager

> **Статус:** 🟠 В разработке (Issue #17)
> **Приоритет:** 🟠 Средний
> **GitHub Issue:** [#17](https://github.com/urfu-online/apps-service/issues/17)

---

## ⚠️ Критические исправления (применены к плану)

На основе аудита плана выявлены и исправлены следующие критические риски:

| № | Риск | Исправление | Приоритет |
|---|------|-------------|-----------|
| 1 | **Блокировка FastAPI event loop** — Docker SDK синхронный | ✅ Все вызовы `docker_manager.get_logs()` обёрнуты в `await asyncio.to_thread()` | 🔴 Критично |
| 2 | **Неточность статистики** — считает только кэш | ✅ Добавлены параметры `full_skan=True` и метаданные `scope`/`note` в ответ API | 🟠 Средний |
| 3 | **Эфемерный экспорт** — файлы удаляются при рестарте | ✅ Используется volume-mounted путь `DATA_DIR/log_exports` | 🟠 Средний |
| 4 | **ANSI-коды** — поиск не работает при `tty: true` | ✅ Добавлен метод `_strip_ansi()` для очистки escape-последовательностей | 🟡 Низкий |
| 5 | **Конкурентные обновления кэша** | ✅ Добавлен `asyncio.Lock()` в `_update_cache()` | 🟡 Низкий |
| 6 | **Малый размер кэша** — 1000 строк мало для отладки | ✅ Увеличено до 5000 строк (`LOG_CACHE_SIZE=5000`) | 🟡 Низкий |
| 7 | **Path traversal** — уязвимость экспорта | ✅ Валидация пути через `Path.resolve().is_relative_to()` | 🟠 Средний |

---

## Оглавление

1. [Текущее состояние](#текущее-состояние)
2. [Проблема](#проблема)
3. [Цели реализации](#цели-реализации)
4. [Архитектурный подход](#архитектурный-подход)
5. [Детальный план реализации](#детальный-план-реализации)
6. [Этапы выполнения](#этапы-выполнения)
7. [Тестирование](#тестирование)
8. [Обновление документации](#обновление-документации)

---

## Текущее состояние

### Статус компонентов

| Компонент | Статус | Примечание |
|-----------|--------|------------|
| `LogManager` (класс) | ❌ Заглушка | In-memory `deque`, данные не персистентны |
| `add_log_entry()` | ❌ Не используется | Метод существует, но никто его не вызывает |
| API `/api/logs/service/{name}` | ⚠️ Обходит LogManager | Читает напрямую из Docker API через `DockerManager.get_logs()` |
| API `/logs/search` | ❌ Работает с пустым кэшем | Использует `LogManager`, который возвращает пустые данные |
| API `/logs/stats` | ❌ Некорректные данные | Статистика считается по пустому кэшу |
| UI страница логов | ⚠️ Частично работает | Использует `LogManager.get_service_logs()`, который возвращает кэш |
| `LogViewer` компонент | ✅ Готов | UI компонент работает, но данные не поступают |

### Файлы, задействованные в текущей реализации

```
_core/master/app/services/log_manager.py      # Заглушка LogManager
_core/master/app/api/routes/logs.py          # API эндпоинты логов
_core/master/app/services/docker_manager.py  # Реальное получение логов из Docker
_core/master/app/ui/logs_page.py            # UI страница логов
_core/master/app/ui/components/log_viewer.py # Компонент отображения логов
_core/master/tests/unit/test_log_endpoints.py # Тесты моделей логов
```

---

## Проблема

1. **LogManager не собирает логи** — `add_log_entry()` никогда не вызывается, кэш всегда пуст.
2. **API эндпоинты работают некорректно**:
   - `GET /api/logs/service/{name}` обходит LogManager и работает напрямую с Docker API.
   - `POST /api/logs/service/{name}/search` ищет по пустому кэшу LogManager.
   - `GET /api/logs/service/{name}/stats` возвращает статистику по пустым данным.
3. **Отсутствует персистентность** — in-memory `deque` теряет все данные при перезапуске.
4. **Комментарий в коде**: *"В реальной реализации здесь будет взаимодействие с Loki или Docker API"* — Loki не реализован, а Docker API используется только напрямую.

---

## Цели реализации

1. Сделать `LogManager` рабочим компонентом, который реально собирает и возвращает логи.
2. Унифицировать получение логов через `LogManager` (API и UI должны использовать его).
3. Добавить кэширование с TTL для уменьшения нагрузки на Docker API.
4. Обеспечить базовую персистентность (сохранение логов в файлы).
5. Сделать поиск и статистику работающими на реальных данных.

---

## Архитектурный подход

### Выбранный подход: Простой (рекомендуемый)

Согласно `docs/plan/4-log-manager.md`, выбран **простой подход**:

> **LogManager → wrapper вокруг `DockerManager.get_logs()`** с кешированием в памяти и TTL. Убрать заглушку, делегировать.

### Почему не Loki/Prometheus?

- Loki/Prometheus/Grafana **не реализованы** в текущей версии платформы.
- Директория `_core/monitoring/` удалена.
- Интеграция с Loki потребует значительных усилий и добавления новых сервисов.

### Схема работы после реализации

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│ API /logs   │────▶│ LogManager   │────▶│ DockerManager    │
│ UI LogsPage │     │              │     │ .get_logs()      │
└─────────────┘     │ • Кэш (TTL) │     └──────────────────┘
                    │ • Поиск      │            │
                    │ • Статистика │            ▼
                    │ • Экспорт    │     ┌──────────────┐
                    └──────────────┘     │ Docker API   │
                          │              │ (контейнеры)  │
                          ▼              └──────────────┘
                    ┌──────────────┐
                    │ Файловое     │
                    │ хранилище    │
                    │ (опционально)│
                    └──────────────┘
```

---

## Детальный план реализации

### 1. Рефакторинг `LogManager` (`_core/master/app/services/log_manager.py`)

#### 1.1 Замена in-memory кэша на работу с Docker API

```python
import re
import asyncio
from collections import deque
from typing import Dict, List, Optional, Any

class LogManager:
    """Управление логами сервисов через Docker API с кэшированием.

    ⚠️ КРИТИЧНО: Docker SDK синхронный. Все вызовы docker_manager.get_logs()
    должны выполняться через await asyncio.to_thread() чтобы не блокировать event loop.
    """

    def __init__(
        self,
        docker_manager: DockerManager,
        cache_ttl: int = 30,  # секунды
        cache_size: int = 5000,  # ✅ Увеличено с 1000 для реальной отладки
        safe_export_path: Optional[Path] = None
    ):
        self.docker_manager = docker_manager
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        # Кэш: {service_name: {"logs": deque, "timestamp": datetime, "total_lines": int}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()  # ✅ Защита от конкурентных обновлений кэша
        # Путь для экспорта (должен быть volume-mounted)
        self.safe_export_path = safe_export_path or (
            Path(settings.DATA_DIR) / "log_exports"
        )
        self.safe_export_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _strip_ansi(line: str) -> str:
        """Удаление ANSI escape-последовательностей из строки лога.

        Docker с tty: true добавляет коды типа [31mERROR[0m.
        Без очистки поиск по 'error' может не сработать.
        """
        ansi_re = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_re.sub('', line)
```

#### 1.2 Метод `get_service_logs()` — основная логика

```python
async def get_service_logs(
    self,
    service: ServiceManifest,
    tail: int = 100,
    since: Optional[str] = None,
    skip_cache: bool = False  # ✅ Флаг для полного сканирования
) -> List[str]:
    """Получение логов сервиса.

    ⚠️ Docker SDK синхронный — используем asyncio.to_thread().
    """
    cache_key = service.name

    # Проверяем кэш (если не требуется полное сканирование)
    if not skip_cache:
        cached = await self._get_cached_logs(cache_key)
        if cached is not None:
            return cached[-tail:] if tail > 0 else cached

    # ✅ КРИТИЧНО: async def + to_thread чтобы не заблокировать event loop
    raw_logs_str = await asyncio.to_thread(
        self.docker_manager.get_logs,
        service,
        tail=tail if not skip_cache else 0,  # 0 = все логи для full_scan
        since=since
    )

    # Парсим строки, очищаем от ANSI-кодов
    raw_lines = raw_logs_str.split("\n") if isinstance(raw_logs_str, str) else []
    cleaned_lines = [self._strip_ansi(line) for line in raw_lines if line.strip()]

    # Опционально: сохраняем в файл для персистентности
    if settings.LOG_ENABLE_PERSISTENCE:
        await self._persist_logs(service.name, cleaned_lines)

    # Обновляем кэш
    await self._update_cache(cache_key, cleaned_lines)
    return cleaned_lines[-tail:] if tail > 0 else cleaned_lines
```

#### 1.3 Метод `search_logs()` — поиск по логам

```python
async def search_logs(
    self,
    service: ServiceManifest,
    query: str,
    limit: int = 50,  # ✅ Ограничение результатов
    case_sensitive: bool = False,
    full_scan: bool = False  # ✅ Полное сканирование игнорирует кэш
) -> List[str]:
    """Поиск по логам сервиса.

    Args:
        full_scan: Если True, игнорирует кэш и делает полный запрос к Docker API.
                   Дорого по ресурсам, но честно для поиска старых ошибок.
    """
    logs = await self.get_service_logs(
        service,
        tail=1000,
        skip_cache=full_scan
    )

    # Поиск
    if case_sensitive:
        matching = [log for log in logs if query in log]
    else:
        query_lower = query.lower()
        matching = [log for log in logs if query_lower in log.lower()]

    # Возвращаем последние N совпадений
    return matching[-limit:]
```

#### 1.4 Метод `get_log_stats()` — статистика

```python
async def get_log_stats(
    self,
    service: ServiceManifest,
    full_scan: bool = False  # ✅ Честная статистика по всем логам
) -> Dict[str, Any]:
    """Получение статистики по логам сервиса.

    ⚠️ Статистика базируется на кэшированных данных (tail-вызов).
    Для полной истории используйте full_scan=True (дорого).
    """
    logs = await self.get_service_logs(
        service,
        tail=1000,
        skip_cache=full_scan
    )

    stats = {
        "total_entries": len(logs),
        "error_count": 0,
        "warning_count": 0,
        "info_count": 0,
        # ✅ Метаданные для честности API
        "scope": "full_scan" if full_scan else "cached_tail",
        "note": "Based on cached tail, not full history" if not full_scan else "Full container history"
    }

    for log in logs:
        log_lower = log.lower()
        if "error" in log_lower or "exception" in log_lower or "fatal" in log_lower:
            stats["error_count"] += 1
        elif "warning" in log_lower or "warn" in log_lower:
            stats["warning_count"] += 1
        else:
            stats["info_count"] += 1

    return stats
```

#### 1.5 Метод `export_logs()` — экспорт в файл

```python
async def export_logs(
    self,
    service: ServiceManifest,
    export_path: Optional[Path] = None
) -> Path:
    """Экспорт логов сервиса в файл.

    ⚠️ Path traversal защита: экспорт только в разрешённую директорию.
    ⚠️ Использует volume-mounted путь, чтобы файлы не удалялись при рестарте.
    """
    # Генерируем имя файла если не указано
    if export_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_path = self.safe_export_path / f"{service.name}_logs_{timestamp}.txt"

    # ✅ Валидация пути (защита от path traversal)
    export_path = export_path.resolve()
    if not export_path.is_relative_to(self.safe_export_path.resolve()):
        raise ValueError(f"Export path {export_path} is not allowed. Must be inside {self.safe_export_path}")

    # Получаем все логи (игнорируем кэш для экспорта)
    logs = await self.get_service_logs(service, tail=0, skip_cache=True)

    async with aiofiles.open(export_path, 'w') as f:
        for log in logs:
            await f.write(log + '\n')

    logger.info(f"Exported {len(logs)} logs for {service.name} to {export_path}")
    return export_path
```

#### 1.6 Кэширование с TTL и блокировкой

```python
async def _get_cached_logs(self, service_name: str) -> Optional[List[str]]:
    """Получение логов из кэша если они актуальны."""
    if service_name not in self._cache:
        return None

    cache_entry = self._cache[service_name]
    age = (datetime.now(timezone.utc) - cache_entry["timestamp"]).total_seconds()

    if age < self.cache_ttl:
        return list(cache_entry["logs"])
    return None

async def _update_cache(self, service_name: str, logs: List[str]):
    """Обновление кэша для сервиса.

    ✅ Используется asyncio.Lock() для защиты от конкурентных обновлений,
    если планируются background-таски с обновлением кэша.
    """
    async with self._lock:
        self._cache[service_name] = {
            "logs": deque(logs, maxlen=self.cache_size),
            "timestamp": datetime.now(timezone.utc),
            "total_lines": len(logs)
        }

async def _persist_logs(self, service_name: str, logs: List[str]):
    """Сохранение логов в файл для персистентности."""
    persist_path = Path(settings.LOG_STORAGE_PATH) / f"{service_name}.log"
    persist_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(persist_path, 'a') as f:
        for log in logs:
            await f.write(log + '\n')
```

---

### 2. Обновление API эндпоинтов (`_core/master/app/api/routes/logs.py`)

#### 2.1 `GET /api/logs/service/{service_name}`

**Текущая проблема:** Использует `DockerManager` напрямую, обходя `LogManager`.

**Решение:** Переписать на использование `LogManager`:

```python
@router.get("/service/{service_name}", response_model=List[str])
async def get_service_logs(
    service_name: str,
    tail: int = 100,
    since: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Получение логов сервиса через LogManager"""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    logs = await app.state.log_manager.get_service_logs(service, tail=tail, since=since)
    return logs
```

#### 2.2 `POST /api/logs/service/{service_name}/search`

**Текущая проблема:** Использует `LogManager.get_service_logs()`, но кэш пуст.

**Решение:** Обновить модель запроса и добавить поддержку новых параметров:

```python
class LogSearchRequest(BaseModel):
    query: str
    limit: int = 50  # ✅ Изменено с 100 на 50 (согласно плану)
    case_sensitive: bool = False
    full_scan: bool = False  # ✅ Честный поиск по всей истории

@router.post("/service/{service_name}/search", response_model=List[str])
async def search_service_logs(
    service_name: str,
    request: LogSearchRequest,
    current_user = Depends(get_current_user)
):
    """Поиск по логам сервиса"""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    results = await app.state.log_manager.search_logs(
        service,
        query=request.query,
        limit=request.limit,
        case_sensitive=request.case_sensitive,
        full_scan=request.full_scan
    )
    return results
```

#### 2.3 `GET /api/logs/service/{service_name}/stats`

**Решение:** Добавить параметр `full_scan` и метаданные в ответ:

```python
@router.get("/service/{service_name}/stats")
async def get_log_stats(
    service_name: str,
    full_scan: bool = False,  # ✅ Query параметр для честной статистики
    current_user = Depends(get_current_user)
):
    """Получение статистики по логам сервиса"""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    stats = await app.state.log_manager.get_log_stats(service, full_scan=full_scan)

    # ✅ Добавляем метаданные (согласно плану)
    stats["total_lines_analyzed"] = stats.get("total_entries", 0)

    return stats
```

#### 2.4 `GET /api/logs/service/{service_name}/export`

**Текущая проблема:** Стаб реализация, просто возвращает сообщение.

**Решение:** Реализовать через `LogManager.export_logs()` с использованием volume-mounted пути:

```python
@router.get("/service/{service_name}/export")
async def export_service_logs(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Экспорт логов сервиса в файл.

    ⚠️ Файл сохраняется в volume-mounted директорию,
    чтобы не удалиться при рестарте контейнера.
    """
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        export_path = await app.state.log_manager.export_logs(service)
        return FileResponse(
            path=export_path,
            filename=export_path.name,
            media_type='text/plain'
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed for {service_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to export logs")
```

---

### 3. Обновление инициализации в `main.py`

**Текущая проблема:** `LogManager` инициализируется без `DockerManager`:

```python
app.state.log_manager = LogManager()  # Не передан docker_manager!
```

**Решение:**

```python
# ✅ Передаем docker_manager и параметры из settings
app.state.log_manager = LogManager(
    docker_manager=app.state.docker,
    cache_ttl=settings.LOG_CACHE_TTL if hasattr(settings, 'LOG_CACHE_TTL') else 30,
    cache_size=settings.LOG_CACHE_SIZE if hasattr(settings, 'LOG_CACHE_SIZE') else 5000,  # ✅ 5000 согласно плану
    safe_export_path=Path(settings.DATA_DIR) / "log_exports" if hasattr(settings, 'DATA_DIR') else None
)
```

---

### 4. Настройки конфигурации (`_core/master/app/config.py`)

Добавить настройки для LogManager:

```python
# Настройки логов (согласно критическим правкам)
LOG_CACHE_TTL: int = 30  # Время жизни кэша в секундах
LOG_CACHE_SIZE: int = 5000  # ✅ Увеличено с 1000 для реальной отладки
LOG_STORAGE_PATH: str = "./.logs_cache"  # Путь для персистентного хранения
LOG_ENABLE_PERSISTENCE: bool = False  # Включить сохранение логов в файлы
DATA_DIR: str = "/data"  # ✅ Базовая директория для volume-mounted путей (экспорт)
```

**Обновление `.env.example`:**

```bash
# LogManager settings
LOG_CACHE_TTL=30
LOG_CACHE_SIZE=5000
LOG_ENABLE_PERSISTENCE=false
DATA_DIR=/data
```

---

### 5. UI компоненты (`_core/master/app/ui/logs_page.py`)

**Текущая ситуация:** `LogsPage` уже использует `LogManager.get_service_logs()`. После реализации п.1 будет работать корректно.

**Дополнительные улучшения:**
- Добавить индикацию загрузки (spinner) при запросе логов.
- Добавить кнопку "Экспорт" для скачивания логов.
- Добавить автообновление (polling) с настраиваемым интервалом.

---

## Этапы выполнения

### Phase 1: Обновление LogManager ✅ (первоочередная задача)

**Задачи:**
1. Добавить в `__init__` параметр `docker_manager`.
2. Реализовать кэширование с TTL в `get_service_logs()`.
3. Обновить `search_logs()` для работы с реальными данными.
4. Обновить `get_log_stats()` для работы с реальными данными.
5. Реализовать `export_logs()` с сохранением в файл.

**Файлы:**
- `_core/master/app/services/log_manager.py`

**Критерий готовности:**
- `LogManager.get_service_logs()` возвращает реальные логи из Docker API.
- Кэширование работает (повторный запрос в течение TTL не вызывает Docker API).

---

### Phase 2: Обновление API эндпоинтов

**Задачи:**
1. Переписать `GET /api/logs/service/{name}` на использование `LogManager`.
2. Реализовать `GET /api/logs/service/{name}/export` с отдачей файла.
3. Проверить работу `search` и `stats` с реальными данными.

**Файлы:**
- `_core/master/app/api/routes/logs.py`

**Критерий готовности:**
- Все API эндпоинты используют `LogManager`.
- Экспорт логов возвращает реальный файл.

---

### Phase 3: Обновление main.py и конфигурации

**Задачи:**
1. Обновить инициализацию `LogManager` в `main.py` (передать `docker_manager`).
2. Добавить настройки `LOG_CACHE_TTL`, `LOG_CACHE_SIZE` в `config.py`.
3. Добавить переменные окружения в `.env.example`.

**Файлы:**
- `_core/master/app/main.py`
- `_core/master/app/config.py`
- `.env.example`

**Критерий готовности:**
- `LogManager` корректно инициализируется с `DockerManager`.
- Настройки можно переопределить через переменные окружения.

---

### Phase 4: Улучшение UI

**Задачи:**
1. Добавить индикацию загрузки в `LogsPage`.
2. Добавить кнопку экспорта логов.
3. Протестировать работу с реальными данными.

**Файлы:**
- `_core/master/app/ui/logs_page.py`

**Критерий готовности:**
- UI страница логов показывает реальные данные.
- Экспорт работает из интерфейса.

---

### Phase 5: Тестирование

**Задачи:**
1. Написать unit-тесты для `LogManager`:
   - Тест кэширования с TTL.
   - Тест `search_logs()`.
   - Тест `get_log_stats()`.
   - Тест `export_logs()`.
2. Написать интеграционные тесты для API эндпоинтов.
3. Ручное тестирование UI.

**Файлы:**
- `_core/master/tests/unit/test_log_manager.py` (новый)
- `_core/master/tests/integration/test_logs_api.py` (новый)

**Критерий готовности:**
- Все тесты проходят.
- Ручное тестирование подтверждает работоспособность.

---

## Тестирование

### Unit-тесты для LogManager

```python
# _core/master/tests/unit/test_log_manager.py
import pytest
from unittest.mock import MagicMock, patch
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from app.services.log_manager import LogManager
from app.services.discovery import ServiceManifest


class TestLogManager:
    """Тесты для LogManager с учётом критических исправлений."""

    @pytest.fixture
    def docker_manager_mock(self):
        """Мок DockerManager (MagicMock т.к. get_logs синхронный)."""
        mock = MagicMock()
        mock.get_logs.return_value = "[2024-01-01T12:00:00] line1\n[2024-01-01T12:00:01] line2"
        return mock

    @pytest.fixture
    def log_manager(self, docker_manager_mock, tmp_path):
        """Экземпляр LogManager с моком."""
        return LogManager(
            docker_manager=docker_manager_mock,
            cache_ttl=1,  # 1 сек для быстрого тестирования TTL
            cache_size=5000,
            safe_export_path=tmp_path / "exports"
        )

    @pytest.fixture
    def service(self):
        """Тестовый сервис."""
        return ServiceManifest(name="test-svc", type="docker-compose")

    async def test_get_service_logs_uses_to_thread(self, log_manager, service):
        """Тест: ✅ Вызов Docker API через asyncio.to_thread."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "[INFO] test log"
            await log_manager.get_service_logs(service, tail=100)
            mock_to_thread.assert_called_once()

    async def test_strip_ansi_removes_codes(self, log_manager):
        """Тест: ✅ ANSI-коды удаляются из логов."""
        ansi_log = "\x1B[31mERROR\x1B[0m: db timeout"
        cleaned = log_manager._strip_ansi(ansi_log)
        assert "\x1B" not in cleaned
        assert cleaned == "ERROR: db timeout"

    async def test_strip_ansi_no_escape(self, log_manager):
        """Тест: строка без ANSI-кодов не меняется."""
        plain = "[INFO] All good"
        assert log_manager._strip_ansi(plain) == plain

    async def test_cache_ttl(self, log_manager, docker_manager_mock, service):
        """Тест: кэш уважает TTL."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "log1\nlog2\nlog3"

            # Первый запрос
            await log_manager.get_service_logs(service, tail=100)
            # Второй запрос (должен взять из кэша)
            await log_manager.get_service_logs(service, tail=100)

            # to_thread должен быть вызван только один раз
            assert mock_to_thread.call_count == 1

            # Ждем истечения TTL
            await asyncio.sleep(1.1)

            # Третий запрос (кэш устарел)
            await log_manager.get_service_logs(service, tail=100)
            assert mock_to_thread.call_count == 2

    async def test_cache_structure(self, log_manager, docker_manager_mock, service):
        """Тест: структура кэша содержит total_lines."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "line1\nline2"
            await log_manager.get_service_logs(service, tail=100)

            cache_entry = log_manager._cache["test-svc"]
            assert "logs" in cache_entry
            assert "timestamp" in cache_entry
            assert "total_lines" in cache_entry
            assert cache_entry["total_lines"] == 2

    async def test_search_logs_basic(self, log_manager, service):
        """Тест: поиск по логам."""
        log_manager._cache["test-svc"] = {
            "logs": deque(["[ERROR] Something wrong", "[INFO] All good"]),
            "timestamp": datetime.now(timezone.utc),
            "total_lines": 2
        }

        results = await log_manager.search_logs(service, query="error")
        assert len(results) == 1
        assert "ERROR" in results[0]

    async def test_search_logs_limit(self, log_manager, service):
        """Тест: ✅ поиск с ограничением limit."""
        log_manager._cache["test-svc"] = {
            "logs": deque(["[ERROR] 1", "[ERROR] 2", "[ERROR] 3"]),
            "timestamp": datetime.now(timezone.utc),
            "total_lines": 3
        }

        results = await log_manager.search_logs(service, query="error", limit=2)
        assert len(results) == 2

    async def test_search_logs_case_sensitive(self, log_manager, service):
        """Тест: ✅ поиск с case_sensitive."""
        log_manager._cache["test-svc"] = {
            "logs": deque(["[ERROR] error", "[ERROR] ERROR"]),
            "timestamp": datetime.now(timezone.utc),
            "total_lines": 2
        }

        # case_sensitive=False (по умолчанию)
        results = await log_manager.search_logs(service, query="error")
        assert len(results) == 2

        # case_sensitive=True
        results = await log_manager.search_logs(service, query="ERROR", case_sensitive=True)
        assert len(results) == 1

    async def test_search_logs_full_scan(self, log_manager, docker_manager_mock, service):
        """Тест: ✅ full_scan игнорирует кэш."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "[ERROR] full scan log"

            # Устанавливаем кэш
            log_manager._cache["test-svc"] = {
                "logs": deque(["[INFO] cached"]),
                "timestamp": datetime.now(timezone.utc),
                "total_lines": 1
            }

            # full_scan=True должен вызвать Docker API
            await log_manager.search_logs(service, query="error", full_scan=True)
            mock_to_thread.assert_called_once()

    async def test_get_log_stats(self, log_manager, service):
        """Тест: статистика по логам с метаданными."""
        log_manager._cache["test-svc"] = {
            "logs": deque([
                "[ERROR] Error 1",
                "[ERROR] Error 2",
                "[WARNING] Warning 1",
                "[INFO] Info 1",
            ]),
            "timestamp": datetime.now(timezone.utc),
            "total_lines": 4
        }

        stats = await log_manager.get_log_stats(service)
        assert stats["error_count"] == 2
        assert stats["warning_count"] == 1
        assert stats["info_count"] == 1
        # ✅ Проверяем метаданные
        assert stats["scope"] == "cached_tail"
        assert "note" in stats

    async def test_get_log_stats_full_scan_meta(self, log_manager, docker_manager_mock, service):
        """Тест: ✅ full_scan добавляет правильные метаданные."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "[ERROR] test"

            stats = await log_manager.get_log_stats(service, full_scan=True)
            assert stats["scope"] == "full_scan"
            assert stats["note"] == "Full container history"

    async def test_export_logs_path_traversal(self, log_manager, service):
        """Тест: ✅ Path traversal защита работает."""
        with pytest.raises(ValueError, match="not allowed"):
            bad_path = Path("/etc/passwd")
            await log_manager.export_logs(service, export_path=bad_path)

    async def test_export_logs_persistence(self, log_manager, service):
        """Тест: ✅ Экспорт использует safe_export_path (volume-mounted)."""
        with patch('app.services.log_manager.asyncio.to_thread', new_callable=MagicMock) as mock_to_thread:
            mock_to_thread.return_value = "log1\nlog2"

            export_path = await log_manager.export_logs(service)

            # Проверяем, что файл в разрешённой директории
            assert export_path.is_relative_to(log_manager.safe_export_path)
            assert export_path.exists()

    async def test_concurrent_cache_updates(self, log_manager, service):
        """Тест: ✅ asyncio.Lock() защищает от конкурентных обновлений."""
        import asyncio

        # Имитируем конкурентные обновления
        async def update_cache(idx):
            async with log_manager._lock:
                log_manager._cache["test-svc"] = {
                    "logs": deque([f"log from {idx}"]),
                    "timestamp": datetime.now(timezone.utc),
                    "total_lines": 1
                }

        # Запускаем несколько корутин одновременно
        tasks = [asyncio.create_task(update_cache(i)) for i in range(10)]
        await asyncio.gather(*tasks)

        # Если Lock() работает, мы не должны получить RuntimeError
        assert "test-svc" in log_manager._cache
```


---

## Обновление документации

### Файлы для обновления

| Файл | Что обновить |
|------|--------------|
| `README.md` | Обновить статус LogManager с ❌ на ✅, обновить таблицу компонентов |
| `docs/user-guide/monitoring.md` | Удалить упоминание заглушки, описать реальную работу |
| `docs/plan/4-log-manager.md` | Отметить выполнение задачи, добавить ссылку на этот план |
| `docs/plan/README.md` | Обновить статус задачи #17 на ✅ |
| `docs/index.md` | Обновить статус LogManager |

### Пример обновления README.md

```markdown
| LogManager       | ✅     | Работает через Docker API с кэшированием (TTL 30s)       |
```

---

## Итоговое сравнение: До и После

| Аспект | До реализации | После реализации |
|--------|---------------|------------------|
| Источник логов | Заглушка / прямой Docker API | Docker API через LogManager |
| Кэширование | Нет (или пустой deque) | TTL-кэш (по умолчанию 30с) |
| Поиск | Не работает (пустой кэш) | Работает по реальным данным |
| Статистика | Некорректная (по пустым данным) | Корректная по реальным данным |
| Экспорт | Стаб (возвращает сообщение) | Реальный файл |
| API единообразие | `GET /logs` обходит LogManager | Все эндпоинты используют LogManager |

---

## Заметки и допущения

1. **Персистентность**: В первой версии можно ограничиться in-memory кэшем с TTL. Сохранение в файлы — опциональная функция.
2. **Масштабируемость**: Если сервисов станет слишком много, кэш в памяти может занять много места. В будущем можно добавить Loki или другой централизованный сборщик логов.
3. **Docker API**: Используется библиотека `docker` (через контекстный менеджер `docker_client()`). Убедиться, что она доступна в зависимостях.
4. **Streaming логи**: В будущем можно добавить WebSocket для стриминга логов в реальном времени (пригодится для UI).

---

## Чеклист для разработки

### Критические исправления (приоритет выполнения)
- [ ] ✅ **Блокировка event loop** — обернуть `docker_manager.get_logs()` в `await asyncio.to_thread()`
- [ ] ✅ **Персистентный экспорт** — использовать volume-mounted путь `DATA_DIR/log_exports`
- [ ] ✅ **Path traversal защита** — валидация пути через `Path.resolve().is_relative_to()`
- [ ] **Кэш размер** — установить `cache_size=5000` (уже в плане)

### Основные задачи
- [ ] Обновить `LogManager.__init__()` для приёма `DockerManager` и новых параметров
- [ ] Добавить метод `_strip_ansi()` для очистки ANSI-кодов
- [ ] Добавить `asyncio.Lock()` для защиты конкурентных обновлений кэша
- [ ] Реализовать TTL-кэш с `asyncio.to_thread()` в `get_service_logs()`
- [ ] Добавить параметры `skip_cache` и очистку ANSI в `get_service_logs()`
- [ ] Обновить `search_logs()` — добавить `limit`, `case_sensitive`, `full_scan`
- [ ] Обновить `get_log_stats()` — добавить `full_scan` и метаданные `scope`/`note`
- [ ] Реализовать `export_logs()` с path traversal защитой и volume-mounted путём
- [ ] Обновить API эндпоинты с новыми параметрами
- [ ] Обновить инициализацию в `main.py` (передать `safe_export_path`)
- [ ] Добавить настройки в `config.py` (`DATA_DIR`, `LOG_CACHE_SIZE=5000`)
- [ ] Написать unit-тесты (включая тесты для критических исправлений)
- [ ] Обновить документацию
- [ ] Протестировать вручную (UI + API)

---

**Документ создан:** 2026-04-24
**Версия:** 1.0
**Автор:** На основе анализа кодовой базы проекта `apps-service-opus`
