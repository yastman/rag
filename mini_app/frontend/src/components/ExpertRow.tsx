import type { Expert } from "../types";

interface Props {
  expert: Expert;
  onClick: (e: Expert) => void;
}

export function ExpertRow({ expert, onClick }: Props) {
  return (
    <div
      onClick={() => onClick(expert)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "12px 16px",
        cursor: "pointer",
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          background: "var(--tg-theme-secondary-bg-color)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 24,
          flexShrink: 0,
        }}
      >
        {expert.emoji}
      </div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--tg-theme-text-color)" }}>
          {expert.name}
        </div>
        <div style={{ fontSize: 13, color: "var(--tg-theme-hint-color)", marginTop: 2 }}>
          {expert.description}
        </div>
      </div>
    </div>
  );
}
