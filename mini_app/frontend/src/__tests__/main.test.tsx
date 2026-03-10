import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('main.tsx', () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('calls initApp and renders', async () => {
    const mockRender = vi.fn();
    const mockCreateRoot = vi.fn(() => ({ render: mockRender }));

    vi.doMock('react-dom/client', () => ({ createRoot: mockCreateRoot }));
    vi.doMock('../bootstrap', () => ({
      initApp: vi.fn(() => Promise.resolve({ isTelegram: true })),
    }));
    vi.doMock('../App', () => ({ App: () => null }));
    vi.doMock('../guards/TelegramGate', () => ({
      TelegramGate: ({ children }: { children: React.ReactNode }) => children,
    }));
    vi.doMock('../ErrorBoundary', () => ({
      ErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
    }));

    await import('../main');

    // Ждём async initApp
    await new Promise((r) => setTimeout(r, 0));

    expect(mockCreateRoot).toHaveBeenCalled();
    expect(mockRender).toHaveBeenCalled();
  });
});
