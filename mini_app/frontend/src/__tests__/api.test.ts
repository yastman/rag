import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchConfig, streamChat } from '../api';

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

describe('streamChat', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends POST with correct body', async () => {
    const mockFetch = vi.mocked(fetch);
    const lines = ['data: {"type":"chunk","text":"ok"}', 'data: {"type":"done","full_text":"ok"}'];
    let callCount = 0;
    const mockReader = {
      read: vi.fn().mockImplementation(async () => {
        if (callCount < lines.length) {
          const text = lines[callCount++] + '\n';
          return { done: false, value: new TextEncoder().encode(text) };
        }
        return { done: true, value: undefined };
      }),
    };
    mockFetch.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const events = [];
    for await (const event of streamChat('Привет', 42, 'expert1')) {
      events.push(event);
    }

    expect(mockFetch).toHaveBeenCalledWith('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'Привет', user_id: 42, expert_id: 'expert1' }),
    });
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'chunk', text: 'ok' });
    expect(events[1]).toEqual({ type: 'done', full_text: 'ok' });
  });

  it('buffers SSE lines split across read() chunks', async () => {
    const mockFetch = vi.mocked(fetch);
    // First chunk ends mid-JSON, second chunk completes the line
    const chunks = [
      'data: {"type":"chunk","te',
      'xt":"hello"}\ndata: {"type":"done","full_text":"hello"}\n',
    ];
    let callCount = 0;
    const mockReader = {
      read: vi.fn().mockImplementation(async () => {
        if (callCount < chunks.length) {
          return { done: false, value: new TextEncoder().encode(chunks[callCount++]) };
        }
        return { done: true, value: undefined };
      }),
    };
    mockFetch.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const events = [];
    for await (const event of streamChat('test', 1)) {
      events.push(event);
    }

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'chunk', text: 'hello' });
    expect(events[1]).toEqual({ type: 'done', full_text: 'hello' });
  });

  it('throws on non-ok response (500)', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    } as unknown as Response);

    const gen = streamChat('test', 1);
    await expect(gen.next()).rejects.toThrow('Chat request failed: 500');
  });

  it('throws when backend sends error event', async () => {
    const mockFetch = vi.mocked(fetch);
    let callCount = 0;
    const chunks = ['data: {"type":"error","text":"Backend error"}\n'];
    const mockReader = {
      read: vi.fn().mockImplementation(async () => {
        if (callCount < chunks.length) {
          return { done: false, value: new TextEncoder().encode(chunks[callCount++]) };
        }
        return { done: true, value: undefined };
      }),
    };
    mockFetch.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const gen = streamChat('test', 1);
    await expect(gen.next()).rejects.toThrow('Backend error');
  });
});
