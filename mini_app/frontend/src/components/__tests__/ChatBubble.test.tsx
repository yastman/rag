import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ChatBubble } from '../ChatBubble';

describe('ChatBubble', () => {
  it('renders user message with correct alignment', () => {
    const { container } = render(<ChatBubble role="user" text="Привет!" />);
    expect(screen.getByText('Привет!')).toBeInTheDocument();
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.justifyContent).toBe('flex-end');
  });

  it('renders assistant message with correct alignment', () => {
    const { container } = render(<ChatBubble role="assistant" text="Здравствуйте!" />);
    expect(screen.getByText('Здравствуйте!')).toBeInTheDocument();
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.justifyContent).toBe('flex-start');
  });
});
