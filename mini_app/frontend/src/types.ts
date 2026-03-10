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
