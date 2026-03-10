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
