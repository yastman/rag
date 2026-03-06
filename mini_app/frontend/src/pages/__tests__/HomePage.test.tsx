import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { HomePage } from '../HomePage';
import * as api from '../../api';
import type { AppConfig } from '../../types';

const mockConfig: AppConfig = {
  questions: [
    { id: 'q1', emoji: '🏠', title: 'Купить квартиру', description: 'Desc', prompts: [] },
    { id: 'q2', emoji: '📋', title: 'Ипотека', description: 'Desc2', prompts: [] },
  ],
  experts: [
    {
      id: 'e1',
      emoji: '👨‍💼',
      name: 'Эксперт Иванов',
      description: 'Специалист',
      system_prompt_key: 'key',
      cta_text: 'Позвонить',
      cta_source: 'expert',
      prompts: [],
    },
  ],
};

describe('HomePage', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchConfig').mockResolvedValue(mockConfig);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading indicator while config is pending', () => {
    vi.spyOn(api, 'fetchConfig').mockReturnValue(new Promise(() => {}));
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    expect(screen.getByText('Загрузка...')).toBeInTheDocument();
  });

  it('renders empty lists on fetch error', async () => {
    vi.spyOn(api, 'fetchConfig').mockRejectedValue(new Error('network error'));
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.queryByText('Загрузка...')).not.toBeInTheDocument();
    });
  });

  it('renders questions and experts after fetch', async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Купить квартиру')).toBeInTheDocument();
    });

    expect(screen.getByText('Ипотека')).toBeInTheDocument();
    expect(screen.getByText('Эксперт Иванов')).toBeInTheDocument();
    expect(api.fetchConfig).toHaveBeenCalled();
  });
});
