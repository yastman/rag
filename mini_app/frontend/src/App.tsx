import { HashRouter, Routes, Route } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { QuestionSheet } from "./pages/QuestionSheet";
import { ExpertSheet } from "./pages/ExpertSheet";
import { ChatPage } from "./pages/ChatPage";

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
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </div>
    </HashRouter>
  );
}
