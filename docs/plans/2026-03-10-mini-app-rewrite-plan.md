# Mini App Frontend Rewrite — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Переписать mini_app/frontend на `@telegram-apps/sdk-react` v3 с mockTelegramEnv, Eruda и рабочим openTelegramLink.

**Architecture:** Заменяем raw `window.Telegram.WebApp` на SDK v3 хуки. Добавляем mock env для локальной разработки в браузере. Компоненты (BottomSheet, PromptRow, etc) сохраняются без изменений.

**Tech Stack:** React 18, @telegram-apps/sdk-react v3, Vite 5, Vitest, Eruda

**Design doc:** `docs/plans/2026-03-10-mini-app-rewrite-design.md`

---

### Task 1: Обновить зависимости

**Files:**
- Modify: `mini_app/frontend/package.json`

**Step 1: Обновить пакеты**

```bash
cd mini_app/frontend
npm uninstall @telegram-apps/sdk @telegram-apps/telegram-ui
npm install @telegram-apps/sdk-react@^3.0.0
npm install --save-dev eruda @types/eruda
```

> `@telegram-apps/sdk-react` v3 полностью реэкспортирует `@telegram-apps/sdk` — отдельно ставить не нужно.
> `@telegram-apps/telegram-ui` не используется в коде — удаляем.

**Step 2: Проверить package.json**

```bash
cat package.json | grep -E "telegram-apps|eruda"
```

Expected: `@telegram-apps/sdk-react: ^3.x`, `eruda` в devDependencies. Нет `@telegram-apps/sdk` или `@telegram-apps/telegram-ui`.

**Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "feat(mini-app): upgrade to @telegram-apps/sdk-react v3, add eruda"
```

---

### Task 2: Rewrite main.tsx — SDK init, mockTelegramEnv, Eruda

**Files:**
- Rewrite: `mini_app/frontend/src/main.tsx`
- Create: `mini_app/frontend/src/mockEnv.ts`

**Docs:** https://docs.telegram-mini-apps.com/packages/telegram-apps-sdk-react/3-x

**Step 1: Создать mockEnv.ts**

```typescript
// mini_app/frontend/src/mockEnv.ts
import { mockTelegramEnv, isTMA, parseInitData } from "@telegram-apps/sdk-react";

/**
 * Мок Telegram окружения для разработки в браузере.
 * В Telegram (isTMA=true) — ничего не делает.
 * В браузере — подставляет фейковые initData.
 */
export function setupMockEnv(): void {
  if (isTMA("simple")) return;

  const initDataRaw = new URLSearchParams([
    [
      "user",
      JSON.stringify({
        id: 99999999,
        first_name: "Dev",
        last_name: "User",
        username: "dev_user",
        language_code: "ru",
        is_premium: false,
      }),
    ],
    ["hash", "mock_hash_for_dev"],
    ["auth_date", String(Math.floor(Date.now() / 1000))],
  ]).toString();

  mockTelegramEnv({
    themeParams: {
      accentTextColor: "#6ab2f2",
      bgColor: "#17212b",
      buttonColor: "#5288c1",
      buttonTextColor: "#ffffff",
      destructiveTextColor: "#ec3942",
      headerBgColor: "#17212b",
      hintColor: "#708499",
      linkColor: "#6ab3f3",
      sectionBgColor: "#17212b",
      sectionHeaderTextColor: "#6ab3f3",
      secondaryBgColor: "#232e3c",
      subtitleTextColor: "#708499",
      textColor: "#f5f5f5",
    },
    initData: parseInitData(initDataRaw),
    initDataRaw,
    version: "8",
    platform: "tdesktop",
  });

  console.log("[mockEnv] Telegram environment mocked for browser dev");
}
```

**Step 2: Переписать main.tsx**

```typescript
// mini_app/frontend/src/main.tsx
import { createRoot } from "react-dom/client";
import { ErrorBoundary } from "./ErrorBoundary";
import { setupMockEnv } from "./mockEnv";

// Mock env BEFORE any SDK calls — only activates in browser
setupMockEnv();

// Init Eruda in development
if (import.meta.env.DEV) {
  import("eruda").then(({ default: eruda }) => eruda.init());
}

// SDK init
import { init } from "@telegram-apps/sdk-react";
init();

// Render
import { App } from "./App";
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
```

**Step 3: Убрать `<script src="telegram-web-app.js">` из index.html**

SDK v3 сам инжектирует скрипт. Удалить строку из `mini_app/frontend/index.html`:

```html
<!-- УДАЛИТЬ ЭТУ СТРОКУ: -->
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```

**Step 4: Запустить dev server и проверить в браузере**

```bash
cd mini_app/frontend && npm run dev
```

Expected: Открыть http://localhost:5173 → консоль показывает `[mockEnv] Telegram environment mocked for browser dev` + Eruda кнопка видна.

**Step 5: Commit**

```bash
git add mini_app/frontend/src/main.tsx mini_app/frontend/src/mockEnv.ts mini_app/frontend/index.html
git commit -m "feat(mini-app): SDK v3 init, mockTelegramEnv, Eruda"
```

---

### Task 3: Убрать global Window.Telegram types, обновить types.ts

**Files:**
- Modify: `mini_app/frontend/src/types.ts`

**Step 1: Удалить блок `declare global` из types.ts**

SDK v3 предоставляет свои типы. Убираем кастомное определение `Window.Telegram`.

Оставляем только:

```typescript
// mini_app/frontend/src/types.ts
export interface Prompt {
  emoji: string;
  text: string;
}

export interface Question {
  id: string;
  emoji: string;
  title: string;
  description: string;
  prompts: Prompt[];
}

export interface Expert {
  id: string;
  emoji: string;
  name: string;
  description: string;
  system_prompt_key: string;
  cta_text: string;
  cta_source: string;
  prompts: Prompt[];
}

export interface AppConfig {
  questions: Question[];
  experts: Expert[];
}
```

**Step 2: Commit**

```bash
git add mini_app/frontend/src/types.ts
git commit -m "refactor(mini-app): remove custom Window.Telegram types (SDK v3 provides its own)"
```

---

### Task 4: Rewrite ExpertSheet — SDK openTelegramLink

**Files:**
- Rewrite: `mini_app/frontend/src/pages/ExpertSheet.tsx`
- Modify: `mini_app/frontend/src/pages/__tests__/ExpertSheet.test.tsx`

**Docs:** SDK `openTelegramLink` — https://docs.telegram-mini-apps.com/packages/tma-js-sdk/features/links

**Step 1: Переписать ExpertSheet.tsx**

```typescript
// mini_app/frontend/src/pages/ExpertSheet.tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { openTelegramLink, initData } from "@telegram-apps/sdk-react";
import { fetchConfig, remoteLog, startExpert } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { ChatInput } from "../components/ChatInput";
import { PromptRow } from "../components/PromptRow";
import type { Expert } from "../types";

export function ExpertSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [expert, setExpert] = useState<Expert | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchConfig().then((c) => {
      setExpert(c.experts.find((e: Expert) => e.id === id) ?? null);
    });
  }, [id]);

  if (!expert) return null;

  const user = initData.user();
  const userId = user?.id;

  const handleStart = async (text: string) => {
    remoteLog("info", "handleStart", { userId, id, text });

    if (!userId) {
      remoteLog("error", "userId undefined — initData.user() is null");
      alert("Ошибка: не удалось определить пользователя.");
      return;
    }
    if (!id || loading) return;
    setLoading(true);

    try {
      const data = await startExpert(userId, id, text);
      remoteLog("info", "startExpert OK", { start_link: data.start_link });

      try {
        openTelegramLink(data.start_link);
      } catch (e) {
        remoteLog("warn", "openTelegramLink failed, fallback", { error: String(e) });
        window.location.href = data.start_link;
      }
    } catch (err) {
      remoteLog("error", "startExpert failed", { error: String(err) });
      setLoading(false);
    }
  };

  return (
    <BottomSheet
      emoji={expert.emoji}
      title={expert.name}
      description={expert.description}
      onClose={() => navigate("/")}
    >
      {expert.prompts.map((p, i) => (
        <PromptRow key={i} prompt={p} onClick={(text) => handleStart(text)} />
      ))}
      <ChatInput onSend={handleStart} />
    </BottomSheet>
  );
}
```

**Step 2: Обновить тест ExpertSheet.test.tsx**

Тест должен мокать `@telegram-apps/sdk-react` вместо `window.Telegram`:

```typescript
vi.mock("@telegram-apps/sdk-react", () => ({
  openTelegramLink: vi.fn(),
  initData: { user: () => ({ id: 123, firstName: "Test" }) },
}));
```

**Step 3: Запустить тесты**

```bash
cd mini_app/frontend && npm test
```

**Step 4: Commit**

```bash
git add mini_app/frontend/src/pages/ExpertSheet.tsx mini_app/frontend/src/pages/__tests__/ExpertSheet.test.tsx
git commit -m "feat(mini-app): ExpertSheet → SDK v3 openTelegramLink with fallback"
```

---

### Task 5: Rewrite QuestionSheet — SDK sendData + closeMiniApp

**Files:**
- Rewrite: `mini_app/frontend/src/pages/QuestionSheet.tsx`
- Modify: `mini_app/frontend/src/pages/__tests__/QuestionSheet.test.tsx`

**Step 1: Переписать QuestionSheet.tsx**

```typescript
// mini_app/frontend/src/pages/QuestionSheet.tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { closeMiniApp, sendData } from "@telegram-apps/sdk-react";
import { fetchConfig } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { PromptRow } from "../components/PromptRow";
import { ChatInput } from "../components/ChatInput";
import type { Question } from "../types";

export function QuestionSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [question, setQuestion] = useState<Question | null>(null);

  useEffect(() => {
    fetchConfig().then((c) => {
      setQuestion(c.questions.find((q: Question) => q.id === id) ?? null);
    });
  }, [id]);

  if (!question) return null;

  const handlePrompt = (text: string) => {
    try {
      sendData(text);
      closeMiniApp();
    } catch (e) {
      console.warn("sendData/closeMiniApp failed:", e);
    }
  };

  return (
    <BottomSheet
      emoji={question.emoji}
      title={question.title}
      description={question.description}
      onClose={() => navigate("/")}
    >
      {question.prompts.map((p, i) => (
        <PromptRow key={i} prompt={p} onClick={handlePrompt} />
      ))}
      <ChatInput onSend={handlePrompt} />
    </BottomSheet>
  );
}
```

**Step 2: Обновить тест**

```typescript
vi.mock("@telegram-apps/sdk-react", () => ({
  sendData: vi.fn(),
  closeMiniApp: vi.fn(),
}));
```

**Step 3: Тесты + commit**

```bash
cd mini_app/frontend && npm test
git add mini_app/frontend/src/pages/QuestionSheet.tsx mini_app/frontend/src/pages/__tests__/QuestionSheet.test.tsx
git commit -m "feat(mini-app): QuestionSheet → SDK v3 sendData + closeMiniApp"
```

---

### Task 6: Fix vite.config — proxy port + host

**Files:**
- Modify: `mini_app/frontend/vite.config.ts`

**Step 1: Обновить vite.config.ts**

Текущий proxy указывает на порт **8080** (неправильно). mini-app-api на **8090**.

```typescript
/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,  // нужно для tunnel
    proxy: {
      "/api": "http://localhost:8090",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
```

**Step 2: Проверить что proxy работает**

```bash
cd mini_app/frontend && npm run dev &
curl -s http://localhost:5173/api/config | head -c 100
kill %1
```

Expected: JSON с questions и experts.

**Step 3: Commit**

```bash
git add mini_app/frontend/vite.config.ts
git commit -m "fix(mini-app): vite proxy port 8080→8090, add host:true for tunnel"
```

---

### Task 7: Обновить все тесты

**Files:**
- Modify: Все `__tests__/*.test.tsx` файлы
- Modify: `mini_app/frontend/src/test-setup.ts`

**Step 1: Обновить test-setup.ts — мок SDK**

```typescript
// mini_app/frontend/src/test-setup.ts
import "@testing-library/jest-dom";

// Mock @telegram-apps/sdk-react для тестов
vi.mock("@telegram-apps/sdk-react", () => ({
  init: vi.fn(),
  openTelegramLink: vi.fn(),
  closeMiniApp: vi.fn(),
  sendData: vi.fn(),
  initData: {
    user: () => ({ id: 99999, firstName: "Test" }),
    restore: vi.fn(),
  },
  mockTelegramEnv: vi.fn(),
  isTMA: () => false,
  parseInitData: vi.fn(),
  $debug: { set: vi.fn() },
  expandViewport: vi.fn(),
  miniApp: { mount: vi.fn() },
  themeParams: { mount: vi.fn() },
  swipeBehavior: { mount: vi.fn() },
}));
```

**Step 2: Убрать все `window.Telegram` моки из тестов**

Пройтись по всем тестам: заменить `window.Telegram = ...` на импорты из мока SDK.

**Step 3: Запустить все тесты**

```bash
cd mini_app/frontend && npm test
```

Expected: Все 13 тест-файлов проходят.

**Step 4: Commit**

```bash
git add mini_app/frontend/src/
git commit -m "test(mini-app): update all tests for SDK v3 mocks"
```

---

### Task 8: Проверить build + Docker

**Files:**
- Возможно modify: `mini_app/frontend/Dockerfile`

**Step 1: Проверить TypeScript build**

```bash
cd mini_app/frontend && npm run build
```

Expected: Без ошибок. Выход в `dist/`.

**Step 2: Проверить Docker build**

```bash
cd /home/user/projects/rag-fresh
docker compose build mini-app-frontend
```

Expected: Сборка без ошибок.

**Step 3: Commit если были изменения**

---

### Task 9: Smoke test — браузер + Telegram tunnel

**Step 1: Тест в браузере (mock env)**

```bash
cd mini_app/frontend && npm run dev
```

Открыть http://localhost:5173:
- [ ] Видно карточки вопросов и экспертов
- [ ] Eruda кнопка в углу
- [ ] Клик на эксперта → ExpertSheet → клик на промт → консоль: `openTelegramLink called`
- [ ] Клик на вопрос → QuestionSheet → клик на промт → консоль: `sendData called`

**Step 2: Тест в Telegram (tunnel)**

```bash
ssh -R 8091:127.0.0.1:5173 vps -N
```

Открыть Mini App в Telegram:
- [ ] Карточки загружаются
- [ ] Клик на эксперта → промт → deep link → бот создаёт тред → RAG ответ
- [ ] Клик на вопрос → sendData → бот получает → ответ

**Step 3: Финальный commit**

```bash
git add -p  # review changes
git commit -m "feat(mini-app): complete rewrite to @telegram-apps/sdk-react v3"
```
