import type { Question } from "../types";

interface Props {
  question: Question;
  onClick: (q: Question) => void;
}

export function QuestionCard({ question, onClick }: Props) {
  return (
    <div
      onClick={() => onClick(question)}
      style={{
        background: "var(--tg-theme-secondary-bg-color)",
        borderRadius: 16,
        padding: "20px 12px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        minHeight: 100,
        justifyContent: "center",
      }}
    >
      <span style={{ fontSize: 32 }}>{question.emoji}</span>
      <span
        style={{
          fontSize: 14,
          fontWeight: 500,
          color: "var(--tg-theme-text-color)",
          textAlign: "center",
          lineHeight: 1.3,
        }}
      >
        {question.title}
      </span>
    </div>
  );
}
