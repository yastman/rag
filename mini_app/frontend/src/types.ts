export interface Prompt {
  emoji: string;
  text: string;
}

export interface Question {
  id: string;
  emoji: string;
  title: string;
  description: string;
  prompts: Prompt[];
}

export interface Expert {
  id: string;
  emoji: string;
  name: string;
  description: string;
  system_prompt_key: string;
  cta_text: string;
  cta_source: string;
  prompts: Prompt[];
}

export interface AppConfig {
  questions: Question[];
  experts: Expert[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
        MainButton: { show(): void; hide(): void; setText(t: string): void; onClick(cb: () => void): void };
        ready(): void;
        expand(): void;
        close(): void;
        initData: string;
        initDataUnsafe: { user?: { id: number; first_name: string } };
        themeParams: Record<string, string>;
      };
    };
  }
}
