import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ChatInput } from '../ChatInput';

describe('ChatInput', () => {
  it('renders input and send button', () => {
    render(<ChatInput onSend={vi.fn()} />);
    expect(screen.getByPlaceholderText('Спросить что-нибудь...')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('calls onSend with input value when button clicked', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);
    const input = screen.getByPlaceholderText('Спросить что-нибудь...');
    await userEvent.type(input, 'Привет');
    await userEvent.click(screen.getByRole('button'));
    expect(onSend).toHaveBeenCalledWith('Привет');
  });

  it('clears input after send', async () => {
    render(<ChatInput onSend={vi.fn()} />);
    const input = screen.getByPlaceholderText('Спросить что-нибудь...');
    await userEvent.type(input, 'Текст');
    await userEvent.click(screen.getByRole('button'));
    expect(input).toHaveValue('');
  });

  it('does not call onSend when input is empty or whitespace', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onSend).not.toHaveBeenCalled();
  });
});
