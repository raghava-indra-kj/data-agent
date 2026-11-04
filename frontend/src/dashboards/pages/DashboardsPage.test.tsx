import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../../test/server';

vi.mock('../../organizations/OrganizationProvider', () => ({ useOrganization: () => ({ activeOrganization: { id: 'org-1', name: 'Org', role: 'owner' } }) }));

import { DashboardsPage } from './DashboardsPage';

let dashboards: Array<Record<string, unknown>> = [];
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboards']}><DashboardsPage/></MemoryRouter></QueryClientProvider>);
}

describe('DashboardsPage', () => {
  beforeEach(() => {
    dashboards = [];
    server.use(
      http.get('http://localhost:12201/api/v1/dashboards', () => HttpResponse.json(dashboards)),
      http.post('http://localhost:12201/api/v1/dashboards', async ({ request }) => {
        const body = await request.json() as { title: string; description?: string | null };
        const created = { id: 'd1', organization_id: 'org-1', title: body.title, description: body.description ?? null, created_by: 'u1', widget_count: 0, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z' };
        dashboards = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
  });

  it('renders the deliberate empty state', async () => {
    renderPage();
    expect(await screen.findByText('No dashboards yet')).toBeInTheDocument();
  });

  it('creates a simple dashboard without an oversized modal workflow', async () => {
    renderPage();
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Create your first dashboard' }));
    await userEvent.setup().type(screen.getByLabelText('Title'), 'Operations');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Create dashboard' }));
    expect(await screen.findByRole('link', { name: 'Operations' })).toHaveAttribute('href', '/dashboards/d1');
  });
});
