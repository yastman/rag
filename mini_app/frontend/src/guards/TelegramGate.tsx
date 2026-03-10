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
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>Откройте в Telegram</h1>
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
