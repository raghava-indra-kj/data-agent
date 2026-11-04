import { describe, expect, it } from 'vitest';
import type { ExecutionTrace } from '../api/execution-api';
import { normalizeTrace } from './normalize-trace';

const base = {
  tools: [
    { id: 't2', job_id: 'j1', sequence: 4, tool_name: 'future_tool', status: 'succeeded', input_summary: {}, output_summary: null, error_code: null, error_message: null, started_at: '2026-08-24T12:00:04Z', finished_at: null },
    { id: 't1', job_id: 'j1', sequence: 2, tool_name: 'execute_sql', status: 'succeeded', input_summary: {}, output_summary: null, error_code: null, error_message: null, started_at: '2026-08-24T12:00:02Z', finished_at: null },
  ],
  sql: [{ id: 's1', tool_execution_id: 't1', data_source_id: 'ds1', sql_text: 'select 1', status: 'succeeded', row_count: 1, truncated: false, columns: ['x'], result_bytes: 2, duration_ms: 5, error_code: null, error_message: null, started_at: '2026-08-24T12:00:02.100Z', finished_at: '2026-08-24T12:00:02.200Z' }],
  models: [{ id: 'm1', job_id: 'j1', sequence: 1, model_profile_id: 'mp1', model_name: 'model', phase: 'analysis', status: 'succeeded', input_tokens: null, output_tokens: null, total_tokens: null, error_code: null, error_message: null, started_at: '2026-08-24T12:00:01Z', finished_at: null }],
  artifacts: [],
} satisfies ExecutionTrace;

describe('normalizeTrace', () => {
  it('orders arbitrary model/tool/SQL records chronologically by persisted sequence relationships', () => {
    expect(normalizeTrace(base).map((item) => `${item.kind}:${item.record.id}`)).toEqual(['model:m1', 'tool:t1', 'sql:s1', 'tool:t2']);
  });

  it('keeps unknown future tool names as generic tool records', () => {
    const unknown = normalizeTrace(base).find((item) => item.kind === 'tool' && item.record.id === 't2');
    expect(unknown?.kind === 'tool' && unknown.record.tool_name).toBe('future_tool');
  });
});
