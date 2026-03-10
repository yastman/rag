# Mini App Local Dev + SDK Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Убрать зависимость от VPS/tunnel для dev-тестирования, мигрировать на @tma.js/sdk-react, добавить viewport/swipe/TelegramGate.

**Architecture:** Один bootstrap.ts orchestrator, mockEnv.ts отдельно, TelegramGate.tsx как guard-компонент. main.tsx — тупой entry point.

**Tech Stack:** @tma.js/sdk-react, Vite, React 18, Vitest, cloudflared (test env)

**Design doc:** `docs/plans/2026-03-10-mini-app-local-dev-design.md`

---

## Phase 1: Telegram Test Environment

### Task 1: Документация Test Environment setup

**Files:**
- Modify: `.claude/rules/mini-app.md` (секция Dev Workflow)

**Step 1: Добавить секцию Test Environment в правила**

В `.claude/rules/mini-app.md` после секции "Dev Workflow" добавить:

```markdown
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
```

**Step 2: Commit**

```bash
git add .claude/rules/mini-app.md
git commit -m "docs(mini-app): add Telegram Test Environment setup guide"
```

---

## Phase 2: SDK Migration + Bootstrap Refactor

### Task 2: Заменить @telegram-apps/sdk-react на @tma.js/sdk-react

**Files:**
- Modify: `mini_app/frontend/package.json`

**Step 1: Удалить старый SDK, установить новый**

```bash
cd mini_app/frontend
npm remove @telegram-apps/sdk-react
npm install @tma.js/sdk-react
```

**Step 2: Проверить что установилось**

```bash
cd mini_app/frontend && cat node_modules/@tma.js/sdk-react/package.json | head -5
```

Expected: name = "@tma.js/sdk-react"

**Step 3: Commit**

```bash
git add mini_app/frontend/package.json mini_app/frontend/package-lock.json
git commit -m "feat(mini-app): replace @telegram-apps/sdk-react with @tma.js/sdk-react"
```

---

### Task 3: Создать bootstrap.ts с тестами

**Files:**
- Create: `mini_app/frontend/src/bootstrap.ts`
- Create: `mini_app/frontend/src/__tests__/bootstrap.test.ts`

**Step 1: Написать тест на bootstrap**

```typescript
// mini_app/frontend/src/__tests__/bootstrap.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";

// Мокаем модули до импорта
const mockSetupMockEnv = vi.fn();
const mockInit = vi.fn();
const mockRestore = vi.fn();
const mockThemeMount = vi.fn();
const mockThemeBindCss = vi.fn();
const mockViewportMount = vi.fn(() => Promise.resolve());
const mockViewportBindCss = vi.fn();
const mockSwipeMount = vi.fn();
const mockSwipeDisable = vi.fn();

vi.mock("@tma.js/sdk-react", () => ({
  init: mockInit,
  initData: { restore: mockRestore },
  themeParams: {
    mount: mockThemeMount,
    bindCssVars: mockThemeBindCss,
  },
  viewport: {
    mount: Object.assign(mockViewportMount, {
      isAvailable: vi.fn(() => true),
    }),
    bindCssVars: mockViewportBindCss,
  },
  swipeBehavior: {
    isSupported: vi.fn(() => true),
    mount: mockSwipeMount,
    disableVerticalSwipe: mockSwipeDisable,
  },
}));

vi.mock("@tma.js/bridge", () => ({
  isTMA: vi.fn(() => Promise.resolve(true)),
}));

vi.mock("../mockEnv", () => ({
  setupMockEnv: mockSetupMockEnv,
}));

vi.mock("eruda", () => ({ default: { init: vi.fn() } }));

describe("bootstrap", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls init sequence in correct order", async () => {
    const { initApp } = await import("../bootstrap");
    const result = await initApp();

    expect(mockInit).toHaveBeenCalled();
    expect(mockRestore).toHaveBeenCalled();
    expect(mockThemeMount).toHaveBeenCalled();
    expect(mockThemeBindCss).toHaveBeenCalled();
    expect(result.isTelegram).toBe(true);
  });

  it("mounts viewport when available", async () => {
    const { initApp } = await import("../bootstrap");
    await initApp();

    expect(mockViewportMount).toHaveBeenCalled();
    expect(mockViewportBindCss).toHaveBeenCalled();
  });

  it("enables swipe protection when supported", async () => {
    const { initApp } = await import("../bootstrap");
    await initApp();

    expect(mockSwipeMount).toHaveBeenCalled();
    expect(mockSwipeDisable).toHaveBeenCalled();
  });

  it("returns isTelegram=false when not in TMA", async () => {
    const bridge = await import("@tma.js/bridge");
    vi.mocked(bridge.isTMA).mockResolvedValueOnce(false);

    // Нужен resetModules чтобы bootstrap переимпортировался
    vi.resetModules();

    // Переопределяем моки после resetModules
    vi.doMock("@tma.js/bridge", () => ({
      isTMA: vi.fn(() => Promise.resolve(false)),
    }));
    vi.doMock("@tma.js/sdk-react", () => ({
      init: mockInit,
      initData: { restore: mockRestore },
      themeParams: { mount: mockThemeMount, bindCssVars: mockThemeBindCss },
      viewport: {
        mount: Object.assign(mockViewportMount, { isAvailable: vi.fn(() => true) }),
        bindCssVars: mockViewportBindCss,
      },
      swipeBehavior: {
        isSupported: vi.fn(() => true),
        mount: mockSwipeMount,
        disableVerticalSwipe: mockSwipeDisable,
      },
    }));
    vi.doMock("../mockEnv", () => ({ setupMockEnv: mockSetupMockEnv }));
    vi.doMock("eruda", () => ({ default: { init: vi.fn() } }));

    const { initApp } = await import("../bootstrap");
    const result = await initApp();

    expect(result.isTelegram).toBe(false);
    expect(mockInit).not.toHaveBeenCalled();
  });
});
```

**Step 2: Запустить тест — должен упасть (bootstrap.ts не существует)**

```bash
cd mini_app/frontend && npx vitest run src/__tests__/bootstrap.test.ts
```

Expected: FAIL — module not found

**Step 3: Написать bootstrap.ts**

```typescript
// mini_app/frontend/src/bootstrap.ts
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

  // 2. Detect environment
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

**Step 4: Запустить тест — должен пройти**

```bash
cd mini_app/frontend && npx vitest run src/__tests__/bootstrap.test.ts
```

Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add mini_app/frontend/src/bootstrap.ts mini_app/frontend/src/__tests__/bootstrap.test.ts
git commit -m "feat(mini-app): add bootstrap.ts with TMA lifecycle init"
```

---

### Task 4: Создать TelegramGate с тестами

**Files:**
- Create: `mini_app/frontend/src/guards/TelegramGate.tsx`
- Create: `mini_app/frontend/src/guards/__tests__/TelegramGate.test.tsx`

**Step 1: Написать тест**

```typescript
// mini_app/frontend/src/guards/__tests__/TelegramGate.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TelegramGate } from "../TelegramGate";

describe("TelegramGate", () => {
  it("renders children when isTelegram=true", () => {
    render(
      <TelegramGate isTelegram={true}>
        <div>App Content</div>
      </TelegramGate>,
    );
    expect(screen.getByText("App Content")).toBeInTheDocument();
  });

  it("renders children in dev mode even when isTelegram=false", () => {
    const originalDev = import.meta.env.DEV;
    // В тестах DEV = true по умолчанию
    render(
      <TelegramGate isTelegram={false}>
        <div>App Content</div>
      </TelegramGate>,
    );
    expect(screen.getByText("App Content")).toBeInTheDocument();
  });

  it("renders fallback when isTelegram=false and not dev", () => {
    // Мокаем production mode
    const original = import.meta.env.DEV;
    import.meta.env.DEV = false;

    render(
      <TelegramGate isTelegram={false}>
        <div>App Content</div>
      </TelegramGate>,
    );

    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
    expect(screen.getByText(/Telegram/i)).toBeInTheDocument();

    import.meta.env.DEV = original;
  });
});
```

**Step 2: Запустить тест — должен упасть**

```bash
cd mini_app/frontend && npx vitest run src/guards/__tests__/TelegramGate.test.tsx
```

Expected: FAIL — module not found

**Step 3: Написать TelegramGate**

```typescript
// mini_app/frontend/src/guards/TelegramGate.tsx
import type { ReactNode } from "react";

interface Props {
  isTelegram: boolean;
  children: ReactNode;
}

export function TelegramGate({ isTelegram, children }: Props) {
  // В dev mode всегда показываем app (mockEnv работает)
  if (isTelegram || import.meta.env.DEV) {
    return <>{children}</>;
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: 32,
        fontFamily: "system-ui, sans-serif",
        textAlign: "center",
        background: "#17212b",
        color: "#f5f5f5",
      }}
    >
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>
        Откройте в Telegram
      </h1>
      <p style={{ fontSize: 16, color: "#708499", marginBottom: 24 }}>
        Это приложение работает только внутри Telegram.
      </p>
      <a
        href="https://t.me/FortnoksBot"
        style={{
          display: "inline-block",
          padding: "12px 24px",
          background: "#5288c1",
          color: "#fff",
          borderRadius: 8,
          textDecoration: "none",
          fontSize: 16,
        }}
      >
        Открыть в Telegram
      </a>
    </div>
  );
}
```

**Step 4: Запустить тест — должен пройти**

```bash
cd mini_app/frontend && npx vitest run src/guards/__tests__/TelegramGate.test.tsx
```

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add mini_app/frontend/src/guards/TelegramGate.tsx mini_app/frontend/src/guards/__tests__/TelegramGate.test.tsx
git commit -m "feat(mini-app): add TelegramGate fallback component"
```

---

### Task 5: Обновить mockEnv.ts — миграция импортов

**Files:**
- Modify: `mini_app/frontend/src/mockEnv.ts`

**Step 1: Обновить импорты**

Заменить:
```typescript
import { mockTelegramEnv, isTMA } from "@telegram-apps/sdk-react";
```

На:
```typescript
import { mockTelegramEnv, isTMA } from "@tma.js/bridge";
```

Логика и API `mockTelegramEnv` идентичны — меняется только пакет.

**Step 2: Запустить тесты mockEnv**

```bash
cd mini_app/frontend && npx vitest run src/__tests__/mockEnv.test.ts
```

Expected: PASS (мок в test-setup перехватит)

**Step 3: Commit**

```bash
git add mini_app/frontend/src/mockEnv.ts
git commit -m "refactor(mini-app): migrate mockEnv imports to @tma.js/bridge"
```

---

### Task 6: Обновить страницы — миграция импортов

**Files:**
- Modify: `mini_app/frontend/src/pages/ExpertSheet.tsx`
- Modify: `mini_app/frontend/src/pages/QuestionSheet.tsx`

**Step 1: ExpertSheet.tsx — обновить импорт**

Заменить:
```typescript
import { openTelegramLink, initData } from "@telegram-apps/sdk-react";
```

На:
```typescript
import { openTelegramLink, initData } from "@tma.js/sdk-react";
```

**Step 2: QuestionSheet.tsx — обновить импорт**

Заменить:
```typescript
import { closeMiniApp, sendData } from "@telegram-apps/sdk-react";
```

На:
```typescript
import { closeMiniApp, sendData } from "@tma.js/sdk-react";
```

**Step 3: Commit**

```bash
git add mini_app/frontend/src/pages/ExpertSheet.tsx mini_app/frontend/src/pages/QuestionSheet.tsx
git commit -m "refactor(mini-app): migrate page imports to @tma.js/sdk-react"
```

---

### Task 7: Обновить test-setup и тесты — миграция моков

**Files:**
- Modify: `mini_app/frontend/src/test-setup.ts`
- Modify: `mini_app/frontend/src/__tests__/main.test.tsx`
- Modify: `mini_app/frontend/src/pages/__tests__/ExpertSheet.test.tsx`
- Modify: `mini_app/frontend/src/pages/__tests__/QuestionSheet.test.tsx`
- Modify: `mini_app/frontend/src/__tests__/mockEnv.test.ts`

**Step 1: test-setup.ts — обновить глобальный мок**

Заменить весь блок `vi.mock("@telegram-apps/sdk-react", ...)`:

```typescript
// Mock @tma.js/sdk-react для тестов
vi.mock("@tma.js/sdk-react", () => ({
  init: vi.fn(),
  openTelegramLink: Object.assign(vi.fn(), {
    isAvailable: vi.fn(() => true),
    ifAvailable: vi.fn(),
  }),
  closeMiniApp: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  sendData: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  initData: {
    user: () => ({ id: 99999, firstName: "Test" }),
    restore: vi.fn(),
  },
  themeParams: {
    mount: vi.fn(),
    bindCssVars: vi.fn(),
  },
  viewport: {
    mount: Object.assign(vi.fn(() => Promise.resolve()), {
      isAvailable: vi.fn(() => true),
    }),
    bindCssVars: vi.fn(),
  },
  swipeBehavior: {
    isSupported: vi.fn(() => true),
    mount: vi.fn(),
    disableVerticalSwipe: vi.fn(),
  },
  parseInitData: vi.fn(),
}));

// Mock @tma.js/bridge
vi.mock("@tma.js/bridge", () => ({
  mockTelegramEnv: vi.fn(),
  isTMA: vi.fn(() => false),
}));
```

**Step 2: main.test.tsx — обновить доки на новые пакеты**

Все `'@telegram-apps/sdk-react'` → `'@tma.js/sdk-react'`.
Добавить мок `@tma.js/bridge`.
Обновить мок SDK: убрать `mountThemeParamsSync`/`bindThemeParamsCssVars`, добавить `themeParams`/`viewport`/`swipeBehavior`.

Тест полностью переписывается под новый `main.tsx` (который будет вызывать `initApp()`).

**Step 3: ExpertSheet.test.tsx и QuestionSheet.test.tsx**

Заменить `import * as sdkReact from '@telegram-apps/sdk-react'` на `import * as sdkReact from '@tma.js/sdk-react'`.

**Step 4: mockEnv.test.ts**

Заменить `import * as sdkReact from '@telegram-apps/sdk-react'` на `import * as bridge from '@tma.js/bridge'`.
Обновить мок вызовы соответственно.

**Step 5: Запустить все тесты**

```bash
cd mini_app/frontend && npm test
```

Expected: Все тесты PASS

**Step 6: Commit**

```bash
git add mini_app/frontend/src/test-setup.ts mini_app/frontend/src/__tests__/ mini_app/frontend/src/pages/__tests__/
git commit -m "refactor(mini-app): migrate all test mocks to @tma.js packages"
```

---

### Task 8: Переписать main.tsx на bootstrap + TelegramGate

**Files:**
- Modify: `mini_app/frontend/src/main.tsx`
- Modify: `mini_app/frontend/src/__tests__/main.test.tsx`

**Step 1: Обновить main.test.tsx**

```typescript
// mini_app/frontend/src/__tests__/main.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("main.tsx", () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("calls initApp and renders", async () => {
    const mockRender = vi.fn();
    const mockCreateRoot = vi.fn(() => ({ render: mockRender }));

    vi.doMock("react-dom/client", () => ({ createRoot: mockCreateRoot }));
    vi.doMock("../bootstrap", () => ({
      initApp: vi.fn(() => Promise.resolve({ isTelegram: true })),
    }));
    vi.doMock("../App", () => ({ App: () => null }));
    vi.doMock("../guards/TelegramGate", () => ({
      TelegramGate: ({ children }: { children: React.ReactNode }) => children,
    }));
    vi.doMock("../ErrorBoundary", () => ({
      ErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
    }));

    await import("../main");

    // Ждём async initApp
    await new Promise((r) => setTimeout(r, 0));

    expect(mockCreateRoot).toHaveBeenCalled();
    expect(mockRender).toHaveBeenCalled();
  });
});
```

**Step 2: Переписать main.tsx**

```typescript
// mini_app/frontend/src/main.tsx
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import { TelegramGate } from "./guards/TelegramGate";
import { initApp } from "./bootstrap";

const { isTelegram } = await initApp();

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <TelegramGate isTelegram={isTelegram}>
      <App />
    </TelegramGate>
  </ErrorBoundary>,
);
```

**Step 3: Запустить все тесты**

```bash
cd mini_app/frontend && npm test
```

Expected: Все тесты PASS

**Step 4: Проверить build**

```bash
cd mini_app/frontend && npm run build
```

Expected: tsc + vite build OK

**Step 5: Commit**

```bash
git add mini_app/frontend/src/main.tsx mini_app/frontend/src/__tests__/main.test.tsx
git commit -m "refactor(mini-app): rewrite main.tsx to use bootstrap + TelegramGate"
```

---

### Task 9: Обновить правила .claude/rules/mini-app.md

**Files:**
- Modify: `.claude/rules/mini-app.md`

**Step 1: Обновить секцию SDK**

Заменить `@telegram-apps/sdk-react` на `@tma.js/sdk-react` во всех упоминаниях.
Обновить порядок инициализации на новый (bootstrap.ts).
Добавить viewport и swipeBehavior в таблицу API.

**Step 2: Обновить секцию Архитектура**

Добавить `bootstrap.ts` и `guards/TelegramGate.tsx` в дерево файлов.

**Step 3: Commit**

```bash
git add .claude/rules/mini-app.md
git commit -m "docs(mini-app): update rules for @tma.js/sdk-react migration"
```

---

### Task 10: Финальная верификация

**Step 1: Все тесты**

```bash
cd mini_app/frontend && npm test
```

Expected: Все тесты PASS (должно быть ~55+ тестов)

**Step 2: Build check**

```bash
cd mini_app/frontend && npm run build
```

Expected: OK

**Step 3: Backend checks (не сломали ли что-то)**

```bash
make check
```

Expected: OK (mini_app frontend не влияет на Python lint/mypy)

**Step 4: Dev server smoke test**

```bash
cd mini_app/frontend && npx vite --host &
sleep 3
# Открыть http://localhost:5173 — должен работать с mock env
kill %1
```

**Step 5: Commit финального состояния (если есть незакоммиченное)**

```bash
git status
# Если чисто — ничего не делать
```
