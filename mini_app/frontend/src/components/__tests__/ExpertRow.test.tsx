import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ExpertRow } from '../ExpertRow';
import type { Expert } from '../../types';

const expert: Expert = {
  id: 'e1',
  emoji: '👨‍💼',
  name: 'Иван Иванов',
  description: 'Специалист по ипотеке',
  system_prompt_key: 'mortgage',
  cta_text: 'Позвонить',
  cta_source: 'expert',
  prompts: [],
};

describe('ExpertRow', () => {
  it('renders expert name and role', () => {
    render(<ExpertRow expert={expert} onClick={vi.fn()} />);
    expect(screen.getByText('Иван Иванов')).toBeInTheDocument();
    expect(screen.getByText('Специалист по ипотеке')).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn();
    render(<ExpertRow expert={expert} onClick={onClick} />);
    await userEvent.click(screen.getByText('Иван Иванов'));
    expect(onClick).toHaveBeenCalledWith(expert);
  });
});
