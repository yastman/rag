import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchConfig } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { PromptRow } from "../components/PromptRow";
import { ChatInput } from "../components/ChatInput";
import type { Expert } from "../types";

export function ExpertSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [expert, setExpert] = useState<Expert | null>(null);

  useEffect(() => {
    fetchConfig().then((c) => {
      setExpert(c.experts.find((e: Expert) => e.id === id) ?? null);
    });
  }, [id]);

  if (!expert) return null;

  const handlePrompt = (text: string) => {
    navigate(`/chat?message=${encodeURIComponent(text)}&expert_id=${id}`);
  };

  return (
    <BottomSheet
      emoji={expert.emoji}
      title={expert.name}
      description={expert.description}
      onClose={() => navigate("/")}
    >
      {expert.prompts.map((p, i) => (
        <PromptRow key={i} prompt={p} onClick={handlePrompt} />
      ))}
      <ChatInput onSend={(text) => handlePrompt(text)} />
    </BottomSheet>
  );
}
