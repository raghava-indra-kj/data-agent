import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SqlExecutionBlock } from './SqlExecutionBlock';

describe('SQL execution block', () => {
  it('shows truncation metadata and copies only the SQL text', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText');
    render(<SqlExecutionBlock dataSourceName="Warehouse" execution={{ id: 's1', tool_execution_id: 't1', data_source_id: 'ds1', sql_text: 'SELECT * FROM orders', status: 'succeeded', row_count: 1000, truncated: true, columns: ['id'], result_bytes: 2048, duration_ms: 183, error_code: null, error_message: null, started_at: '2026-08-24T12:00:00Z', finished_at: '2026-08-24T12:00:01Z' }}/>);
    expect(screen.getByText('Truncated')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith('SELECT * FROM orders');
  });
});
