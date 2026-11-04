import { memo, useMemo } from 'react';
import type { JobArtifact, QueryExecution } from '../../agent/api/execution-api';
import { ArtifactRenderer } from '../../agent/components/ArtifactRenderer';
import { parseArtifactDirectives } from '../../agent/lib/artifact-directives';
import { AssistantMarkdown } from './AssistantMarkdown';
import { AnswerNavigation } from './AnswerNavigation';

// Keep already-created charts mounted and unchanged while adjacent prose grows.
const InlineArtifact = memo(function InlineArtifact({
  artifact,
  jobId,
  sql,
  dataSourceNames,
  onFollowUp,
}: {
  artifact: JobArtifact;
  jobId: string;
  sql: QueryExecution[];
  dataSourceNames: Record<string, string>;
  onFollowUp?(question: string): Promise<void> | void;
}) {
  const artifacts = useMemo(() => [artifact], [artifact]);
  return (
    <ArtifactRenderer
      jobId={jobId}
      artifacts={artifacts}
      sql={sql}
      dataSourceNames={dataSourceNames}
      renderReferencedHiddenTables
      onFollowUp={onFollowUp}
    />
  );
});

export function AssistantResponseRenderer({
  jobId,
  markdown,
  artifacts,
  sql,
  dataSourceNames = {},
  traceLoading = false,
  traceUnavailable = false,
  onFollowUp,
  presenting = false,
  onSectionChange,
  selectedSection,
  onSelectedSectionChange,
  streaming = false,
}: {
  jobId: string;
  markdown: string;
  artifacts: JobArtifact[];
  sql: QueryExecution[];
  dataSourceNames?: Record<string, string>;
  traceLoading?: boolean;
  traceUnavailable?: boolean;
  onFollowUp?(question: string): Promise<void> | void;
  presenting?: boolean;
  onSectionChange?: () => void;
  selectedSection?: string;
  onSelectedSectionChange?: (key: string) => void;
  streaming?: boolean;
}) {
  const artifactsById = useMemo(
    () => new Map(artifacts.map((artifact) => [artifact.id, artifact])),
    [artifacts],
  );

  const renderContent = (sectionMarkdown: string) => (
    <div className="assistant-response-segments">
      {parseArtifactDirectives(sectionMarkdown).map((segment, index) => {
        if (segment.type === 'markdown') {
          return <AssistantMarkdown key={`markdown-${index}`} content={segment.content} />;
        }

        const artifact = artifactsById.get(segment.artifactId);
        if (traceLoading) {
          return (
            <div
              key={`artifact-${segment.artifactId}`}
              className="my-3 p-3 border border-[var(--db-border-default)] bg-[var(--db-surface)] text-xs text-[var(--db-text-muted)]"
              role="status"
            >
              Loading output…
            </div>
          );
        }
        if (traceUnavailable || !artifact) {
          return (
            <div
              key={`artifact-${segment.artifactId}`}
              className="my-3 p-3 border border-[var(--db-border-default)] bg-[var(--db-danger-soft)] text-xs text-[var(--db-text-secondary)]"
              role="status"
            >
              <strong>Output unavailable</strong>
              <p className="mt-1">
                The answer is preserved, but this referenced output could not be loaded.
              </p>
            </div>
          );
        }
        return (
          <InlineArtifact
            key={`artifact-${segment.artifactId}`}
            jobId={jobId}
            artifact={artifact}
            sql={sql}
            dataSourceNames={dataSourceNames}
            onFollowUp={onFollowUp}
          />
        );
      })}
    </div>
  );
  // Keep the growing response in one stable view. Section tabs are created on completion.
  if (streaming) return <div className="answer-main-content">{renderContent(markdown)}</div>;
  return (
    <AnswerNavigation
      key={presenting ? 'presenting' : 'conversation'}
      content={markdown}
      showIdentity={!presenting}
      onSectionChange={onSectionChange}
      selectedKey={selectedSection}
      onSelectedKeyChange={onSelectedSectionChange}
      renderContent={renderContent}
    />
  );
}
