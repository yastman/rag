import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
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

  it('redirects unknown routes to HomePage (wildcard fallback)', async () => {
    // Simulate Telegram Desktop opening URL without hash fragment
    window.location.hash = '#/nonexistent-path';
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Загрузка...')).toBeInTheDocument();
    });
    expect(window.location.hash).toBe('#/');
  });
});
