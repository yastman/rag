---
paths: "mini_app/**/*.py, mini_app/**/*.tsx, mini_app/**/*.ts, telegram_bot/config/mini_app.yaml, telegram_bot/services/topic_service.py, telegram_bot/services/topic_manager.py, telegram_bot/services/draft_streamer.py, .env"
---

# Mini App (Telegram Web App)

## SDK

**@telegram-apps/sdk-react v3** — официальный React SDK для Telegram Mini Apps. Заменяет raw `window.Telegram.WebApp`.

```typescript
// main.tsx — порядок инициализации КРИТИЧЕН:
setupMockEnv();              // 1. Mock env (только в браузере, до SDK)
init();                      // 2. SDK init
mountThemeParamsSync();       // 3. Mount theme params
bindThemeParamsCssVars();     // 4. Bind --tg-theme-* CSS vars
```

### Ключевые API

| Функция | Паттерн | Назначение |
|---------|---------|------------|
| `openTelegramLink` | `.isAvailable()` + try/catch + `location.href` fallback | Deep link navigation |
| `sendData` | `.ifAvailable(text)` | Отправка данных боту (закрывает Mini App) |
| `closeMiniApp` | `.ifAvailable()` | Закрытие Mini App |
| `initData.user()` | Прямой вызов | `{ id, firstName, lastName, username }` |
| `isTMA()` | Sync проверка | `true` в Telegram, `false` в браузере |
| `mockTelegramEnv` | `({ launchParams: URLSearchParams })` | Фейк env для локальной разработки |
| `mountThemeParamsSync` | Вызов после `init()` | Загрузка theme params |
| `bindThemeParamsCssVars` | Вызов после mount | Привязка `--tg-theme-*` CSS переменных |

### Anti-patterns

- **НЕ** `window.Telegram.WebApp.*` — используй SDK хуки
- **НЕ** `openTelegramLink(url)` без `.isAvailable()` guard — платформенные баги
- **НЕ** забывай `mountThemeParamsSync()` + `bindThemeParamsCssVars()` — без них CSS переменные пустые
- **НЕ** `<script src="telegram-web-app.js">` в index.html — SDK v3 сам управляет

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
    │   ├── main.tsx        # SDK init, mockEnv, Eruda, theme CSS vars
    │   ├── mockEnv.ts      # mockTelegramEnv для dev в браузере
    │   ├── App.tsx         # Routes: /, /question/:id, /expert/:id
    │   ├── api.ts          # fetchConfig(), startExpert(), submitPhone(), remoteLog()
    │   ├── types.ts        # Prompt, Question, Expert, AppConfig
    │   └── pages/
    │       ├── HomePage.tsx
    │       ├── QuestionSheet.tsx  # sendData.ifAvailable + closeMiniApp
    │       └── ExpertSheet.tsx    # openTelegramLink + fallback + remoteLog
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
| После закрытия | Remote logging `/api/log` | Отлов ошибок openTelegramLink |

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
| CSS пустые/белый экран | `mountThemeParamsSync` не вызван | Проверить main.tsx порядок инициализации |
| remote port forwarding failed | Порт занят или GatewayPorts off | Остановить mini-app на VPS, проверить sshd_config |

## Expert Start Flow (Deep Link)

```
ExpertSheet → startExpert(userId, expertId, text)
  → POST /api/start-expert → Redis SET miniapp:q:{uuid} (TTL 300s)
  → response: { start_link }
  → SDK openTelegramLink.isAvailable() ? openTelegramLink(start_link) : location.href
    → catch → fallback: location.href = start_link
  → Mini App закрывается
  → Бот: /start q_{uuid} → Redis GETDEL → TopicManager → RAG
```

**Важно:** `mini-app-api` и бот — **отдельные Docker-контейнеры**. Связь через **Redis** (одноразовый payload с TTL 300s).

### Redis ключи

```
miniapp:q:{uuid}                      → json payload (TTL 300s, одноразовый GETDEL)
topic:{chat_id}:{expert_id}           → thread_id (TTL 30 дней)
topic_rev:{chat_id}:{thread_id}       → expert_id (reverse lookup)
```

### Edge cases

| Кейс | Поведение |
|------|-----------|
| UUID expired/replay | "Ссылка устарела" |
| Forum topic уже есть | TopicManager.get_or_create → существующий |
| Topics не включены в чате | TelegramBadRequest → "Не удалось создать тему" |
| BOT_USERNAME не задан | API → HTTP 500 |
| EXPERT_TOPICS_ENABLED=false | Deep link игнорируется, обычный /start |
| openTelegramLink throws | remoteLog + fallback location.href |
| userId null (initData пуст) | alert + remoteLog, не отправляет запрос |

### Env переменные

| Var | Описание |
|-----|----------|
| `BOT_USERNAME` | Username бота для deep link (compose: mini-app-api) |
| `EXPERT_TOPICS_ENABLED` | Feature flag для TopicManager + deep link handler |
| `MINI_APP_URL` | URL Mini App для MenuButtonWebApp |

## Тесты

### Frontend (Vitest, 14 файлов, 51 тест)

```bash
cd mini_app/frontend && npm test                    # Все тесты
cd mini_app/frontend && npm run build               # TS build check
```

Моки SDK в `test-setup.ts` — глобальный `vi.mock("@telegram-apps/sdk-react")`.
Для `main.test.tsx` используется `vi.doMock` с `vi.resetModules()`.

### Backend (pytest)

```bash
pytest tests/unit/mini_app/test_chat.py -v           # API endpoint tests (5)
pytest tests/unit/mini_app/test_start_expert.py -v   # Pydantic model tests (4)
pytest tests/unit/services/test_topic_manager.py -v  # TopicManager service (7)
pytest tests/unit/test_bot_deeplink.py -v            # Bot deep link handler (8)
```

## Конфигурация контента

`telegram_bot/config/mini_app.yaml` — вопросы (questions) и эксперты (experts) для UI.
