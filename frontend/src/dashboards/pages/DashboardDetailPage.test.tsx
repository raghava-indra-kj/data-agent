import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagedJob } from '../../jobs/types';
import { server } from '../../test/server';

const manager = vi.hoisted(() => ({ jobs: [] as ManagedJob[], registerJob: vi.fn(async () => undefined) }));
vi.mock('../../organizations/OrganizationProvider', () => ({ useOrganization: () => ({ activeOrganization: { id: 'org-1', name: 'Org', role: 'owner' } }) }));
vi.mock('../../jobs/JobManagerProvider', () => ({ useJobManager: () => ({ jobs: manager.jobs, registerJob: manager.registerJob, activeJobs: [], isLoading: false, cancel: vi.fn(), latestEvent: () => undefined, currentLabel: () => null }) }));
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts"/> }));

import { DashboardDetailPage } from './DashboardDetailPage';

const source = { id: 'ds1', organization_id: 'org-1', name: 'Warehouse', kind: 'postgres', display_type: 'postgres', status: 'active', config: {}, created_by: 'u1', last_tested_at: null, last_error_code: null, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z', active_file: null };
function widget(id: string, field: string, value: number) { return { id, dashboard_id: 'd1', data_source_id: 'ds1', title: field, widget_type: 'metric', question: `What is ${field}?`, sql_text: `select ${field} from metrics`, visualization_config: { field }, layout_config: { columns: 3, rows: 1 }, created_from_job_id: `j-${id}`, created_from_sql_execution_id: `s-${id}`, last_refresh_job_id: null, last_refreshed_at: null, enabled: true, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z', latest_artifact: { id: `a-${id}`, kind: 'table', name: field, created_at: '2026-08-24T12:00:00Z', payload: { schema_version: 1, data_source_id: 'ds1', columns: [field], rows: [[value]], row_count: 1, truncated: false } } }; }
let detail = { id: 'd1', organization_id: 'org-1', title: 'Executive', description: 'Core metrics', created_by: 'u1', widget_count: 2, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z', widgets: [widget('w1', 'revenue', 100), widget('w2', 'orders', 200)] };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboards/d1']}><Routes><Route path="/dashboards/:dashboardId" element={<DashboardDetailPage/>}/><Route path="/dashboards" element={<div>Dashboards list</div>}/></Routes></MemoryRouter></QueryClientProvider>);
  return client;
}
function handlers() {
  server.use(
    http.get('http://localhost:12201/api/v1/dashboards/d1', () => HttpResponse.json(detail)),
    http.get('http://localhost:12201/api/v1/data-sources', () => HttpResponse.json([source])),
  );
}

describe('DashboardDetailPage', () => {
  beforeEach(() => { manager.jobs = []; manager.registerJob.mockClear(); detail = { ...detail, title: 'Executive' }; handlers(); });

  it('edits dashboard metadata and refetches the durable dashboard', async () => {
    server.use(http.patch('http://localhost:12201/api/v1/dashboards/d1', async ({ request }) => {
      const body = await request.json() as { title: string; description: string | null };
      detail = { ...detail, title: body.title, description: body.description ?? '' };
      return HttpResponse.json(detail);
    }));
    renderPage();
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Edit dashboard' }));
    const title = screen.getByLabelText('Title');
    await userEvent.setup().clear(title); await userEvent.setup().type(title, 'Operations');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Save dashboard' }));
    expect(await screen.findByRole('heading', { name: 'Operations' })).toBeInTheDocument();
  });

  it('registers widget refresh jobs globally while retaining the previous visualization', async () => {
    server.use(http.post('http://localhost:12201/api/v1/dashboards/widgets/w1/refresh', () => HttpResponse.json({ job_id: 'jr1' }, { status: 202 })));
    renderPage();
    expect(await screen.findByText('100')).toBeInTheDocument();
    await userEvent.setup().click(screen.getAllByRole('button', { name: 'Refresh' })[0]!);
    await waitFor(() => expect(manager.registerJob).toHaveBeenCalledWith('jr1'));
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('isolates a failed widget refresh and keeps other widgets rendered', async () => {
    manager.jobs = [{ job: { id: 'jr1', organization_id: 'org-1', job_type: 'dashboard_refresh', status: 'failed', requested_by: 'u1', conversation_id: null, input: { widget_id: 'w1' }, result: null, attempt_count: 1, max_attempts: 3, cancel_requested_at: null, error_code: 'SQL_QUERY_TIMEOUT', error_message: 'Refresh query timed out.', created_at: '2026-08-24T12:05:00Z', started_at: '2026-08-24T12:05:00Z', finished_at: '2026-08-24T12:05:02Z' }, events: [], lastSeenSequence: 0, connectionState: 'closed' }];
    renderPage();
    expect(await screen.findByText('Refresh query timed out.')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
  });
});
