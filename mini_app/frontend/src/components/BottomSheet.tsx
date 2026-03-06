import type { ReactNode } from "react";

interface Props {
  emoji: string;
  title: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
}

export function BottomSheet({ emoji, title, description, onClose, children }: Props) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--tg-theme-bg-color)",
        zIndex: 100,
        display: "flex",
        flexDirection: "column",
        overflowY: "auto",
      }}
    >
      <div
        onClick={onClose}
        style={{
          padding: "16px",
          fontSize: 24,
          cursor: "pointer",
          color: "var(--tg-theme-text-color)",
        }}
      >
        x
      </div>
      <div style={{ textAlign: "center", padding: "0 16px 24px" }}>
        <div style={{ fontSize: 64, marginBottom: 12 }}>{emoji}</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--tg-theme-text-color)" }}>
          {title}
        </div>
        <div style={{ fontSize: 14, color: "var(--tg-theme-hint-color)", marginTop: 4 }}>
          {description}
        </div>
      </div>
      {children}
    </div>
  );
}
