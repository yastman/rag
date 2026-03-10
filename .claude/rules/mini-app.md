---
paths: "mini_app/**/*.py, mini_app/**/*.tsx, mini_app/**/*.ts, telegram_bot/config/mini_app.yaml, telegram_bot/services/topic_service.py, telegram_bot/services/topic_manager.py, telegram_bot/services/draft_streamer.py, .env"
---

# Mini App (Telegram Web App)

## SDK

**@tma.js/sdk-react** — официальный React SDK для Telegram Mini Apps. Заменяет raw `window.Telegram.WebApp`.

Инициализация через `bootstrap.ts` (единый orchestrator):

```typescript
// bootstrap.ts — порядок инициализации:
setupMockEnv();              // 1. Mock env (dev only, до SDK — ставит TelegramWebviewProxy)
// isDev ? true : await isTMA("complete")  // 2. Dev = всегда true, prod = строгая проверка
init();                      // 3. SDK init (@tma.js/sdk-react)
initData.restore();          // 4. Restore user/auth_date/hash
themeParams.mount();         // 5. Mount theme params
themeParams.bindCssVars();   // 6. Bind --tg-theme-* CSS vars
await viewport.mount();      // 7. Viewport (async, .isAvailable() guard)
viewport.bindCssVars();      // 8. Viewport CSS vars
swipeBehavior.mount();       // 9. Swipe protection (.isSupported() guard)
swipeBehavior.disableVertical(); // 10. Disable vertical swipe
// try/catch: если init() бросает UnknownEnvError в dev → applyFallbackTheme()
```

Пакеты:
- `@tma.js/sdk-react` — init, initData, themeParams, viewport, swipeBehavior, openTelegramLink, miniApp, sendData
- `@tma.js/bridge` — isTMA, mockTelegramEnv

### Ключевые API

| Функция | Пакет | Паттерн | Назначение |
|---------|-------|---------|------------|
| `miniApp.close` | `@tma.js/sdk-react` | `.ifAvailable()` | Закрытие Mini App |
| `initData.user()` | `@tma.js/sdk-react` | Прямой вызов | `{ id, firstName, lastName, username }` |
| `initData.queryId()` | `@tma.js/sdk-react` | Optional | Session ID (MenuButtonWebApp), передаётся в backend payload |
| `sendData` | `@tma.js/sdk-react` | `.ifAvailable(text)` | Только для KeyboardButton Mini Apps |
| `viewport.mount` | `@tma.js/sdk-react` | `.isAvailable()` — Computed signal | Async mount viewport |
| `swipeBehavior.isSupported` | `@tma.js/sdk-react` | Computed signal `()` | true если платформа поддерживает |
| `swipeBehavior.disableVertical` | `@tma.js/sdk-react` | Вызов после mount | Запрет вертикального свайпа |
| `isTMA("complete")` | `@tma.js/bridge` | Async проверка | Promise<boolean>, строгая проверка |
| `mockTelegramEnv` | `@tma.js/bridge` | `({ launchParams: {object}, onEvent })` | Фейк env для локальной разработки |

### Передача данных из Mini App в бот

| Способ | Когда работает | Ограничения |
|--------|---------------|-------------|
| `sendData` | Только KeyboardButton Mini Apps | НЕ работает для MenuButtonWebApp |
| `answerWebAppQuery` | MenuButtonWebApp + InlineButton | Отправляет в General chat, НЕ в forum topic |
| Backend relay (Redis pub/sub) | Всегда | Для тихой серверной логики без сообщения в чат |

**У нас:** MenuButtonWebApp + forum topics → backend relay через Redis pub/sub.
`answerWebAppQuery` не подходит — не поддерживает `message_thread_id`, дублирует в General.

### Anti-patterns

- **НЕ** `window.Telegram.WebApp.*` — используй SDK хуки
- **НЕ** `openTelegramLink(t.me/OUR_BOT?start=)` — deep link к своему боту молча игнорируется из Mini App
- **НЕ** `answerWebAppQuery` для forum topics — не поддерживает `message_thread_id`, дублирует в General
- **НЕ** `@telegram-apps/sdk-react` — мигрировано на `@tma.js/sdk-react`
- **НЕ** `mountThemeParamsSync` / `bindThemeParamsCssVars` — устаревшие методы, используй `themeParams.mount()` + `themeParams.bindCssVars()`
- **НЕ** `<script src="telegram-web-app.js">` в index.html — SDK сам управляет
- **НЕ** инициализировать SDK в main.tsx напрямую — только через `bootstrap.ts`
- **НЕ** `if (isTMA()) return` в mockEnv — sessionStorage переживает reload, window globals нет → UnknownEnvError
- **НЕ** `mockTelegramEnv({ launchParams: new URLSearchParams(...) })` — object format: `{ tgWebAppThemeParams, tgWebAppData, tgWebAppVersion, tgWebAppPlatform }` + `onEvent` handler
- **НЕ** `closeMiniApp()` — используй `miniApp.close.ifAvailable()`

## Архитектура

```
mini_app/
├── api.py              # FastAPI backend (порт 8090): /api/config, /api/start-expert, /api/phone, /api/log
├── auth.py             # Telegram WebApp auth (initData validation)
├── expert_start.py     # StartExpertRequest/Response модели для /api/start-expert
├── phone.py            # Phone collection endpoints
├── Dockerfile          # uv sync → uvicorn
└── frontend/
    ├── src/
    │   ├── main.tsx        # Entry point: await initApp() → TelegramGate → App
    │   ├── bootstrap.ts    # TMA lifecycle orchestrator (init, theme, viewport, swipe)
    │   ├── mockEnv.ts      # mockTelegramEnv для dev в браузере (@tma.js/bridge)
    │   ├── App.tsx         # Routes: /, /question/:id, /expert/:id
    │   ├── api.ts          # fetchConfig(), startExpert(), submitPhone(), remoteLog()
    │   ├── types.ts        # Prompt, Question, Expert, AppConfig
    │   ├── guards/
    │   │   └── TelegramGate.tsx  # Guard: fallback если не в Telegram (prod)
    │   └── pages/
    │       ├── HomePage.tsx
    │       ├── QuestionSheet.tsx  # sendData.ifAvailable + miniApp.close
    │       └── ExpertSheet.tsx    # startExpert → Redis pub/sub → miniApp.close
    ├── Dockerfile      # node build → nginx (порт 80)
    ├── nginx.conf      # Reverse proxy config (API проксируется через /api/)
    ├── vite.config.ts  # proxy /api → localhost:8090, host:true для tunnel
    └── package.json
```

## Dev Workflow

### Локальная разработка (90% времени)

```bash
cd mini_app/frontend && npm run dev   # → localhost:5173
# mockTelegramEnv подставляет фейковый user/initData
# Vite proxy: /api/* → localhost:8090 (Docker mini-app-api)
# Chrome DevTools — console, network, breakpoints
# Eruda кнопка в dev mode
```

### Тест в Telegram (smoke test)

```bash
ssh -R 8091:127.0.0.1:5173 vps -N
# miniapp.awdawdawd.space → Vite dev server (hot reload)
# Eruda консоль прямо в Mini App
# Remote logging: /api/log → docker logs dev-mini-app-api-1
```

### 3 уровня дебага

| Уровень | Инструмент | Когда |
|---------|-----------|-------|
| Браузер | Chrome DevTools | Локальная разработка, mock env |
| Telegram | Eruda (автоматически в dev) | Smoke test через tunnel |
| После закрытия | Remote logging `/api/log` | Отлов ошибок после закрытия Mini App |

### Telegram Test Environment (HTTP без tunnel)

Для тестирования с реальным initData без VPS/tunnel:

1. **Создать аккаунт в Test DC:**
   - iOS: Settings → 10 быстрых тапов на версию → "Switch to Test DC"
   - Android: Settings → 10 тапов на версию → "Enable Test Backend"
   - Desktop: Settings → Alt + Shift + клик "Add Account" → test server

2. **Создать тестового бота:**
   - В Test DC написать @BotFather → /newbot
   - Сохранить токен в `.env.test` как `TELEGRAM_BOT_TOKEN_TEST`

3. **Настроить Mini App URL:**
   - @BotFather → /newapp (или /setmenubutton)
   - URL: `http://<WSL-IP>:5173` (HTTP разрешён в test DC)
   - Узнать IP: `hostname -I | awk '{print $1}'`

4. **Запустить:**
   ```bash
   docker compose --profile bot up -d mini-app-api
   cd mini_app/frontend && npm run dev  # host: true уже в vite.config.ts
   # Открыть мини-ап в Telegram Test DC
   ```

| Среда | URL | HTTPS | initData |
|-------|-----|-------|----------|
| Браузер (mock) | localhost:5173 | Нет | Фейковый |
| Test DC | http://WSL-IP:5173 | Нет | Реальный |
| Production | miniapp.awdawdawd.space | Да | Реальный |

## Docker-сервисы

- `mini-app-api` — FastAPI, порт **8090** (dev: 127.0.0.1:8090)
  - Env: `REDIS_URL`, `BOT_USERNAME` + стандартные
- `mini-app-frontend` — nginx, порт **80** (dev: 127.0.0.1:8091)
- Профили: `bot`, `full`
- Frontend зависит от API (condition: service_healthy)

## Привязка к боту

`telegram_bot/config.py` → `BotConfig.mini_app_url` (env: `MINI_APP_URL`)

При старте бота:
- Если `mini_app_url` задан → устанавливает `MenuButtonWebApp` с кнопкой "Открыть"
- Если пуст → `MenuButtonCommands` (стандартное меню команд)

## Cloudflare Tunnel

Mini app требует HTTPS для Telegram WebApp API.

### Prod (named tunnel — фиксированный URL)

VPS: `miniapp.awdawdawd.space` → named tunnel `rag-mini-app` → `http://localhost:8091`

### Dev (SSH reverse tunnel через VPS)

```bash
ssh -R 8091:127.0.0.1:8091 vps -N
# miniapp.awdawdawd.space → cloudflared → VPS:8091 → SSH → localhost:8091
```

### Диагностика

| Симптом | Причина | Решение |
|---------|---------|---------|
| ERR_NAME_NOT_RESOLVED | Туннель не запущен | SSH tunnel или перезапустить cloudflared |
| Mini app не открывается | `MINI_APP_URL` не обновлён | Обновить .env + перезапустить бота |
| 502 Bad Gateway | mini-app-frontend не запущен | `docker compose --profile bot up -d` |
| API ошибки | mini-app-api не healthy | `docker compose logs mini-app-api` |
| CSS пустые/белый экран | `themeParams.mount()` не вызван | Проверить bootstrap.ts порядок инициализации |
| `UnknownEnvError` в dev | `mockEnv` не поставил `TelegramWebviewProxy` | Убедиться что mockEnv вызывается без `isTMA()` guard |
| `UnknownEnvError` после reload | sessionStorage есть, window globals сброшены | mockEnv должен всегда переустанавливать mock |
| remote port forwarding failed | Порт занят или GatewayPorts off | Остановить mini-app на VPS, проверить sshd_config |

## Expert Start Flow (Redis Pub/Sub)

```
ExpertSheet → startExpert(userId, expertId, text, queryId)
  → POST /api/start-expert
    → Redis SET miniapp:q:{uuid} (TTL 300s, payload: expert_id, message, user_id, query_id)
    → Redis PUBLISH miniapp:start {uuid, user_id, query_id}
    → response: { status: "ok", expert_name }
  → miniApp.close.ifAvailable()
  → Бот (_miniapp_subscriber_loop):
    → Redis SUBSCRIBE miniapp:start
    → _process_miniapp_start(chat_id, uuid)
    → Redis GETDEL miniapp:q:{uuid} → payload
    → TopicManager.get_or_create → forum topic (с retry при stale cache)
    → Echo вопрос в тред → RAG pipeline → ответ в тред
```

**Важно:** `mini-app-api` и бот — **отдельные Docker-контейнеры**. Связь через **Redis** (payload с TTL 300s + pub/sub для мгновенной доставки).

**Почему не `answerWebAppQuery`:** не поддерживает `message_thread_id` → дублирует сообщение в General chat при forum topics.

**Почему не `openTelegramLink`:** deep link к своему боту (`t.me/bot?start=`) молча игнорируется Telegram-клиентом из Mini App.

### Redis ключи

```
miniapp:q:{uuid}                      → json payload (TTL 300s, одноразовый GETDEL)
miniapp:start                         → pub/sub канал (uuid, user_id, query_id)
topic:{chat_id}:{expert_id}           → thread_id (TTL 30 дней)
topic_rev:{chat_id}:{thread_id}       → expert_id (reverse lookup)
```

### Edge cases

| Кейс | Поведение |
|------|-----------|
| UUID expired/replay | "Ссылка устарела" (GETDEL вернул null) |
| Forum topic уже есть | TopicManager.get_or_create → существующий |
| Stale topic cache (удалён в Telegram) | TelegramBadRequest → invalidate_topic() → пересоздание |
| Topics не включены в чате | TelegramBadRequest → "Не удалось создать тему" |
| EXPERT_TOPICS_ENABLED=false | Pub/sub игнорируется, обычный /start |
| userId null (initData пуст) | alert + remoteLog, не отправляет запрос |
| Pub/sub subscriber упал | Автоматический reconnect в цикле |

### Env переменные

| Var | Описание |
|-----|----------|
| `REDIS_URL` | Redis для payload + pub/sub (compose: mini-app-api + bot) |
| `EXPERT_TOPICS_ENABLED` | Feature flag для TopicManager + pub/sub handler |
| `MINI_APP_URL` | URL Mini App для MenuButtonWebApp |

## Тесты

### Frontend (Vitest, 16 файлов, 53 теста)

```bash
cd mini_app/frontend && npm test                    # Все тесты
cd mini_app/frontend && npm run build               # TS build check
```

Моки SDK в `test-setup.ts`:
- Глобальный `vi.mock("@tma.js/sdk-react")` — init, initData, themeParams, viewport, swipeBehavior, openTelegramLink, miniApp.close, sendData
- Глобальный `vi.mock("@tma.js/bridge")` — mockTelegramEnv, isTMA
- `vi.mock("eruda")` — заглушка dev-инструмента

Для `main.test.tsx` используется `vi.doMock` (mock bootstrap, не реальный SDK).
Для `bootstrap.test.ts` используется `vi.useFakeTimers()` + `vi.clearAllMocks()` в beforeEach.

### Backend (pytest)

```bash
pytest tests/unit/mini_app/test_chat.py -v           # API endpoint tests (5)
pytest tests/unit/mini_app/test_start_expert.py -v   # Pydantic model tests (4)
pytest tests/unit/services/test_topic_manager.py -v  # TopicManager service (7)
pytest tests/unit/test_bot_deeplink.py -v            # Bot deep link handler (8)
```

## Конфигурация контента

`telegram_bot/config/mini_app.yaml` — вопросы (questions) и эксперты (experts) для UI.
