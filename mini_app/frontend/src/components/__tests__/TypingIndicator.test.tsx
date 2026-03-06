import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TypingIndicator } from '../TypingIndicator';

describe('TypingIndicator', () => {
  it('renders typing dots', () => {
    render(<TypingIndicator />);
    expect(screen.getByText('...')).toBeInTheDocument();
  });

  it('renders with typing-dots class', () => {
    render(<TypingIndicator />);
    const dots = screen.getByText('...');
    expect(dots).toHaveClass('typing-dots');
  });
});
