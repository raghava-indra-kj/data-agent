import type { ExecutionTrace } from '../api/execution-api';
import { normalizeTrace } from '../lib/normalize-trace';
import { JobUsageSummary } from './JobUsageSummary';
import { ModelExecutionCard } from './ModelExecutionCard';
import { SqlExecutionBlock } from './SqlExecutionBlock';
import { ToolExecutionCard } from './ToolExecutionCard';

export function ExecutionTimeline({
  trace,
  dataSourceNames = {},
}: {
  trace: ExecutionTrace;
  dataSourceNames?: Record<string, string>;
}) {
  const allEntries = normalizeTrace(trace);
  const entries = allEntries.slice(0, 500);

  if (!entries.length) {
    return (
      <div className="p-3 text-center text-xs text-[var(--db-text-muted)] bg-[var(--db-surface-muted)] rounded-lg border border-[var(--db-border-default)]">
        No persisted execution records are available for this job.
      </div>
    );
  }

  return (
    <div className="execution-timeline space-y-2 mt-2" aria-label="Execution trace">
      <JobUsageSummary models={trace.models ?? []} />
      {allEntries.length > entries.length ? (
        <p className="text-[11px] text-[var(--db-text-muted)] mb-2" role="status">
          Showing the first 500 persisted execution records.
        </p>
      ) : null}

      <div className="space-y-1.5">
        {entries.map((entry) => {
          if (entry.kind === 'dax') return <details key={`dax:${entry.record.id}`} className="p-3 border border-[var(--db-border-default)] rounded">
            <summary>Power BI query · {entry.record.status} · {entry.record.row_count ?? 0} rows</summary>
            <p>{dataSourceNames[entry.record.data_source_id] ?? 'Power BI'}</p>
            {entry.record.truncated && <p role="status">This result is truncated.</p>}
            {entry.record.error_message && <p role="alert">{entry.record.error_message}</p>}
            <pre aria-label="DAX query" className="overflow-auto"><code>{entry.record.dax_text}</code></pre>
          </details>;
          if (entry.kind === 'tool') {
            return (
              <ToolExecutionCard
                key={`tool:${entry.record.id}`}
                execution={entry.record}
              />
            );
          }
          if (entry.kind === 'sql') {
            return (
              <SqlExecutionBlock
                key={`sql:${entry.record.id}`}
                execution={entry.record}
                dataSourceName={
                  dataSourceNames[entry.record.data_source_id] ?? 'Data source'
                }
              />
            );
          }
          return (
            <ModelExecutionCard
              key={`model:${entry.record.id}`}
              execution={entry.record}
            />
          );
        })}
      </div>
    </div>
  );
}
