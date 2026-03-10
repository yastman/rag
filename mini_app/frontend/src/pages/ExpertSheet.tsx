import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { openTelegramLink, initData } from "@tma.js/sdk-react";
import { fetchConfig, remoteLog, startExpert } from "../api";
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

  const user = initData.user();
  const userId = user?.id;

  const handleStart = async (text: string) => {
    remoteLog("info", "handleStart", { userId, id, text });

    if (!userId) {
      remoteLog("error", "userId undefined — initData.user() is null");
      alert("Ошибка: не удалось определить пользователя.");
      return;
    }
    if (!id || loading) return;
    setLoading(true);

    try {
      const data = await startExpert(userId, id, text);
      remoteLog("info", "startExpert OK", { start_link: data.start_link });

      try {
        if (openTelegramLink.isAvailable()) {
          openTelegramLink(data.start_link);
        } else {
          remoteLog("warn", "openTelegramLink not available, fallback");
          window.location.href = data.start_link;
        }
      } catch (e) {
        remoteLog("warn", "openTelegramLink threw, fallback", { error: String(e) });
        window.location.href = data.start_link;
      }
    } catch (err) {
      remoteLog("error", "startExpert failed", { error: String(err) });
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
