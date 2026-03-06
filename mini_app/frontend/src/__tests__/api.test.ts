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
      json: async () => ({ questions: [], experts: [] }),
    } as Response);

    await fetchConfig();

    expect(mockFetch).toHaveBeenCalledWith('/api/config');
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
});
