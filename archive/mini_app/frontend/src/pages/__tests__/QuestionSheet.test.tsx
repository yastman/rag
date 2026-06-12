import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QuestionSheet } from '../QuestionSheet';
import * as api from '../../api';
import * as sdkReact from '@tma.js/sdk-react';
import type { AppConfig } from '../../types';

const mockConfig: AppConfig = {
  questions: [
    {
      id: 'purchase',
      emoji: '🏠',
      title: 'Покупка',
      description: 'Вопросы о покупке жилья',
      prompts: [
        { emoji: '🔑', text: 'С чего начать поиск квартиры?' },
        { emoji: '💰', text: 'Как рассчитать бюджет?' },
      ],
    },
  ],
  experts: [],
};

describe('QuestionSheet', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchConfig').mockResolvedValue(mockConfig);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderQuestionSheet = (path = '/question/purchase') =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/question/:id" element={<QuestionSheet />} />
        </Routes>
      </MemoryRouter>,
    );

  it('renders question info after config load', async () => {
    renderQuestionSheet();
    await waitFor(() => {
      expect(screen.getByText('Покупка')).toBeInTheDocument();
    });
    expect(screen.getByText('Вопросы о покупке жилья')).toBeInTheDocument();
  });

  it('renders prompts list', async () => {
    renderQuestionSheet();
    await waitFor(() => {
      expect(screen.getByText('С чего начать поиск квартиры?')).toBeInTheDocument();
    });
    expect(screen.getByText('Как рассчитать бюджет?')).toBeInTheDocument();
  });

  it('calls sendData.ifAvailable on prompt click', async () => {
    const sendDataMock = sdkReact.sendData as unknown as ReturnType<typeof vi.fn> & {
      ifAvailable: ReturnType<typeof vi.fn>;
    };

    renderQuestionSheet();
    await waitFor(() => screen.getByText('С чего начать поиск квартиры?'));
    fireEvent.click(screen.getByText('С чего начать поиск квартиры?'));

    expect(sendDataMock.ifAvailable).toHaveBeenCalledWith('С чего начать поиск квартиры?');
  });

  it('calls miniApp.close.ifAvailable on prompt click', async () => {
    const miniAppMock = sdkReact.miniApp as unknown as {
      close: ReturnType<typeof vi.fn> & { ifAvailable: ReturnType<typeof vi.fn> };
    };

    renderQuestionSheet();
    await waitFor(() => screen.getByText('С чего начать поиск квартиры?'));
    fireEvent.click(screen.getByText('С чего начать поиск квартиры?'));

    expect(miniAppMock.close.ifAvailable).toHaveBeenCalled();
  });

  it('renders not found state for unknown question id', async () => {
    renderQuestionSheet('/question/missing');

    await waitFor(() => {
      expect(screen.getByText('Вопрос не найден')).toBeInTheDocument();
    });
  });

  it('renders error state when config fails to load', async () => {
    vi.spyOn(api, 'fetchConfig').mockRejectedValue(new Error('network error'));

    renderQuestionSheet();

    await waitFor(() => {
      expect(screen.getByText('Не удалось загрузить вопросы')).toBeInTheDocument();
    });
  });
});
