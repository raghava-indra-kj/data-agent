import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { DashboardWidget } from '../api/dashboard-api';
import { WidgetProvenance } from './WidgetProvenance';

const widget: DashboardWidget = { id: 'w1', dashboard_id: 'd1', data_source_id: 'ds1', title: 'Revenue', widget_type: 'metric', question: 'What is revenue?', sql_text: 'SELECT revenue FROM metrics', visualization_config: { field: 'revenue' }, layout_config: {}, created_from_job_id: 'j1', created_from_sql_execution_id: 's1', last_refresh_job_id: null, last_refreshed_at: '2026-08-24T12:00:00Z', enabled: true, created_at: '2026-08-24T12:00:00Z', updated_at: '2026-08-24T12:00:00Z', latest_artifact: null };

describe('WidgetProvenance', () => {
  it('exposes question, datasource, SQL, originating job and copy action', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    render(<MemoryRouter><WidgetProvenance widget={widget} dataSourceName="Warehouse"/></MemoryRouter>);
    await user.click(screen.getByText('View source'));
    expect(screen.getByText('What is revenue?')).toBeInTheDocument();
    expect(screen.getByText('Warehouse')).toBeInTheDocument();
    expect(screen.getByText('SELECT revenue FROM metrics')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View job' })).toHaveAttribute('href', '/jobs/j1');
    await user.click(screen.getByRole('button', { name: 'Copy SQL' }));
    expect(writeText).toHaveBeenCalledWith('SELECT revenue FROM metrics');
  });
});
