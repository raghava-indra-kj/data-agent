import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from './AppShell';
vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { email: 'user@example.com', display_name: 'Alex' }, signOut: vi.fn() }),
}));
vi.mock('../organizations/OrganizationProvider', () => ({
  useOrganization: () => ({
    organizations: [{ id: 'org-1', name: 'Acme' }],
    activeOrganization: { id: 'org-1', name: 'Acme' },
    setActiveOrganization: vi.fn(),
  }),
}));
const mockConversations = vi.hoisted(() => ({
  list: [{ id: 'c1', title: 'Revenue analysis' }],
  deleteAll: vi.fn().mockResolvedValue(undefined),
  search: vi.fn(),
}));
vi.mock('../conversations/hooks/useConversations', () => ({
  useConversationList: (search: string) => {
    mockConversations.search(search);
    return { conversations: mockConversations.list, hasNextPage: false };
  },
  useDeleteConversation: () => ({ mutate: vi.fn() }),
  useDeleteAllConversations: () => ({
    mutate: mockConversations.deleteAll,
    mutateAsync: mockConversations.deleteAll,
    isPending: false,
  }),
}));
describe('AppShell', () => {
  beforeEach(() => localStorage.clear());

  it('exposes desktop and mobile navigation controls semantically', () => {
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/ask" element={<div>Ask content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open navigation' })).toBeInTheDocument();
    expect(screen.getByText('Ask content')).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^Ask$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show recent chats' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'More navigation' })).toBeInTheDocument();
  });

  it('keeps less frequent tools accessible from More', async () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/settings" element={<div>Settings content</div>} />
            <Route path="/skills" element={<div>Templates content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.setup().click(screen.getByRole('button', { name: 'More navigation' }));
    await userEvent.setup().click(screen.getByRole('menuitem', { name: /^Templates$/ }));
    expect(screen.getByText('Templates content')).toBeInTheDocument();
    expect(screen.queryByText('AI Instructions & Commands')).not.toBeInTheDocument();
  });

  it('searches chat history on the server after the user pauses typing', async () => {
    const user = userEvent.setup();
    mockConversations.search.mockClear();
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/ask" element={<div>Ask content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await user.type(screen.getByRole('textbox', { name: 'Search conversation history' }), ' rev ');
    await waitFor(() => expect(mockConversations.search).toHaveBeenLastCalledWith('rev'));
    expect(mockConversations.search).not.toHaveBeenCalledWith(' r');
  });

  it('hides and restores chat history while persisting the collapsed state', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/ask" element={<div>Ask content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('textbox', { name: 'Search conversation history' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(screen.queryByText('Recent chats')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Search conversation history')).not.toBeInTheDocument();
    expect(localStorage.getItem('db-assistant.preferences.v1')).toContain(
      '"navigationCollapsed":true',
    );

    await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(screen.getByText('Recent chats')).toBeInTheDocument();
    expect(screen.getByLabelText('Search conversation history')).toBeInTheDocument();
  });

  it('opens delete all chats confirmation dialog and triggers deletion', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/conversations/c1']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/conversations/:id" element={<div>Conversation view</div>} />
            <Route path="/ask" element={<div>Ask view</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const deleteAllBtn = screen.getByRole('button', { name: 'Delete all chats' });
    expect(deleteAllBtn).toBeInTheDocument();
    await user.hover(deleteAllBtn);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Delete all chats');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    await user.click(deleteAllBtn);

    expect(screen.getByRole('dialog', { name: 'Delete all chats' })).toBeInTheDocument();
    expect(
      screen.getByText(/All chats and their message history in this workspace will be permanently deleted/),
    ).toBeInTheDocument();

    const confirmBtns = screen.getAllByRole('button', { name: 'Delete all chats' });
    const modalConfirmBtn = confirmBtns[confirmBtns.length - 1];
    await user.click(modalConfirmBtn!);
    expect(mockConversations.deleteAll).toHaveBeenCalled();
  });
});
