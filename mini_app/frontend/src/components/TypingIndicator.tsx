export function TypingIndicator() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", padding: "4px 16px" }}>
      <div
        style={{
          padding: "12px 18px",
          borderRadius: 16,
          background: "var(--tg-theme-secondary-bg-color)",
          fontSize: 20,
        }}
      >
        <span className="typing-dots">...</span>
      </div>
    </div>
  );
}
