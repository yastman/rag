import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { closeMiniApp, sendData } from "@tma.js/sdk-react";
import { fetchConfig } from "../api";
import { BottomSheet } from "../components/BottomSheet";
import { PromptRow } from "../components/PromptRow";
import { ChatInput } from "../components/ChatInput";
import type { Question } from "../types";

export function QuestionSheet() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [question, setQuestion] = useState<Question | null>(null);

  useEffect(() => {
    fetchConfig().then((c) => {
      setQuestion(c.questions.find((q: Question) => q.id === id) ?? null);
    });
  }, [id]);

  if (!question) return null;

  const handlePrompt = (text: string) => {
    sendData.ifAvailable(text);
    closeMiniApp.ifAvailable();
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
