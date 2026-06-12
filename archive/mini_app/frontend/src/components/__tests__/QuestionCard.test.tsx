import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QuestionCard } from '../QuestionCard';
import type { Question } from '../../types';

const question: Question = {
  id: 'q1',
  emoji: '🏠',
  title: 'Как купить квартиру?',
  description: 'Описание',
  prompts: [],
};

describe('QuestionCard', () => {
  it('renders question title and emoji', () => {
    render(<QuestionCard question={question} onClick={vi.fn()} />);
    expect(screen.getByText('Как купить квартиру?')).toBeInTheDocument();
    expect(screen.getByText('🏠')).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn();
    render(<QuestionCard question={question} onClick={onClick} />);
    await userEvent.click(screen.getByText('Как купить квартиру?'));
    expect(onClick).toHaveBeenCalledWith(question);
  });
});
