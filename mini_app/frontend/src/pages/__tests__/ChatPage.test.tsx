import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ChatPage } from '../ChatPage';
import * as api from '../../api';

async function* mockStream() {
  yield { type: 'chunk', text: 'Привет' };
  yield { type: 'done', full_text: 'Привет!' };
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.spyOn(api, 'streamChat').mockImplementation(() => mockStream());
  });

  const renderChatPage = (search = '') =>
    render(
      <MemoryRouter initialEntries={[`/chat${search}`]}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

  it('renders chat input', () => {
    renderChatPage();
    expect(screen.getByPlaceholderText('Спросить что-нибудь...')).toBeInTheDocument();
  });

  it('sends message on submit', async () => {
    renderChatPage();
    const input = screen.getByPlaceholderText('Спросить что-нибудь...');
    await userEvent.type(input, 'Как купить квартиру?');
    await userEvent.click(screen.getByRole('button'));
    expect(api.streamChat).toHaveBeenCalledWith('Как купить квартиру?', 0, undefined);
    expect(await screen.findByText('Как купить квартиру?')).toBeInTheDocument();
  });
});
