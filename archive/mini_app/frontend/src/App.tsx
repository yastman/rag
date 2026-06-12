import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { ExpertSheet } from "./pages/ExpertSheet";
import { HomePage } from "./pages/HomePage";
import { QuestionSheet } from "./pages/QuestionSheet";

export function App() {
  return (
    <HashRouter>
      <div
        style={{
          minHeight: "100vh",
          background: "var(--tg-theme-bg-color, #ffffff)",
          color: "var(--tg-theme-text-color, #000000)",
        }}
      >
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/question/:id" element={<QuestionSheet />} />
          <Route path="/expert/:id" element={<ExpertSheet />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </HashRouter>
  );
}
