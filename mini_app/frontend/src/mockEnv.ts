import { mockTelegramEnv, emitEvent } from "@tma.js/bridge";

const themeParams = {
  accent_text_color: "#6ab2f2",
  bg_color: "#17212b",
  button_color: "#5288c1",
  button_text_color: "#ffffff",
  destructive_text_color: "#ec3942",
  header_bg_color: "#17212b",
  hint_color: "#708499",
  link_color: "#6ab3f3",
  secondary_bg_color: "#232e3c",
  section_bg_color: "#17212b",
  section_header_text_color: "#6ab3f3",
  subtitle_text_color: "#708499",
  text_color: "#f5f5f5",
} as const;

const noInsets = { left: 0, top: 0, bottom: 0, right: 0 } as const;

/**
 * Мок Telegram окружения для разработки в браузере.
 * Вызывается только из bootstrap.ts в dev mode.
 * Всегда переустанавливает window.TelegramWebviewProxy
 * (sessionStorage переживает reload, но window globals — нет).
 */
export function setupMockEnv(): void {

  mockTelegramEnv({
    launchParams: {
      tgWebAppThemeParams: themeParams,
      tgWebAppData: new URLSearchParams([
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
        ["signature", "mock_signature_for_dev"],
      ]),
      tgWebAppStartParam: "debug",
      tgWebAppVersion: "8",
      tgWebAppPlatform: "tdesktop",
    },
    onEvent(event) {
      if (event.name === "web_app_request_theme") {
        return emitEvent("theme_changed", { theme_params: themeParams });
      }
      if (event.name === "web_app_request_viewport") {
        return emitEvent("viewport_changed", {
          height: window.innerHeight,
          width: window.innerWidth,
          is_expanded: true,
          is_state_stable: true,
        });
      }
      if (event.name === "web_app_request_content_safe_area") {
        return emitEvent("content_safe_area_changed", noInsets);
      }
      if (event.name === "web_app_request_safe_area") {
        return emitEvent("safe_area_changed", noInsets);
      }
    },
  });

  console.log("[mockEnv] Telegram environment mocked for browser dev");
}
