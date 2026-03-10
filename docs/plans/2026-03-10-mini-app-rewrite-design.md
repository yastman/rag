# Mini App Rewrite — Design

**Дата:** 2026-03-10
**Статус:** Approved

## Проблема

Mini App на `@twa-dev/sdk` (raw `window.Telegram.WebApp`):
- `openTelegramLink` не работает (известные баги платформы)
- Нет debug: консоль закрывается вместе с Mini App
- Нет mock env: каждый тест через Cloudflare tunnel → Telegram
- Docker frontend unhealthy, медленный цикл пересборки

## Решение

Полная переписка фронтенда на `@telegram-apps/sdk-react` v3 с сохранением текущей функциональности.

## Архитектура

```
mini_app/frontend/src/
├── main.tsx              # init SDK, Eruda (dev), mockTelegramEnv (dev)
├── App.tsx               # SDKProvider + routes
├── api.ts                # fetchConfig, startExpert, submitPhone, remoteLog
├── pages/
│   ├── HomePage.tsx       # список вопросов + экспертов
│   ├── QuestionSheet.tsx  # промты → sendData → close
│   └── ExpertSheet.tsx    # промты → startExpert → openTelegramLink (SDK v3)
├── components/            # BottomSheet, PromptRow, ChatInput, etc
└── hooks/
    └── useTelegramEnv.ts  # mockTelegramEnv для dev, isTMA проверка
```

### Ключевые изменения

- `@twa-dev/sdk` → `@telegram-apps/sdk-react` v3
- `window.Telegram.WebApp.*` → хуки SDK (`useLaunchParams`, `useSignal`, etc)
- `openTelegramLink` через SDK с try/catch + fallback `location.href`
- `mockTelegramEnv` в dev — работает в браузере без Telegram
- Eruda инициализируется в dev/staging
- Remote logging (`/api/log`) — сохраняется

### Без изменений

- Бэкенд (api.py, expert_start.py, auth.py, phone.py)
- 3 страницы: HomePage, QuestionSheet, ExpertSheet
- Deep link flow: Mini App → API → Redis → deep link → бот → тред → RAG
- Docker compose конфигурация (для prod)

## Deep Link Flow

```
ExpertSheet → startExpert(userId, expertId, text)
  → POST /api/start-expert → Redis SET miniapp:q:{uuid}
  → response: { start_link }
  → SDK openTelegramLink(start_link)
    → catch → fallback: location.href = start_link
  → Mini App закрывается
  → Бот: /start q_{uuid} → Redis GETDEL → TopicManager → RAG
```

```typescript
import { openTelegramLink } from '@telegram-apps/sdk-react';

try {
  openTelegramLink(data.start_link);
} catch {
  window.location.href = data.start_link;
}
```

## Debug & Dev Workflow

### Локальная разработка (90% времени)

```
npm run dev → localhost:5173
  → mockTelegramEnv подставляет фейковый user/initData
  → Vite proxy: /api/* → localhost:8090 (Docker mini-app-api)
  → Chrome DevTools — console, network, breakpoints
```

### Тест в Telegram (smoke test)

```
ssh -R 8091:127.0.0.1:5173 vps -N
  → miniapp.awdawdawd.space → Vite dev server (hot reload)
  → Eruda консоль прямо в Mini App
  → Remote logging: /api/log → docker logs dev-mini-app-api-1
```

### 3 уровня дебага

| Уровень | Инструмент | Когда |
|---------|-----------|-------|
| Браузер | Chrome DevTools | Локальная разработка, mock env |
| Telegram | Eruda (автоматически в dev) | Smoke test через tunnel |
| После закрытия | Remote logging `/api/log` | Отлов ошибок openTelegramLink |

### Vite config

```typescript
server: {
  proxy: { "/api": "http://localhost:8090" }
}
```

### Что работает локально

| Функция | Браузер | Telegram |
|---------|---------|----------|
| Навигация, UI | ✅ | ✅ |
| API calls | ✅ | ✅ |
| openTelegramLink | mock (лог в консоль) | ✅ реальный |
| sendData | mock (лог в консоль) | ✅ |
| Hot reload | ✅ | ✅ через tunnel |
| Remote logging | ✅ | ✅ |

Docker для фронтенда — только для VPS deploy.
