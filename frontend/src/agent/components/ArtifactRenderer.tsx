import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { BookmarkPlus } from 'lucide-react';
import type { JobArtifact, QueryExecution } from '../api/execution-api';
import { AnalyticalTable } from '../../analytics/table/AnalyticalTable';
import type { AnalyticalTableModel } from '../../analytics/table/table-domain';
import type { ArtifactAction, ArtifactMetadata } from '../../analytics/components/ArtifactFrame';
import { AssistantMarkdown } from '../../conversations/components/AssistantMarkdown';
import { AnalyticalChart } from '../../charts/AnalyticalChart';
import { MetricCard } from '../../charts/MetricCard';
import {
  combineCompatibleCharts,
  normalizeChartArtifact,
  type NormalizedChartModel,
} from '../../charts/chart-domain';
import { parseHtmlArtifact, parseTableArtifact, parseTextArtifact } from '../lib/artifacts';
import { HtmlArtifactCard } from './HtmlArtifactCard';
import { parseMatrixArtifact } from '../../analytics/matrix/matrix-domain';
import { AnalyticalMatrix } from '../../analytics/matrix/AnalyticalMatrix';

function sourceMetadata(source: QueryExecution | undefined, dataSourceNames: Record<string, string>) {
  return source
    ? {
        name: dataSourceNames[source.data_source_id] ?? 'Data source',
        rowCount: source.row_count,
        durationMs: source.duration_ms,
        ...('dax_text' in source ? { dax: source.dax_text } : { sql: source.sql_text }),
        executionId: source.id,
        truncated: source.truncated,
      }
    : undefined;
}

function dashboardAction(
  navigate: ReturnType<typeof useNavigate>,
  jobId: string,
  artifactId: string,
  sqlId?: string | null,
): ArtifactAction | undefined {
  if (!sqlId) return undefined;
  return {
    id: 'save',
    label: 'Save to dashboard',
    icon: BookmarkPlus,
    run: () => {
      const params = new URLSearchParams({
        sourceJobId: jobId,
        sourceSqlExecutionId: sqlId,
        artifactId,
      });
      void navigate('/dashboards?' + params.toString());
    },
  };
}

function CollapsibleTableArtifact({
  artifact,
  model,
  sourceSql,
  dataSourceNames,
  defaultOpen,
  jobId,
}: {
  artifact: JobArtifact;
  model: AnalyticalTableModel;
  sourceSql?: QueryExecution;
  dataSourceNames: Record<string, string>;
  defaultOpen: boolean;
  jobId: string;
}) {
  const navigate = useNavigate();
  const source = sourceMetadata(sourceSql, dataSourceNames);
  const save = dashboardAction(navigate, jobId, artifact.id, artifact.source_sql_execution_id);
  return (
    <AnalyticalTable
      model={model}
      label={artifact.name || 'Query result'}
      defaultOpen={defaultOpen}
      className="artifact-block table-artifact"
      metadata={{
        rowCount: model.rowCount,
        jobId,
        artifactId: artifact.id,
        sources: source ? [source] : [],
      }}
      extraActions={save ? [save] : []}
    />
  );
}

export function ArtifactRenderer({
  jobId,
  artifacts,
  sql,
  dataSourceNames = {},
  excludeTextMarkdown,
  renderReferencedHiddenTables = false,
  onFollowUp,
}: {
  jobId: string;
  artifacts: JobArtifact[];
  sql: QueryExecution[];
  dataSourceNames?: Record<string, string>;
  excludeTextMarkdown?: string;
  renderReferencedHiddenTables?: boolean;
  onFollowUp?(question: string): Promise<void> | void;
}) {
  const navigate = useNavigate();
  const sqlById = new Map(sql.map((item) => [item.id, item]));
  const artifactOrder = new Map(artifacts.map((artifact, index) => [artifact.id, index]));
  const chartArtifacts = artifacts.filter((artifact) => artifact.kind === 'chart');
  const normalizedCharts = chartArtifacts
    .map((artifact) => {
      const source = sqlById.get(artifact.source_dax_execution_id ?? artifact.source_sql_execution_id ?? '');
      return normalizeChartArtifact(
        artifact,
        source,
        source ? (dataSourceNames[source.data_source_id] ?? 'Data source') : 'Data source',
      );
    })
    .filter((item): item is NormalizedChartModel => item != null);
  const charts = combineCompatibleCharts(normalizedCharts);
  const validChartIds = new Set(
    normalizedCharts.flatMap((model) =>
      model.provenance.map((item) => item.artifactId).filter((id): id is string => Boolean(id)),
    ),
  );
  const invalidCharts = chartArtifacts.filter((item) => !validChartIds.has(item.id));
  const tables = artifacts
    .map((artifact) => ({ artifact, model: parseTableArtifact(artifact) }))
    .filter(
      (item): item is { artifact: JobArtifact; model: AnalyticalTableModel } => item.model != null,
    );
  const texts = artifacts
    .map((artifact) => ({ artifact, model: parseTextArtifact(artifact) }))
    .filter(
      (item) => item.model != null && item.model.markdown.trim() !== excludeTextMarkdown?.trim(),
    );
  const htmlArtifacts = artifacts
    .map((artifact) => ({ artifact, model: parseHtmlArtifact(artifact) }))
    .filter((item) => item.model != null);
  const allValidTextArtifactIds = artifacts
    .filter((artifact) => parseTextArtifact(artifact) != null)
    .map((artifact) => artifact.id);
  const matrices = artifacts.flatMap((artifact) => {
    const model = parseMatrixArtifact(artifact);
    const source = sqlById.get(artifact.source_sql_execution_id ?? '');
    return model && source?.status === 'succeeded' && !source.truncated
      ? [{ artifact, model, source }]
      : [];
  });
  const supportedIds = new Set([
    ...tables.map((item) => item.artifact.id),
    ...allValidTextArtifactIds,
    ...chartArtifacts.map((item) => item.id),
    ...htmlArtifacts.map((item) => item.artifact.id),
    ...matrices.map((item) => item.artifact.id),
  ]);
  const unsupported = artifacts.filter((artifact) => !supportedIds.has(artifact.id));
  if (!artifacts.length) return null;

  const hasCharts = charts.length > 0;
  // Filter out tables marked 'hidden' or 0-row exploratory retries when other successful data exists
  const visibleTables = tables.filter(({ model }) => {
    if (model.display === 'hidden' && !renderReferencedHiddenTables) return false;
    if (
      model.display === 'auto' &&
      model.rowCount === 0 &&
      (hasCharts || tables.some((t) => t.model.rowCount > 0))
    ) {
      return false;
    }
    return true;
  });

  const entries: Array<{ order: number; key: string; node: ReactNode }> = [];
  for (const chart of charts) {
    const metadata: ArtifactMetadata = {
      jobId,
      artifactId: chart.id,
      sources: chart.provenance.map(
        (item) =>
          sourceMetadata(sqlById.get(item.executionId ?? ''), dataSourceNames) ?? {
            name: item.dataSourceName,
          },
      ),
      notes:
        chart.provenance.length > 1
          ? ['Combined views from multiple sources remain separate when saved.']
          : [],
    };
    const single = chart.provenance.length === 1 ? chart.provenance[0] : undefined;
    const save = single?.artifactId && !('dax_text' in (sqlById.get(single.executionId ?? '') ?? {}))
      ? dashboardAction(navigate, jobId, single.artifactId, single.executionId)
      : undefined;
    const sourceIds = chart.provenance
      .map((item) => item.artifactId)
      .filter((id): id is string => Boolean(id));
    const order = Math.min(
      ...sourceIds.map((id) => artifactOrder.get(id) ?? Number.MAX_SAFE_INTEGER),
    );
    entries.push({
      order,
      key: `chart-${chart.id}`,
      node: (
        <section className="artifact-block chart-artifact mb-4">
          {chart.chartType === 'metric' ? (
            <MetricCard model={chart} metadata={metadata} extraActions={save ? [save] : []} />
          ) : (
            <AnalyticalChart
              model={chart}
              onFollowUp={onFollowUp}
              metadata={metadata}
              extraActions={save ? [save] : []}
            />
          )}
        </section>
      ),
    });
  }

  for (const [i, { artifact, model }] of visibleTables.entries()) {
    const sourceSql = sqlById.get(artifact.source_dax_execution_id ?? artifact.source_sql_execution_id ?? '');
    const isLastTable = i === visibleTables.length - 1;

    let defaultOpen: boolean;
    if (model.display === 'expanded') {
      defaultOpen = true;
    } else if (model.display === 'collapsed') {
      defaultOpen = false;
    } else {
      // auto mode: collapsed if charts exist, or open if it's the primary table
      defaultOpen = hasCharts ? false : isLastTable;
    }

    entries.push({
      order: artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER,
      key: `table-${artifact.id}`,
      node: (
        <CollapsibleTableArtifact
          artifact={artifact}
          model={model}
          sourceSql={sourceSql}
          dataSourceNames={dataSourceNames}
          defaultOpen={defaultOpen}
          jobId={jobId}
        />
      ),
    });
  }

  for (const { artifact, model } of texts) {
    entries.push({
      order: artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER,
      key: `text-${artifact.id}`,
      node: (
        <section className="artifact-text mb-4">
          <h4 className="font-semibold text-xs text-[var(--db-text-primary)] mb-2">
            {artifact.name || 'Text output'}
          </h4>
          <AssistantMarkdown content={model!.markdown} />
        </section>
      ),
    });
  }
  for (const { artifact, model, source } of matrices) {
    entries.push({
      order: artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER,
      key: `matrix-${artifact.id}`,
      node: (
        <div className="artifact-block matrix-artifact mb-4">
          <AnalyticalMatrix
            key={artifact.id}
            model={model}
            artifactId={artifact.id}
            jobId={jobId}
            dataSourceName={dataSourceNames[source.data_source_id] ?? 'Data source'}
            metadata={{
              jobId,
              artifactId: artifact.id,
              sources: [sourceMetadata(source, dataSourceNames)!],
            }}
          />
        </div>
      ),
    });
  }
  for (const { artifact, model } of htmlArtifacts) {
    entries.push({
      order: artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER,
      key: `html-${artifact.id}`,
      node: <HtmlArtifactCard jobId={jobId} artifact={artifact} model={model!} />,
    });
  }
  if (invalidCharts.length) {
    const order = Math.min(
      ...invalidCharts.map((artifact) => artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER),
    );
    entries.push({
      order,
      key: 'invalid-charts',
      node: (
        <div
          className="p-3 bg-[var(--db-danger-soft)] border border-[var(--db-border-default)] rounded text-xs text-[var(--db-danger)] mb-2"
          role="status"
        >
          <strong>Chart unavailable</strong>
          <p className="mt-1 text-[var(--db-text-secondary)]">
            {invalidCharts.length} chart artifact{invalidCharts.length === 1 ? '' : 's'} could not
            be rendered because its field encoding or data is invalid.
          </p>
        </div>
      ),
    });
  }
  for (const artifact of unsupported) {
    entries.push({
      order: artifactOrder.get(artifact.id) ?? Number.MAX_SAFE_INTEGER,
      key: `unsupported-${artifact.id}`,
      node: (
        <div
          className="p-3 bg-[var(--db-surface-muted)] border border-[var(--db-border-default)] rounded text-xs text-[var(--db-text-secondary)] mb-2"
          role="status"
        >
          <strong>Unsupported artifact</strong>
          <p className="mt-1">{artifact.kind || 'Unknown'} output cannot be displayed safely.</p>
        </div>
      ),
    });
  }

  return (
    <div className="artifact-stack" aria-label="Analytical artifacts">
      {entries
        .sort((a, b) => a.order - b.order)
        .map((entry) => (
          <div key={entry.key} className="artifact-sequence-item">
            {entry.node}
          </div>
        ))}
    </div>
  );
}
