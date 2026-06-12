import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as bridge from '@tma.js/bridge';

describe('setupMockEnv', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('always calls mockTelegramEnv (no isTMA guard)', async () => {
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    expect(mockTelegramEnvSpy).toHaveBeenCalledTimes(1);
  });

  it('passes correct launchParams structure', async () => {
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    expect(mockTelegramEnvSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        launchParams: expect.objectContaining({
          tgWebAppVersion: '8',
          tgWebAppPlatform: 'tdesktop',
          tgWebAppThemeParams: expect.objectContaining({
            bg_color: '#17212b',
            text_color: '#f5f5f5',
          }),
          tgWebAppData: expect.any(URLSearchParams),
        }),
        onEvent: expect.any(Function),
      }),
    );
  });

  it('passes user data in tgWebAppData', async () => {
    const mockTelegramEnvSpy = vi.spyOn(bridge, 'mockTelegramEnv');

    const { setupMockEnv } = await import('../mockEnv');
    setupMockEnv();

    const callArg = mockTelegramEnvSpy.mock.calls[0][0] as {
      launchParams: { tgWebAppData: URLSearchParams };
    };
    const data = callArg.launchParams.tgWebAppData;
    expect(data.get('hash')).toBe('mock_hash_for_dev');
    const user = JSON.parse(data.get('user')!);
    expect(user.id).toBe(99999999);
    expect(user.username).toBe('dev_user');
  });
});
