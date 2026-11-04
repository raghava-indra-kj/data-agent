import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import type { ReactNode, Ref } from 'react';
import { queryKeys } from '../../api/queryKeys';
import { listDataSources } from '../../data-sources/api/data-source-api';
import { useOrganization } from '../../organizations/OrganizationProvider';
import { useExecutionTrace } from '../hooks/useExecutionTrace';
import { ArtifactRenderer } from './ArtifactRenderer';
import { JobUsageSummary } from './JobUsageSummary';
import { hasArtifactDirectives } from '../lib/artifact-directives';
import { AssistantResponseRenderer } from '../../conversations/components/AssistantResponseRenderer';
import type { JobArtifact } from '../api/execution-api';

export function MessageAnalysisDetails({
  jobId,
  answerMarkdown,
  onFollowUp,
  onArtifactsLoaded,
  footerActions,
  presenting = false,
  presentationBodyRef,
  onSectionChange,
  selectedSection,
  onSelectedSectionChange,
}: {
  jobId: string;
  answerMarkdown: string;
  onFollowUp?(question: string): Promise<void> | void;
  onArtifactsLoaded?(artifacts: JobArtifact[]): void;
  footerActions?: ReactNode;
  presenting?: boolean;
  presentationBodyRef?: Ref<HTMLDivElement>;
  onSectionChange?: () => void;
  selectedSection?: string;
  onSelectedSectionChange?: (key: string) => void;
}) {
  const { activeOrganization } = useOrganization();
  const orgId = activeOrganization?.id ?? null;
  const trace = useExecutionTrace(jobId);
  const dataSources = useQuery({
    queryKey: queryKeys.dataSources.list(orgId),
    queryFn: listDataSources,
    enabled: Boolean(orgId),
    staleTime: 60_000,
  });
  const sourceNames = Object.fromEntries(
    (dataSources.data ?? []).map((source) => [source.id, source.name]),
  );

  const artifactCount = trace.data?.artifacts?.length ?? 0;
  const inlineArtifacts = hasArtifactDirectives(answerMarkdown);

  useEffect(() => {
    if (trace.data) onArtifactsLoaded?.(trace.data.artifacts ?? []);
  }, [onArtifactsLoaded, trace.data]);

  return (
    <>
      <div ref={presentationBodyRef} className="assistant-card-body">
        <div className="assistant-card-content">
          <AssistantResponseRenderer
            jobId={jobId}
            markdown={answerMarkdown}
            artifacts={trace.data?.artifacts ?? []}
            sql={[...(trace.data?.sql ?? []), ...(trace.data?.dax ?? [])]}
            dataSourceNames={sourceNames}
            traceLoading={trace.isLoading}
            traceUnavailable={trace.isError}
            onFollowUp={onFollowUp}
            presenting={presenting}
            onSectionChange={onSectionChange}
            selectedSection={selectedSection}
            onSelectedSectionChange={onSelectedSectionChange}
          />
        </div>

        {trace.data && artifactCount > 0 && !inlineArtifacts ? (
          <div className="assistant-card-artifacts">
            <ArtifactRenderer
              jobId={jobId}
              artifacts={trace.data.artifacts ?? []}
              sql={[...(trace.data.sql ?? []), ...(trace.data.dax ?? [])]}
              dataSourceNames={sourceNames}
              excludeTextMarkdown={answerMarkdown}
              onFollowUp={onFollowUp}
            />
          </div>
        ) : null}
      </div>

      {footerActions ? (
        <footer className="assistant-card-footer assistant-card-footer--actions-only">
          <JobUsageSummary models={trace.data?.models ?? []} className="assistant-card-usage" />
          {footerActions}
        </footer>
      ) : null}
    </>
  );
}
