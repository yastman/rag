interface Props {
  role: "user" | "assistant";
  text: string;
}

export function ChatBubble({ role, text }: Props) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", padding: "4px 16px" }}>
      <div
        style={{
          maxWidth: "80%",
          padding: "10px 14px",
          borderRadius: 16,
          fontSize: 15,
          lineHeight: 1.4,
          background: isUser
            ? "var(--tg-theme-button-color)"
            : "var(--tg-theme-secondary-bg-color)",
          color: isUser
            ? "var(--tg-theme-button-text-color)"
            : "var(--tg-theme-text-color)",
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </div>
    </div>
  );
}
