import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { streamChat } from "../api";
import { ChatBubble } from "../components/ChatBubble";
import { ChatInput } from "../components/ChatInput";
import { TypingIndicator } from "../components/TypingIndicator";
import type { ChatMessage } from "../types";

export function ChatPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [currentChunk, setCurrentChunk] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const initialMessage = params.get("message");
  const expertId = params.get("expert_id") ?? undefined;
  const initialized = useRef(false);

  useEffect(() => {
    if (initialMessage && !initialized.current) {
      initialized.current = true;
      sendMessage(initialMessage);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentChunk]);

  const sendMessage = async (text: string) => {
    setMessages((prev) => [...prev, { role: "user", text }]);
    setStreaming(true);
    setCurrentChunk("");

    let fullText = "";
    try {
      for await (const event of streamChat(text, 123, expertId)) {
        if (event.type === "chunk") {
          fullText += event.text;
          setCurrentChunk(fullText);
        } else if (event.type === "done") {
          fullText = event.full_text;
        }
      }
    } catch {
      fullText = fullText || "Произошла ошибка. Попробуйте позже.";
    }

    setStreaming(false);
    setCurrentChunk("");
    setMessages((prev) => [...prev, { role: "assistant", text: fullText }]);
  };

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (webApp?.BackButton) {
      webApp.BackButton.show();
      webApp.BackButton.onClick(() => navigate(-1));
      return () => webApp.BackButton.hide();
    }
  }, [navigate]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <div style={{ flex: 1, paddingTop: 8, paddingBottom: 80 }}>
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} text={m.text} />
        ))}
        {streaming && currentChunk && <ChatBubble role="assistant" text={currentChunk} />}
        {streaming && !currentChunk && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={sendMessage} />
    </div>
  );
}
