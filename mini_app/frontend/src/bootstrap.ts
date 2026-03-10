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

  // 2. Detect environment (setupMockEnv ensures isTMA returns true in browser dev)
  const isTelegram = await isTMA("complete");

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
    swipeBehavior.disableVertical();
  }

  // 8. Eruda (dev only)
  if (isDev) {
    import("eruda").then((e) => e.default.init());
  }

  return { isTelegram: true };
}
