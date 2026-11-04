import type { JobEvent } from '../types';
export function parseJobEvent(data: string): JobEvent | null {
  try {
    const value: unknown = JSON.parse(data);
    if (!value || typeof value !== 'object') return null;
    const candidate = value as Record<string, unknown>;
    if (
      typeof candidate.sequence !== 'number' ||
      typeof candidate.event_type !== 'string' ||
      typeof candidate.level !== 'string' ||
      typeof candidate.created_at !== 'string' ||
      !candidate.payload ||
      typeof candidate.payload !== 'object' ||
      Array.isArray(candidate.payload)
    ) {
      return null;
    }
    return {
      sequence: candidate.sequence,
      event_type: candidate.event_type,
      level: candidate.level,
      payload: candidate.payload as Record<string, unknown>,
      created_at: candidate.created_at,
    };
  } catch {
    return null;
  }
}
export function appendJobEvent(events: JobEvent[], next: JobEvent): JobEvent[] {
  if (events.some((event) => event.sequence === next.sequence)) return events;
  return [...events, next].sort((a, b) => a.sequence - b.sequence);
}
const exactLabels: Record<string, string> = {
  'job.queued': 'Waiting to start',
  'job.started': 'Ready to begin',
  'job.completed': 'Completed',
  'job.failed': 'Failed',
  'job.cancelled': 'Cancelled',
  'datasource.test.started': 'Testing data source…',
  'datasource.test.completed': 'Data source test completed',
  'excel.materialization.started': 'Creating analytical database…',
  'excel.database.created': 'Analytical database created',
  'datasource.ready': 'Data source ready',
  'knowledge.generation.started': 'Generating knowledge…',
  'knowledge.schema.inspected': 'Schema inspected',
  'knowledge.index.generated': 'Knowledge index generated',
  'knowledge.documents.generated': 'Knowledge documents generated',
  'knowledge.generation.completed': 'Knowledge ready',
  'knowledge.index.loaded': 'Reviewing your data guide…',
  'knowledge.schema.loaded': 'Checking your table structure…',
  'agent.started': 'Starting your analysis…',
  'analysis.completed': 'Analysis complete',
  'model.request.started': 'Analyzing…',
  'model.request.completed': 'Analysis step completed',
  'tool.started': 'Working on your request…',
  'tool.completed': 'Step complete',
  'sql.started': 'Retrieving the data…',
  'sql.completed': 'Data retrieved',
  'dax.started': 'Querying the Power BI model…',
  'dax.completed': 'Power BI data retrieved',
  'dax.failed': 'Power BI query did not complete',
  'chart.generated': 'Chart ready',
  'answer.generated': 'Answer generated',
  'finalization.started': 'Putting your answer together…',
  'finalization.repair_started': 'Refining final answer…',
  'finalization.quality_warning': 'Answer ready with formatting warnings',
  'finalization.completed': 'Final answer ready',
  'finalization.invalid': 'Final answer validation failed',
  'dashboard.widget.refreshed': 'Dashboard widget refreshed',
};
function safeShortLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) return null;
  return normalized.length > 80 ? `${normalized.slice(0, 77)}…` : normalized;
}
export function getSafeJobEventLabel(event?: JobEvent): string | null {
  if (!event) return null;
  const exact = exactLabels[event.event_type];
  if (exact) return exact;
  if (event.event_type === 'excel.sheet.started') {
    const name = safeShortLabel(event.payload.sheet_name);
    return name ? `Importing ${name}…` : 'Importing worksheet…';
  }
  if (event.event_type === 'excel.sheet.completed') {
    const name = safeShortLabel(event.payload.sheet_name);
    return name ? `Imported ${name}` : 'Worksheet imported';
  }
  if (event.event_type.startsWith('knowledge.')) return 'Updating knowledge…';
  if (event.event_type.startsWith('excel.')) return 'Processing workbook…';
  if (event.event_type.startsWith('datasource.')) return 'Processing data source…';
  if (event.event_type.startsWith('job.')) return 'Updating job…';
  if (event.event_type.startsWith('model.request.')) return 'Analyzing…';
  if (event.event_type.startsWith('tool.')) return 'Working on your request…';
  if (event.event_type.startsWith('sql.')) return 'Retrieving the data…';
  if (event.event_type.startsWith('agent.')) return 'Running analysis…';
  if (event.event_type.startsWith('analysis.')) return 'Validating analysis…';
  if (event.event_type.startsWith('finalization.')) return 'Putting your answer together…';
  if (event.event_type.startsWith('dashboard.')) return 'Refreshing dashboard…';
  return null;
}
