import { createRoot } from "react-dom/client";
import { init } from "@telegram-apps/sdk-react";
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

// Render
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
