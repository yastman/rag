import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ExpertSheet } from '../ExpertSheet';
import * as api from '../../api';
import * as sdkReact from '@telegram-apps/sdk-react';
import type { AppConfig } from '../../types';

const mockConfig: AppConfig = {
  questions: [],
  experts: [
    {
      id: 'consultant',
      emoji: '👷',
      name: 'Консультант',
      description: 'Опытный специалист',
      system_prompt_key: 'consultant_key',
      cta_text: 'Задать вопрос',
      cta_source: 'expert',
      prompts: [
        { emoji: '🏠', text: 'Как выбрать квартиру?' },
        { emoji: '📋', text: 'Что проверить перед покупкой?' },
      ],
    },
  ],
};

describe('ExpertSheet', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchConfig').mockResolvedValue(mockConfig);
    vi.spyOn(api, 'remoteLog').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderExpertSheet = () =>
    render(
      <MemoryRouter initialEntries={['/expert/consultant']}>
        <Routes>
          <Route path="/expert/:id" element={<ExpertSheet />} />
        </Routes>
      </MemoryRouter>,
    );

  it('renders expert info after config load', async () => {
    renderExpertSheet();
    await waitFor(() => {
      expect(screen.getByText('Консультант')).toBeInTheDocument();
    });
    expect(screen.getByText('Опытный специалист')).toBeInTheDocument();
  });

  it('renders prompts list', async () => {
    renderExpertSheet();
    await waitFor(() => {
      expect(screen.getByText('Как выбрать квартиру?')).toBeInTheDocument();
    });
    expect(screen.getByText('Что проверить перед покупкой?')).toBeInTheDocument();
  });

  it('handleStart calls startExpert with correct params', async () => {
    const startExpertMock = vi.spyOn(api, 'startExpert').mockResolvedValue({
      start_link: 'https://t.me/testbot?start=abc',
      expert_name: 'Консультант',
      status: 'ok',
    });

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));

    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(startExpertMock).toHaveBeenCalledWith(99999, 'consultant', 'Как выбрать квартиру?');
    });
  });

  it('handleStart calls openTelegramLink on success', async () => {
    const openTelegramLinkMock = sdkReact.openTelegramLink as ReturnType<typeof vi.fn>;
    vi.spyOn(api, 'startExpert').mockResolvedValue({
      start_link: 'https://t.me/testbot?start=abc',
      expert_name: 'Консультант',
      status: 'ok',
    });

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(openTelegramLinkMock).toHaveBeenCalledWith('https://t.me/testbot?start=abc');
    });
  });

  it('falls back to location.href when openTelegramLink unavailable', async () => {
    const openTelegramLink = sdkReact.openTelegramLink as ReturnType<typeof vi.fn> & {
      isAvailable: ReturnType<typeof vi.fn>;
    };
    openTelegramLink.isAvailable.mockReturnValue(false);

    const originalLocation = window.location;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location;
    window.location = { ...originalLocation, href: '' };

    vi.spyOn(api, 'startExpert').mockResolvedValue({
      start_link: 'https://t.me/testbot?start=abc',
      expert_name: 'Консультант',
      status: 'ok',
    });

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(window.location.href).toBe('https://t.me/testbot?start=abc');
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).location = originalLocation;
    openTelegramLink.isAvailable.mockReturnValue(true);
  });

  it('falls back to location.href when openTelegramLink throws', async () => {
    const openTelegramLink = sdkReact.openTelegramLink as ReturnType<typeof vi.fn> & {
      isAvailable: ReturnType<typeof vi.fn>;
    };
    openTelegramLink.isAvailable.mockReturnValue(true);
    openTelegramLink.mockImplementationOnce(() => {
      throw new Error('TG link failed');
    });

    const originalLocation = window.location;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location;
    window.location = { ...originalLocation, href: '' };

    vi.spyOn(api, 'startExpert').mockResolvedValue({
      start_link: 'https://t.me/testbot?start=abc',
      expert_name: 'Консультант',
      status: 'ok',
    });

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(window.location.href).toBe('https://t.me/testbot?start=abc');
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).location = originalLocation;
  });

  it('shows error alert when userId is null', async () => {
    vi.spyOn(sdkReact.initData, 'user').mockReturnValue(null);
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Ошибка: не удалось определить пользователя.');
    });

    alertMock.mockRestore();
  });

  it('shows loading state during API call', async () => {
    let resolveStart!: (v: api.StartExpertResponse) => void;
    vi.spyOn(api, 'startExpert').mockReturnValue(
      new Promise<api.StartExpertResponse>((resolve) => {
        resolveStart = resolve;
      }),
    );

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    // Button should be disabled/loading — clicking again should not call startExpert twice
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    resolveStart({
      start_link: 'https://t.me/testbot?start=abc',
      expert_name: 'Консультант',
      status: 'ok',
    });

    await waitFor(() => {
      expect(api.startExpert).toHaveBeenCalledTimes(1);
    });
  });

  it('handles API error gracefully', async () => {
    vi.spyOn(api, 'startExpert').mockRejectedValue(new Error('Network error'));

    renderExpertSheet();
    await waitFor(() => screen.getByText('Как выбрать квартиру?'));
    fireEvent.click(screen.getByText('Как выбрать квартиру?'));

    await waitFor(() => {
      expect(api.remoteLog).toHaveBeenCalledWith(
        'error',
        'startExpert failed',
        expect.objectContaining({ error: expect.stringContaining('Network error') }),
      );
    });
  });
});
