/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";

// jsdom stubs
window.HTMLElement.prototype.scrollIntoView = () => {};
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

// Mock @telegram-apps/sdk-react для тестов
vi.mock("@telegram-apps/sdk-react", () => ({
  init: vi.fn(),
  openTelegramLink: Object.assign(vi.fn(), {
    isAvailable: vi.fn(() => true),
    ifAvailable: vi.fn(),
  }),
  closeMiniApp: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  sendData: Object.assign(vi.fn(), { ifAvailable: vi.fn() }),
  initData: {
    user: () => ({ id: 99999, firstName: "Test" }),
    restore: vi.fn(),
  },
  mockTelegramEnv: vi.fn(),
  isTMA: () => false,
  parseInitData: vi.fn(),
}));
