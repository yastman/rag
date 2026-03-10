import { createRoot } from "react-dom/client";
import {
  init,
  initData,
  mountThemeParamsSync,
  bindThemeParamsCssVars,
} from "@telegram-apps/sdk-react";
import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import { setupMockEnv } from "./mockEnv";

// Mock env BEFORE any SDK calls — only activates in browser
setupMockEnv();

// Init Eruda in development
if (import.meta.env.DEV) {
  import("eruda").then(({ default: eruda }) => eruda.init());
}

// SDK init
init();

// Restore init data (user, auth_date, hash, etc.)
initData.restore();

// Mount theme params and bind --tg-theme-* CSS variables
mountThemeParamsSync();
bindThemeParamsCssVars();

// Render
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
