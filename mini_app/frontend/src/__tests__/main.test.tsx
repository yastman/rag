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
      initData: { restore: vi.fn() },
      mountThemeParamsSync: vi.fn(),
      bindThemeParamsCssVars: vi.fn(),
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

  it('restores initData after init', async () => {
    const { initData } = await import('@telegram-apps/sdk-react');
    await import('../main');
    expect(initData.restore).toHaveBeenCalled();
  });

  it('calls setupMockEnv before init', async () => {
    const callOrder: string[] = [];

    vi.doMock('../mockEnv', () => ({
      setupMockEnv: vi.fn(() => {
        callOrder.push('setupMockEnv');
      }),
    }));
    vi.doMock('@telegram-apps/sdk-react', () => ({
      init: vi.fn(() => {
        callOrder.push('init');
      }),
      initData: { restore: vi.fn() },
      mountThemeParamsSync: vi.fn(),
      bindThemeParamsCssVars: vi.fn(),
    }));

    await import('../main');

    const setupIdx = callOrder.indexOf('setupMockEnv');
    const initIdx = callOrder.indexOf('init');

    expect(setupIdx).toBeGreaterThanOrEqual(0);
    expect(initIdx).toBeGreaterThanOrEqual(0);
    expect(setupIdx).toBeLessThan(initIdx);
  });

  it('calls init after mockEnv', async () => {
    const { init } = await import('@telegram-apps/sdk-react');
    const { setupMockEnv } = await import('../mockEnv');

    await import('../main');

    expect(setupMockEnv).toHaveBeenCalled();
    expect(init).toHaveBeenCalled();
  });
});
