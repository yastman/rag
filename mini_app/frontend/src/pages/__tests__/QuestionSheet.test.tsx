import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QuestionSheet } from '../QuestionSheet';
import * as api from '../../api';
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

  const renderQuestionSheet = () =>
    render(
      <MemoryRouter initialEntries={['/question/purchase']}>
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
});
