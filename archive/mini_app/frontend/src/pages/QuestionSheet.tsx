import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { miniApp, sendData } from "@tma.js/sdk-react";
import { fetchConfig } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { PromptRow } from "../components/PromptRow";
import { ChatInput } from "../components/ChatInput";
import type { Question } from "../types";

type QuestionSheetState =
  | { status: "loading" }
  | { status: "ready"; question: Question }
  | { status: "not-found" }
  | { status: "error" };

export function QuestionSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [state, setState] = useState<QuestionSheetState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });

    fetchConfig()
      .then((c) => {
        if (!active) return;
        const question = c.questions.find((q: Question) => q.id === id);
        setState(question ? { status: "ready", question } : { status: "not-found" });
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
        title="Не удалось загрузить вопросы"
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
        title="Вопрос не найден"
        description="Вернитесь на главную и выберите другой вопрос."
        onClose={() => navigate("/")}
      >
        {null}
      </BottomSheet>
    );
  }

  const { question } = state;

  const handlePrompt = (text: string) => {
    sendData.ifAvailable(text);
    miniApp.close.ifAvailable();
  };

  return (
    <BottomSheet
      emoji={question.emoji}
      title={question.title}
      description={question.description}
      onClose={() => navigate("/")}
    >
      {question.prompts.map((p, i) => (
        <PromptRow key={i} prompt={p} onClick={handlePrompt} />
      ))}
      <ChatInput onSend={handlePrompt} />
    </BottomSheet>
  );
}
