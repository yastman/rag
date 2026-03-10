/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";

// jsdom stubs
window.HTMLElement.prototype.scrollIntoView = () => {};
// CSS.supports not available in jsdom — stub it to prevent eruda errors
if (!globalThis.CSS) {
  (globalThis as unknown as Record<string, unknown>).CSS = {};
}
if (!(globalThis.CSS as Record<string, unknown>).supports) {
  (globalThis.CSS as unknown as Record<string, unknown>).supports = () => false;
}
window.matchMedia = window.matchMedia ?? (() => ({
  matches: false,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
}));

// Mock eruda (dev tool, not needed in tests)
vi.mock("eruda", () => ({ default: { init: vi.fn() } }));

// Mock @tma.js/sdk-react для тестов
vi.mock("@tma.js/sdk-react", () => ({
  init: vi.fn(),
  openTelegramLink: Object.assign(vi.fn(), {
    isAvailable: vi.fn(() => true),
    ifAvailable: vi.fn(),
  }),
  miniApp: {
    close: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  },
  sendData: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  initData: {
    user: () => ({ id: 99999, firstName: "Test" }),
    restore: vi.fn(),
  },
  themeParams: {
    mount: vi.fn(),
    bindCssVars: vi.fn(),
  },
  viewport: {
    mount: Object.assign(vi.fn(() => Promise.resolve()), {
      isAvailable: vi.fn(() => true),
    }),
    bindCssVars: vi.fn(),
  },
  swipeBehavior: {
    isSupported: vi.fn(() => true),
    mount: vi.fn(),
    disableVertical: vi.fn(),
  },
  parseInitData: vi.fn(),
}));

// Mock @tma.js/bridge
vi.mock("@tma.js/bridge", () => ({
  mockTelegramEnv: vi.fn(),
  isTMA: vi.fn(() => false),
}));
