import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as bridge from '@tma.js/bridge';

describe('setupMockEnv', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does nothing when isTMA returns true', async () => {
    vi.spyOn(bridge, 'isTMA').mockReturnValue(true as unknown as ReturnType<typeof bridge.isTMA>);
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    expect(mockTelegramEnvSpy).not.toHaveBeenCalled();
  });

  it('calls mockTelegramEnv when not in TMA', async () => {
    vi.spyOn(bridge, 'isTMA').mockReturnValue(false as unknown as ReturnType<typeof bridge.isTMA>);
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    expect(mockTelegramEnvSpy).toHaveBeenCalledTimes(1);
  });

  it('passes correct launchParams structure', async () => {
    vi.spyOn(bridge, 'isTMA').mockReturnValue(false as unknown as ReturnType<typeof bridge.isTMA>);
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    expect(mockTelegramEnvSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        launchParams: expect.any(URLSearchParams),
      }),
    );

    const callArg = mockTelegramEnvSpy.mock.calls[0][0] as { launchParams: URLSearchParams };
    const launchParams = callArg.launchParams;
    expect(launchParams.get('tgWebAppVersion')).toBe('8');
    expect(launchParams.get('tgWebAppPlatform')).toBe('tdesktop');
    expect(launchParams.get('tgWebAppData')).toBeTruthy();
    expect(launchParams.get('tgWebAppThemeParams')).toBeTruthy();
  });
});
