import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

const createConversation = vi.hoisted(() => vi.fn());
vi.mock('../../settings/hooks/useInstructions', () => ({ useInstructions: () => ({ data: [] }) }));

vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { display_name: 'Alex', email: 'alex@example.com' } }),
}));
vi.mock('../../organizations/OrganizationProvider', () => ({
  useOrganization: () => ({ activeOrganization: { id: 'org1' } }),
}));
vi.mock('../../data-sources/api/data-source-api', () => ({
  listSourceTables: async () => ({ knowledge_version_id: 'v1', items: [{ schema: 'dbo', name: 'orders', object_type: 'table', column_count: 4 }], next_cursor: null }),
  listDataSources: async () => [
    {
      id: 'ds1',
      organization_id: 'org1',
      name: 'Warehouse',
      kind: 'postgres',
      display_type: 'postgres',
      status: 'active',
      config: {},
      created_by: 'u1',
      last_tested_at: null,
      last_error_code: null,
      created_at: '2026-08-24T12:00:00Z',
      updated_at: '2026-08-24T12:00:00Z',
      active_file: null,
    },
  ],
}));
vi.mock('../../models/api/models-api', () => ({ listProfiles: async () => [] }));
vi.mock('../api/conversation-api', () => ({ createConversation }));

import { AskPage } from './AskPage';

describe('new analysis screen', () => {
  it('shows the message returned by the API when a source is unavailable', async () => {
    createConversation.mockRejectedValueOnce({
      code: 'POWER_BI_TENANT_MISMATCH',
      message: 'This Power BI source belongs to a different Microsoft tenant.',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><MemoryRouter><AskPage /></MemoryRouter></QueryClientProvider>);
    await screen.findByRole('button', { name: 'Data scope' });
    await user.type(screen.getByRole('textbox', { name: 'Ask a question' }), 'Show revenue');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    expect(await screen.findByText('This Power BI source belongs to a different Microsoft tenant.'))
      .toBeInTheDocument();
  });

  it('sends applied table selection when starting a conversation', async () => {
    createConversation.mockClear();
    createConversation.mockResolvedValue({ id: 'c2' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><MemoryRouter><AskPage /></MemoryRouter></QueryClientProvider>);
    await user.click(await screen.findByRole('button', { name: 'Data scope' }));
    await user.click(await screen.findByRole('radio', { name: 'Choose tables' }));
    await user.click(await screen.findByRole('checkbox', { name: /orders/ }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('button', { name: 'Data scope' })).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask a question' }), 'Count orders');
    await user.click(screen.getByRole('button', { name: 'Send question' }));
    await waitFor(() => expect(createConversation).toHaveBeenCalledWith({
      data_source_ids: ['ds1'], model_profile_id: null, title: 'Count orders',
      table_scope: [{ data_source_id: 'ds1', mode: 'selected', tables: [{ schema: 'dbo', name: 'orders' }] }],
    }));
  });

  it('restores applied tables in a new Ask session and remembers an explicit return to all tables', async () => {
    const showPage = () => render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><AskPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    showPage();
    await user.click(await screen.findByRole('button', { name: 'Data scope' }));
    await user.click(await screen.findByRole('radio', { name: 'Choose tables' }));
    await user.click(await screen.findByRole('checkbox', { name: /orders/ }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    cleanup();
    showPage();

    await user.click(await screen.findByRole('button', { name: 'Data scope' }));
    expect(await screen.findByRole('checkbox', { name: /orders/ })).toBeChecked();
    // Cancelled changes do not overwrite the remembered selection.
    await user.click(screen.getByRole('radio', { name: 'All tables' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    cleanup();
    showPage();
    await user.click(await screen.findByRole('button', { name: 'Data scope' }));
    await user.click(screen.getByRole('radio', { name: 'All tables' }));
    await user.click(screen.getByRole('button', { name: 'Done' }));
    cleanup();
    showPage();
    expect(await screen.findByRole('button', { name: 'Data scope' })).toBeInTheDocument();
  });
  it('centers a personal welcome and fixes the chosen source when creating the conversation', async () => {
    createConversation.mockResolvedValue({ id: 'c1' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/ask']}>
          <Routes>
            <Route path="/ask" element={<AskPage />} />
            <Route path="/conversations/:conversationId" element={<div>Conversation started</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Hi Alex')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'What would you like to know about your data?' }),
    ).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: 'Ask a question' }), 'Show revenue');
    expect(screen.queryByText('Warehouse')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Data scope' }));
    expect(screen.getByRole('button', { name: /Warehouse/ })).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Send question' }));

    await waitFor(() =>
      expect(createConversation).toHaveBeenCalledWith({
        data_source_ids: ['ds1'],
        table_scope: [{ data_source_id: 'ds1', mode: 'all', tables: [] }],
        model_profile_id: null,
        title: 'Show revenue',
      }),
    );
    expect(await screen.findByText('Conversation started')).toBeInTheDocument();
  });
});
