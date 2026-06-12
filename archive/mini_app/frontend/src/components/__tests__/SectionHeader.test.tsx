import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { SectionHeader } from '../SectionHeader';

describe('SectionHeader', () => {
  it('renders title text', () => {
    render(<SectionHeader title="Вопросы" />);
    expect(screen.getByText('Вопросы')).toBeInTheDocument();
  });

  it('does not show "Показать все" when onShowAll is not provided', () => {
    render(<SectionHeader title="Вопросы" />);
    expect(screen.queryByText('Показать все')).not.toBeInTheDocument();
  });

  it('shows "Показать все" and calls onShowAll when clicked', async () => {
    const onShowAll = vi.fn();
    render(<SectionHeader title="Вопросы" onShowAll={onShowAll} />);
    const btn = screen.getByText('Показать все');
    expect(btn).toBeInTheDocument();
    await userEvent.click(btn);
    expect(onShowAll).toHaveBeenCalled();
  });
});
