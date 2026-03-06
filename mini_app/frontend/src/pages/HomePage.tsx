import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchConfig } from "../api";
import { QuestionCard } from "../components/QuestionCard";
import { ExpertRow } from "../components/ExpertRow";
import { SectionHeader } from "../components/SectionHeader";
import type { AppConfig, Question, Expert } from "../types";

export function HomePage() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig({ questions: [], experts: [] }));
  }, []);

  if (!config)
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        Загрузка...
      </div>
    );

  const handleQuestion = (q: Question) => navigate(`/question/${q.id}`);
  const handleExpert = (e: Expert) => navigate(`/expert/${e.id}`);

  return (
    <div style={{ paddingBottom: 16 }}>
      <SectionHeader title="Вопросы" onShowAll={() => {}} />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          padding: "0 16px",
        }}
      >
        {config.questions.map((q) => (
          <QuestionCard key={q.id} question={q} onClick={handleQuestion} />
        ))}
      </div>

      <SectionHeader title="Эксперты" onShowAll={() => {}} />
      <div>
        {config.experts.map((e) => (
          <ExpertRow key={e.id} expert={e} onClick={handleExpert} />
        ))}
      </div>
    </div>
  );
}
