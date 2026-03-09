import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchConfig, startExpert } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { ChatInput } from "../components/ChatInput";
import { PromptRow } from "../components/PromptRow";
import type { Expert } from "../types";

export function ExpertSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [expert, setExpert] = useState<Expert | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchConfig().then((c) => {
      setExpert(c.experts.find((e: Expert) => e.id === id) ?? null);
    });
  }, [id]);

  if (!expert) return null;

  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;

  const handleStart = async (text: string) => {
    if (!userId || !id || loading) return;
    setLoading(true);
    try {
      await startExpert(userId, id, text);
      // Close Mini App — user lands in bot chat with the topic
      window.Telegram?.WebApp?.close();
    } catch (err) {
      console.error("Failed to start expert:", err);
      setLoading(false);
    }
  };

  return (
    <BottomSheet
      emoji={expert.emoji}
      title={expert.name}
      description={expert.description}
      onClose={() => navigate("/")}
    >
      {expert.prompts.map((p, i) => (
        <PromptRow key={i} prompt={p} onClick={(text) => handleStart(text)} />
      ))}
      <ChatInput onSend={handleStart} />
    </BottomSheet>
  );
}
