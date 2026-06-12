import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { initData, miniApp } from "@tma.js/sdk-react";
import { fetchConfig, remoteLog, startExpert } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { ChatInput } from "../components/ChatInput";
import { PromptRow } from "../components/PromptRow";
import type { Expert } from "../types";

type ExpertSheetState =
  | { status: "loading" }
  | { status: "ready"; expert: Expert }
  | { status: "not-found" }
  | { status: "error" };

export function ExpertSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [state, setState] = useState<ExpertSheetState>({ status: "loading" });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });

    fetchConfig()
      .then((c) => {
        if (!active) return;
        const expert = c.experts.find((e: Expert) => e.id === id);
        setState(expert ? { status: "ready", expert } : { status: "not-found" });
      })
      .catch(() => {
        if (active) setState({ status: "error" });
      });

    return () => {
      active = false;
    };
  }, [id]);

  if (state.status === "loading") {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        Загрузка...
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <BottomSheet
        emoji="!"
        title="Не удалось загрузить экспертов"
        description="Проверьте подключение и попробуйте позже."
        onClose={() => navigate("/")}
      >
        {null}
      </BottomSheet>
    );
  }

  if (state.status === "not-found") {
    return (
      <BottomSheet
        emoji="?"
        title="Эксперт не найден"
        description="Вернитесь на главную и выберите другого эксперта."
        onClose={() => navigate("/")}
      >
        {null}
      </BottomSheet>
    );
  }

  const { expert } = state;

  const user = initData.user();
  const userId = user?.id;
  const queryId = initData.queryId?.();

  const handleStart = async (text: string) => {
    remoteLog("info", "handleStart", { userId, id, text, queryId });

    if (!userId) {
      remoteLog("error", "userId undefined — initData.user() is null");
      alert("Ошибка: не удалось определить пользователя.");
      return;
    }
    if (!id || loading) return;
    setLoading(true);

    try {
      // Send payload + query_id to backend; bot will call answerWebAppQuery
      const data = await startExpert(userId, id, text, queryId);
      remoteLog("info", "startExpert OK", { expert_name: data.expert_name });

      // Close Mini App — bot handles the rest via pub/sub + answerWebAppQuery
      miniApp.close.ifAvailable();
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
