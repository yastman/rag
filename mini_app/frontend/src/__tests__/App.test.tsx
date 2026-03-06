import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { App } from '../App';
import * as api from '../api';

describe('App', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchConfig').mockResolvedValue({ questions: [], experts: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders HomePage at root route', () => {
    render(<App />);
    // HomePage renders a loading indicator while fetching config
    expect(screen.getByText('Загрузка...')).toBeInTheDocument();
  });

  it('applies CSS fallback background color', () => {
    const { container } = render(<App />);
    const wrapper = container.firstChild as HTMLElement;
    // App wraps routes in a div with inline style background fallback
    expect(wrapper.style.background).toContain('#ffffff');
  });
});
