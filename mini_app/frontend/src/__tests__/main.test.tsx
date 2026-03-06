import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('main.tsx', () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
    // Mock react-dom/client and App to avoid actual DOM rendering
    vi.doMock('react-dom/client', () => ({
      createRoot: vi.fn(() => ({ render: vi.fn() })),
    }));
    vi.doMock('../App', () => ({ App: () => null }));
  });

  afterEach(() => {
    delete window.Telegram;
    vi.resetModules();
  });

  it('calls Telegram.WebApp.ready() if available', async () => {
    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = { WebApp: { ready, expand } as Window['Telegram']['WebApp'] };

    await import('../main');

    expect(ready).toHaveBeenCalled();
  });

  it('calls Telegram.WebApp.expand() if available', async () => {
    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = { WebApp: { ready, expand } as Window['Telegram']['WebApp'] };

    await import('../main');

    expect(expand).toHaveBeenCalled();
  });

  it('does not throw if Telegram is undefined', async () => {
    delete window.Telegram;

    await expect(import('../main')).resolves.not.toThrow();
  });
});
