import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ExpertSheet } from '../ExpertSheet';
import * as api from '../../api';
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
});
