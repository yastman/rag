import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchConfig, startExpert } from '../api';

describe('fetchConfig', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls correct URL', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ questions: [], experts: [] }),
    } as Response);

    await fetchConfig();

    expect(mockFetch).toHaveBeenCalledWith('/api/config');
  });

  it('throws and logs on network error', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockRejectedValue(new Error('network error'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(fetchConfig()).rejects.toThrow('network error');
    expect(consoleSpy).toHaveBeenCalledWith(
      '[fetchConfig] Failed to load config:',
      expect.any(Error),
    );
    consoleSpy.mockRestore();
  });

  it('throws on non-ok response', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchConfig()).rejects.toThrow('Config fetch failed: 500');
  });
});

describe('startExpert', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends POST with correct body', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        start_link: 'https://t.me/FortnoksBot?start=consultant_42',
        expert_name: 'Консультант',
        status: 'ok',
      }),
    } as Response);

    const result = await startExpert(123, 'consultant', 'Подбери квартиру');

    expect(mockFetch).toHaveBeenCalledWith('/api/start-expert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 123, expert_id: 'consultant', message: 'Подбери квартиру' }),
    });
    expect(result.start_link).toBe('https://t.me/FortnoksBot?start=consultant_42');
    expect(result.expert_name).toBe('Консультант');
    expect(result.status).toBe('ok');
  });

  it('sends without message when not provided', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        start_link: 'https://t.me/FortnoksBot?start=consultant_1',
        expert_name: 'Test',
        status: 'ok',
      }),
    } as Response);

    await startExpert(123, 'consultant');

    const body = JSON.parse(mockFetch.mock.calls[0][1]!.body as string);
    expect(body.message).toBeUndefined();
  });

  it('throws on non-ok response', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    } as Response);

    await expect(startExpert(1, 'x')).rejects.toThrow('start-expert failed: 404');
  });
});
