import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  placeholder?: string;
}

export function ChatInput({ onSend, placeholder = "Спросить что-нибудь..." }: Props) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div
      style={{
        position: "sticky",
        bottom: 0,
        padding: "12px 16px",
        background: "var(--tg-theme-bg-color)",
        display: "flex",
        gap: 8,
      }}
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        placeholder={placeholder}
        style={{
          flex: 1,
          padding: "10px 16px",
          borderRadius: 20,
          border: "none",
          background: "var(--tg-theme-secondary-bg-color)",
          color: "var(--tg-theme-text-color)",
          fontSize: 15,
          outline: "none",
        }}
      />
      <button
        onClick={handleSend}
        style={{
          width: 40,
          height: 40,
          borderRadius: "50%",
          border: "none",
          background: "var(--tg-theme-button-color)",
          color: "var(--tg-theme-button-text-color)",
          fontSize: 18,
          cursor: "pointer",
        }}
      >
        ^
      </button>
    </div>
  );
}
