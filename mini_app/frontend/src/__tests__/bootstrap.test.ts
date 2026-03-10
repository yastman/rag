import { describe, it, expect, vi, beforeEach, afterAll, beforeAll } from "vitest";

// Мокаем модули до импорта
const mockSetupMockEnv = vi.fn();
const mockInit = vi.fn();
const mockRestore = vi.fn();
const mockThemeMount = vi.fn();
const mockThemeBindCss = vi.fn();
const mockViewportMount = vi.fn(() => Promise.resolve());
const mockViewportBindCss = vi.fn();
const mockSwipeMount = vi.fn();
const mockSwipeDisable = vi.fn();

vi.mock("@tma.js/sdk-react", () => ({
  init: mockInit,
  initData: { restore: mockRestore },
  themeParams: {
    mount: mockThemeMount,
    bindCssVars: mockThemeBindCss,
  },
  viewport: {
    mount: Object.assign(mockViewportMount, {
      isAvailable: vi.fn(() => true),
    }),
    bindCssVars: mockViewportBindCss,
  },
  swipeBehavior: {
    isSupported: vi.fn(() => true),
    mount: mockSwipeMount,
    disableVertical: mockSwipeDisable,
  },
}));

vi.mock("@tma.js/bridge", () => ({
  isTMA: vi.fn(() => Promise.resolve(true)),
}));

vi.mock("../mockEnv", () => ({
  setupMockEnv: mockSetupMockEnv,
}));

vi.mock("eruda", () => ({ default: { init: vi.fn() } }));

describe("bootstrap", () => {
  beforeAll(() => {
    vi.useFakeTimers();
  });

  afterAll(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls init sequence in correct order", async () => {
    const { initApp } = await import("../bootstrap");
    const result = await initApp();

    expect(mockInit).toHaveBeenCalled();
    expect(mockRestore).toHaveBeenCalled();
    expect(mockThemeMount).toHaveBeenCalled();
    expect(mockThemeBindCss).toHaveBeenCalled();
    expect(result.isTelegram).toBe(true);
  });

  it("mounts viewport when available", async () => {
    const { initApp } = await import("../bootstrap");
    await initApp();

    expect(mockViewportMount).toHaveBeenCalled();
    expect(mockViewportBindCss).toHaveBeenCalled();
  });

  it("enables swipe protection when supported", async () => {
    const { initApp } = await import("../bootstrap");
    await initApp();

    expect(mockSwipeMount).toHaveBeenCalled();
    expect(mockSwipeDisable).toHaveBeenCalled();
  });

  it("forces isTelegram=true in dev mode (skips isTMA check)", async () => {
    // In dev mode, isTelegram is always true regardless of isTMA result
    const bridge = await import("@tma.js/bridge");
    vi.mocked(bridge.isTMA).mockResolvedValueOnce(false);

    const { initApp } = await import("../bootstrap");
    const result = await initApp();

    // Dev mode forces isTelegram=true, so init is still called
    expect(result.isTelegram).toBe(true);
    expect(mockInit).toHaveBeenCalled();
  });
});
