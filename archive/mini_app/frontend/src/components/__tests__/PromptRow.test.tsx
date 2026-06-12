import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { PromptRow } from '../PromptRow';
import type { Prompt } from '../../types';

const prompt: Prompt = {
  emoji: '💡',
  text: 'Как оформить ипотеку?',
};

describe('PromptRow', () => {
  it('renders prompt text and emoji', () => {
    render(<PromptRow prompt={prompt} onClick={vi.fn()} />);
    expect(screen.getByText('Как оформить ипотеку?')).toBeInTheDocument();
    expect(screen.getByText('💡')).toBeInTheDocument();
  });

  it('calls onClick with prompt text when clicked', async () => {
    const onClick = vi.fn();
    render(<PromptRow prompt={prompt} onClick={onClick} />);
    await userEvent.click(screen.getByText('Как оформить ипотеку?'));
    expect(onClick).toHaveBeenCalledWith('Как оформить ипотеку?');
  });
});
