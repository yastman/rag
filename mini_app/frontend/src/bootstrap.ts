import {
  init,
  initData,
  miniApp,
  themeParams,
  viewport,
  swipeBehavior,
} from "@tma.js/sdk-react";
import { isTMA } from "@tma.js/bridge";
import { setupMockEnv } from "./mockEnv";

export type AppBootstrapResult = {
  isTelegram: boolean;
};

function applyFallbackTheme() {
  const vars: Record<string, string> = {
    "--tg-theme-accent-text-color": "#6ab2f2",
    "--tg-theme-bg-color": "#17212b",
    "--tg-theme-button-color": "#5288c1",
    "--tg-theme-button-text-color": "#ffffff",
    "--tg-theme-destructive-text-color": "#ec3942",
    "--tg-theme-header-bg-color": "#17212b",
    "--tg-theme-hint-color": "#708499",
    "--tg-theme-link-color": "#6ab3f3",
    "--tg-theme-secondary-bg-color": "#232e3c",
    "--tg-theme-subtitle-text-color": "#708499",
    "--tg-theme-text-color": "#f5f5f5",
    "--tg-theme-section-separator-color": "rgba(255,255,255,0.08)",
  };
  for (const [key, value] of Object.entries(vars)) {
    document.documentElement.style.setProperty(key, value);
  }
}

export async function initApp(): Promise<AppBootstrapResult> {
  const isDev = import.meta.env.DEV;

  // 1. Mock env (dev + browser only)
  if (isDev) {
    setupMockEnv();
  }

  // 2. Detect environment (in dev, mockEnv may not fool isTMA("complete") — force true)
  const isTelegram = isDev ? true : await isTMA("complete");

  if (!isTelegram) {
    return { isTelegram: false };
  }

  // 3. SDK init (may throw UnknownEnvError in browser dev)
  try {
    init();
    initData.restore();
    themeParams.mount();
    themeParams.bindCssVars();
    miniApp.mount();
    miniApp.ready();

    if (viewport.mount.isAvailable()) {
      await viewport.mount();
      viewport.bindCssVars();
    }

    if (swipeBehavior.isSupported()) {
      swipeBehavior.mount();
      swipeBehavior.disableVertical();
    }
  } catch (err) {
    if (isDev) {
      console.warn("[bootstrap] SDK init failed in dev, applying fallback CSS vars", err);
      applyFallbackTheme();
    } else {
      throw err;
    }
  }

  // Eruda (dev only)
  if (isDev) {
    import("eruda").then((e) => e.default.init());
  }

  return { isTelegram: true };
}
