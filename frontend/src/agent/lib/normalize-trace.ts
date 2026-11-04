import type { DaxExecution, ExecutionTrace, ModelExecution, SqlExecution, ToolExecution } from '../api/execution-api';

export type TraceEntry =
  | { kind: 'tool'; sequence: number; startedAt: string; record: ToolExecution }
  | { kind: 'sql'; sequence: number; startedAt: string; record: SqlExecution }
  | { kind: 'dax'; sequence: number; startedAt: string; record: DaxExecution }
  | { kind: 'model'; sequence: number; startedAt: string; record: ModelExecution };

export function normalizeTrace(trace: ExecutionTrace): TraceEntry[] {
  const toolSequence = new Map((trace.tools ?? []).map((item) => [item.id, item.sequence]));
  const entries: TraceEntry[] = [
    ...(trace.dax ?? []).map((record) => ({ kind: 'dax' as const, sequence: (toolSequence.get(record.tool_execution_id) ?? 0) * 10 + 1, startedAt: record.started_at, record })),
    ...(trace.tools ?? []).map((record) => ({ kind: 'tool' as const, sequence: record.sequence * 10, startedAt: record.started_at, record })),
    ...(trace.sql ?? []).map((record) => { const tool = toolSequence.get(record.tool_execution_id); return { kind: 'sql' as const, sequence: tool == null ? Number.MAX_SAFE_INTEGER : tool * 10 + 1, startedAt: record.started_at, record }; }),
    ...(trace.models ?? []).map((record) => ({ kind: 'model' as const, sequence: record.sequence * 10 + 2, startedAt: record.started_at, record })),
  ];
  return entries.sort((a, b) => Date.parse(a.startedAt) - Date.parse(b.startedAt) || a.sequence - b.sequence);
}
