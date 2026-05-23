# Техническое задание: Фронтенд приложение на React.js

## 1. Общее описание

Разработка современного одностраничного приложения (SPA) с использованием React 18, TypeScript и Vite для управления сервисами, логами и резервными копиями. Приложение будет интегрировано с существующей backend-инфраструктурой через REST API.

## 2. Архитектура проекта

### 2.1 Структура проекта

```
_core/master/app/ui-v2/
├── src/
│   ├── components/
│   │   ├── dashboard/
│   │   ├── services/
│   │   ├── logs/
│   │   ├── backups/
│   │   ├── layout/
│   │   └── auth/
│   ├── routes/
│   ├── lib/
│   ├── services/
│   ├── hooks/
│   ├── types/
│   └── utils/
├── public/
├── vite.config.ts
├── tsconfig.json
├── package.json
└── README.md
```

### 2.2 Технологии

- **Frontend Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **Routing**: React Router 6
- **State Management**: React Query (TanStack Query)
- **Validation**: Zod
- **UI Components**: shadcn/ui (компоненты для UI)
- **Styling**: CSS Modules + Tailwind CSS
- **Security**: CSP-compliant build, SRI, no inline scripts

## 3. Компоненты приложения

### 3.1 Компоненты макета

#### Header.tsx

- Навигационная панель
- Информация о пользователе
- Кнопка входа/выхода
- Уведомления

#### Sidebar.tsx

- Боковое меню навигации
- Список разделов приложения
- Состояние сервисов

### 3.2 Компоненты разделов

#### Dashboard.tsx

- Обзор состояния сервисов
- Health-статусы
- Алерты и уведомления
- Быстрые действия (deploy, stop, restart)
- Карточки метрик

#### Services.tsx

- Список сервисов
- Фильтры (по статусу, типу, имени)
- Действия: deploy, stop, restart
- Просмотр service.yml
- Статусы сервисов

#### Logs.tsx

- Поток логов (SSE/WebSocket)
- Поиск по логам
- Экспорт логов
- Фильтры по level, service, time
- Таблица событий

#### Backups.tsx

- Список снапшотов Kopia
- Ручной backup
- Восстановление с подтверждением
- Политика хранения (retention policy)
- Статусы резервных копий

## 4. Состояние приложения

### 4.1 React Query для управления состоянием

Используется React Query для:

- Кэширования данных API
- Обработки ошибок
- Управления загрузкой данных
- Синхронизации состояния с сервером

### 4.2 Структура состояния

```typescript
// src/types/state.ts
interface AppState {
  user: User | null;
  services: Service[];
  logs: LogEntry[];
  backups: Backup[];
  alerts: Alert[];
  loading: boolean;
  error: string | null;
}

interface User {
  id: string;
  name: string;
  roles: string[];
  token: string;
}

interface Service {
  id: string;
  name: string;
  status: 'running' | 'stopped' | 'error';
  health: HealthStatus;
  lastDeployed: string;
  config: ServiceConfig;
}

interface LogEntry {
  id: string;
  timestamp: string;
  service: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
}

interface Backup {
  id: string;
  service: string;
  timestamp: string;
  size: number;
  status: 'success' | 'failed' | 'in_progress';
  retentionPolicy: RetentionPolicy;
}
```

## 5. Маршрутизация

### 5.1 Защищенные маршруты

```typescript
// src/routes/index.tsx
const routes = [
  {
    path: '/',
    element: <Dashboard />,
    protected: true,
    roles: ['admin', 'user']
  },
  {
    path: '/services',
    element: <Services />,
    protected: true,
    roles: ['admin', 'user']
  },
  {
    path: '/logs',
    element: <Logs />,
    protected: true,
    roles: ['admin', 'user']
  },
  {
    path: '/backups',
    element: <Backups />,
    protected: true,
    roles: ['admin', 'user']
  },
  {
    path: '/login',
    element: <Login />,
    protected: false
  }
];
```

### 5.2 Защита маршрутов

- Все маршруты кроме `/login` защищены
- Проверка ролей пользователей
- Перенаправление на страницу входа при недостаточных правах

## 6. Взаимодействие с API

### 6.1 Сервисы API

```typescript
// src/services/api.ts
export class ApiService {
  private baseUrl: string;
  private token: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_URL || '/api';
    this.token = localStorage.getItem('token') || '';
  }

  // Service endpoints
  getServices(): Promise<Service[]> {
    return this.get('/services');
  }

  deployService(name: string): Promise<void> {
    return this.post(`/services/${name}/deploy`);
  }

  stopService(name: string): Promise<void> {
    return this.post(`/services/${name}/stop`);
  }

  restartService(name: string): Promise<void> {
    return this.post(`/services/${name}/restart`);
  }

  // Logs endpoints
  getLogs(serviceName: string): Promise<LogEntry[]> {
    return this.get(`/logs/service/${serviceName}`);
  }

  // Backups endpoints
  getBackups(serviceName: string): Promise<Backup[]> {
    return this.get(`/backups/service/${serviceName}`);
  }

  createBackup(serviceName: string): Promise<Backup> {
    return this.post(`/backups/service/${serviceName}`);
  }

  // Health endpoints
  getHealth(): Promise<HealthStatus> {
    return this.get('/health');
  }
}
```

### 6.2 Валидация данных

Все ответы API валидируются через Zod перед попаданием в состояние приложения:

```typescript
// src/lib/zod.ts
import { z } from 'zod';

export const ServiceSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(['running', 'stopped', 'error']),
  health: z.object({
    status: z.enum(['healthy', 'unhealthy', 'unknown']),
    timestamp: z.string()
  }),
  lastDeployed: z.string()
});

export const LogEntrySchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  service: z.string(),
  level: z.enum(['info', 'warn', 'error', 'debug']),
  message: z.string()
});
```

## 7. Безопасность

### 7.1 Content Security Policy

- script-src 'self'
- style-src 'self'
- frame-ancestors 'none'
- Запрет на unsafe-inline и unsafe-eval
- Безопасные импорты ресурсов

### 7.2 Интеграция с Keycloak OIDC

- OAuth2/OpenID Connect для аутентификации
- JWT токены для авторизации
- Защита API-запросов токенами
- Обновление токенов при истечении

## 8. Сборка и деплой

### 8.1 Конфигурация Vite

- CSP-совместимая сборка без SSR
- Безопасная сборка без inline скриптов
- Использование SRI для ресурсов
- Immutable cache для статики
- No-cache для index.html

### 8.2 CI/CD

- Проверка линтинга
- Проверка типов
- Сборка приложения
- Тестирование

## 9. Требования к реализации

### 9.1 Требования к коду

- Все API-ответы валидируются через Zod
- Использование строго типизированных интерфейсов
- Соблюдение принципов React 18
- Чистый код с минимальной заботой о производительности

### 9.2 Требования к безопасности

- CSP-совместимая сборка
- Безопасная работа с токенами
- Нет inline скриптов или стилей
- Безопасное использование ресурсов

### 9.3 Требования к пользовательскому интерфейсу

- Адаптивный дизайн
- Доступность
- Согласованность стиля
- Понятные элементы управления
