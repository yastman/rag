import { mockTelegramEnv, isTMA } from "@telegram-apps/sdk-react";

/**
 * Мок Telegram окружения для разработки в браузере.
 * В Telegram (isTMA=true) — ничего не делает.
 * В браузере — подставляет фейковые launchParams.
 */
export function setupMockEnv(): void {
  if (isTMA()) return;

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
    ["signature", "mock_signature_for_dev"],
  ]).toString();

  const launchParams = new URLSearchParams([
    ["tgWebAppVersion", "8"],
    ["tgWebAppPlatform", "tdesktop"],
    ["tgWebAppData", initDataRaw],
    [
      "tgWebAppThemeParams",
      JSON.stringify({
        accent_text_color: "#6ab2f2",
        bg_color: "#17212b",
        button_color: "#5288c1",
        button_text_color: "#ffffff",
        destructive_text_color: "#ec3942",
        header_bg_color: "#17212b",
        hint_color: "#708499",
        link_color: "#6ab3f3",
        secondary_bg_color: "#232e3c",
        subtitle_text_color: "#708499",
        text_color: "#f5f5f5",
      }),
    ],
  ]);

  mockTelegramEnv({ launchParams });

  console.log("[mockEnv] Telegram environment mocked for browser dev");
}
