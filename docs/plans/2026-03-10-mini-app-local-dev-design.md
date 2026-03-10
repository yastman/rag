# Mini App: Local Dev + SDK Migration + Production Hardening

## Scope

Целевой scope — **C** (test environment + SDK миграция + hardening), реализуемый поэтапно: **A → B/C**.

## Фаза 1: Telegram Test Environment + локальный HTTP flow

### Цель

Убрать зависимость от VPS/SSH tunnel/cloudflared для dev-тестирования в Telegram.

### Что делаем

1. Создать аккаунт в **Telegram Test DC** (мобильный клиент → 10 тапов на версию → test server)
2. Создать тестового бота через **BotFather в test DC**
3. Указать Mini App URL = `http://<WSL-IP>:5173` (test DC разрешает HTTP и IP)
4. Vite dev server с `--host` — доступен по IP из Telegram Desktop (test env)
5. Документировать процесс в `.claude/rules/mini-app.md`

### Dev workflow после настройки

```bash
# 1. API бэкенд (Docker)
docker compose --profile bot up -d mini-app-api

# 2. Vite dev server
cd mini_app/frontend && npm run dev --host

# 3. Открыть мини-ап в Telegram test DC — http://WSL-IP:5173, без tunnel
```

### Ограничения

- Test DC = отдельный аккаунт, отдельный бот, отдельная сессия
- На мобильных тоже работает, но нужен отдельный вход
- Production бот остаётся на production DC с HTTPS

## Фаза 2: SDK миграция + bootstrap refactor + hardening

### SDK миграция

`@telegram-apps/sdk-react` → `@tma.js/sdk-react`

- Ставить **только** `@tma.js/sdk-react` (реэкспортит core SDK, дублировать `@tma.js/sdk` не нужно)
- Official migration guide: docs.telegram-mini-apps.com/packages/tma-js-sdk/migrate-from-telegram-apps
- Обновить все импорты + test mocks

### Структура файлов

```
src/
├── main.tsx             # await initApp() → render(<TelegramGate>)
├── bootstrap.ts         # orchestrator: mock → detect → init → viewport → swipe
├── mockEnv.ts           # dev-only, отдельный файл (независимый concern)
├── guards/
│   └── TelegramGate.tsx # isTelegram ? <App/> : <OpenInTelegram/>
├── App.tsx
└── pages/
    └── ...
```

### Роли файлов

**`main.tsx`** — "тупой" entry point:
```ts
const { isTelegram } = await initApp();

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <TelegramGate isTelegram={isTelegram}>
      <App />
    </TelegramGate>
  </ErrorBoundary>
);
```

**`bootstrap.ts`** — единый orchestration point для platform init:
```ts
import {
  init,
  initData,
  themeParams,
  viewport,
  swipeBehavior,
} from "@tma.js/sdk-react";
import { isTMA } from "@tma.js/bridge";
import { setupMockEnv } from "./mockEnv";

export type AppBootstrapResult = {
  isTelegram: boolean;
};

export async function initApp(): Promise<AppBootstrapResult> {
  const isDev = import.meta.env.DEV;

  // 1. Mock env (dev + browser only)
  if (isDev) {
    setupMockEnv();
  }

  // 2. Detect environment ("complete" mode — более надёжный чем sync)
  const isTelegram = isDev ? true : await isTMA("complete");

  if (!isTelegram) {
    return { isTelegram: false };
  }

  // 3. SDK init
  init();

  // 4. Restore initData (user, auth_date, hash)
  initData.restore();

  // 5. Theme params (mount → bind CSS vars)
  themeParams.mount();
  themeParams.bindCssVars();

  // 6. Viewport (async mount → bind CSS vars)
  if (viewport.mount.isAvailable()) {
    await viewport.mount();
    viewport.bindCssVars();
  }

  // 7. Swipe protection (mount → disable vertical)
  if (swipeBehavior.isSupported()) {
    swipeBehavior.mount();
    swipeBehavior.disableVerticalSwipe();
  }

  // 8. Eruda (dev only)
  if (isDev) {
    import("eruda").then((e) => e.default.init());
  }

  return { isTelegram: true };
}
```

**`TelegramGate.tsx`** — UX-ветка:
- `isTelegram === true` → рендерит children
- `isTelegram === false && !DEV` → страница "Откройте в Telegram" с deep link
- `isTelegram === false && DEV` → рендерит children (mock env)

**`mockEnv.ts`** — без изменений в контракте, обновить импорты на `@tma.js/bridge`.

### Ключевые отличия `@tma.js` lifecycle от `@telegram-apps/sdk`

| Аспект | `@telegram-apps/sdk` (текущий) | `@tma.js/sdk-react` (целевой) |
|--------|-------------------------------|-------------------------------|
| Theme params | `mountThemeParamsSync()` + `bindThemeParamsCssVars()` | `themeParams.mount()` + `themeParams.bindCssVars()` |
| Swipe | Не было | `swipeBehavior.mount()` + `swipeBehavior.disableVerticalSwipe()` |
| Viewport | Не было | `await viewport.mount()` + `viewport.bindCssVars()` |
| Environment detect | `isTMA()` (sync) | `await isTMA("complete")` (async, надёжнее) |
| `ifAvailable()` return | `result \| undefined` | Tuple: `[false]` или `[true, result]` |
| `requestContact` fields | camelCase | snake_case |

### Порядок реализации (7 шагов)

| # | Задача | Файлы |
|---|--------|-------|
| 1 | Telegram Test Environment setup | docs, .env.test |
| 2 | Тестовый бот + локальный HTTP flow | BotFather (test DC), vite.config.ts |
| 3 | `@telegram-apps/sdk-react` → `@tma.js/sdk-react` | package.json, все импорты, test mocks |
| 4 | Bootstrap refactor: `main.tsx` → `bootstrap.ts` + `main.tsx` | bootstrap.ts, main.tsx |
| 5 | Viewport mount | bootstrap.ts |
| 6 | Swipe protection | bootstrap.ts |
| 7 | TelegramGate fallback page | guards/TelegramGate.tsx |

## Что НЕ делаем

- Back button management (нет навигации назад в текущем UX)
- Haptics (не нужны)
- Analytics hooks on launch (Langfuse на бэкенде)
- `miniApp.ready()` (кандидат на будущее, не блокер)
- Переход на A-структуру (bootstrap < 100 строк)

## Когда B → A

Переходить с одного `bootstrap.ts` на модульную структуру `bootstrap/` только если:
- bootstrap > 100–150 строк
- появились отдельные async ветки инициализации
- нужна unit-тестируемость отдельных шагов
- добавляются back button, closing behavior, haptics, navigation, analytics hooks
