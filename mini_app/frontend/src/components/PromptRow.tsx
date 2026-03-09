import type { Prompt } from "../types";

interface Props {
  prompt: Prompt;
  onClick: (text: string) => void;
}

export function PromptRow({ prompt, onClick }: Props) {
  return (
    <div
      onClick={() => onClick(prompt.text)}
      style={{
        display: "flex",
        alignItems: "center",
        padding: "14px 16px",
        cursor: "pointer",
        borderBottom: "1px solid var(--tg-theme-section-separator-color, rgba(255,255,255,0.08))",
      }}
    >
      <span style={{ fontSize: 20, marginRight: 12 }}>{prompt.emoji}</span>
      <span style={{ flex: 1, fontSize: 15, color: "var(--tg-theme-text-color)" }}>
        {prompt.text}
      </span>
      <span style={{ fontSize: 16, color: "var(--tg-theme-hint-color)" }}>&gt;</span>
    </div>
  );
}
