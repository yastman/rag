import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('main.tsx', () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<div id="root"></div>';
    vi.doMock('react-dom/client', () => ({
      createRoot: vi.fn(() => ({ render: vi.fn() })),
    }));
    vi.doMock('../App', () => ({ App: () => null }));
    vi.doMock('../mockEnv', () => ({ setupMockEnv: vi.fn() }));
    vi.doMock('@telegram-apps/sdk-react', () => ({
      init: vi.fn(),
    }));
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('imports without throwing', async () => {
    await expect(import('../main')).resolves.not.toThrow();
  });

  it('calls SDK init on load', async () => {
    const { init } = await import('@telegram-apps/sdk-react');
    await import('../main');
    expect(init).toHaveBeenCalled();
  });
});
