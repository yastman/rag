import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TelegramGate } from "../TelegramGate";

describe("TelegramGate", () => {
  it("renders children when isTelegram=true", () => {
    render(
      <TelegramGate isTelegram={true}>
        <div>App Content</div>
      </TelegramGate>,
    );
    expect(screen.getByText("App Content")).toBeInTheDocument();
  });

  it("renders children in dev mode even when isTelegram=false", () => {
    // В тестах DEV = true по умолчанию
    render(
      <TelegramGate isTelegram={false}>
        <div>App Content</div>
      </TelegramGate>,
    );
    expect(screen.getByText("App Content")).toBeInTheDocument();
  });

  it("renders fallback when isTelegram=false and not dev", () => {
    // Мокаем production mode
    const original = import.meta.env.DEV;
    import.meta.env.DEV = false;

    render(
      <TelegramGate isTelegram={false}>
        <div>App Content</div>
      </TelegramGate>,
    );

    expect(screen.queryByText("App Content")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Telegram/i })).toBeInTheDocument();

    import.meta.env.DEV = original;
  });
});
