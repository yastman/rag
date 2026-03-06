import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { BottomSheet } from '../BottomSheet';

describe('BottomSheet', () => {
  const defaultProps = {
    emoji: '🏠',
    title: 'Покупка квартиры',
    description: 'Помощь с покупкой',
    onClose: vi.fn(),
  };

  it('renders children', () => {
    render(
      <BottomSheet {...defaultProps}>
        <div>Содержимое</div>
      </BottomSheet>,
    );
    expect(screen.getByText('Содержимое')).toBeInTheDocument();
  });

  it('renders title and description', () => {
    render(
      <BottomSheet {...defaultProps}>
        <span />
      </BottomSheet>,
    );
    expect(screen.getByText('Покупка квартиры')).toBeInTheDocument();
    expect(screen.getByText('Помощь с покупкой')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', async () => {
    const onClose = vi.fn();
    render(
      <BottomSheet {...defaultProps} onClose={onClose}>
        <span />
      </BottomSheet>,
    );
    await userEvent.click(screen.getByText('x'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
