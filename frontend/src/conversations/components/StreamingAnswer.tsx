import { memo } from 'react';
import { BrandLogo } from '../../components/BrandLogo';
import { BRANDING } from '../../lib/branding';
import { useExecutionTrace } from '../../agent/hooks/useExecutionTrace';
import type { ManagedJob } from '../../jobs/types';
import { AssistantResponseRenderer } from './AssistantResponseRenderer';

export const StreamingAnswer = memo(function StreamingAnswer({
  managedJob,
  dataSourceNames,
}: {
  managedJob: ManagedJob;
  dataSourceNames: Record<string, string>;
}) {
  const trace = useExecutionTrace(managedJob.job.id);
  const incomplete = managedJob.job.status === 'failed' || managedJob.job.status === 'cancelled';
  return (
    <div className="chat-message-row assistant" data-streaming-job-id={managedJob.job.id}>
      <article
        className="assistant-card assistant-card--streaming"
        aria-label={incomplete ? 'Incomplete answer' : 'Answer being written'}
        aria-busy={!incomplete}
      >
        <div className="answer-identity">
          <BrandLogo />
          <span>{BRANDING.name}</span>
          {incomplete && <span className="streaming-answer-state">Incomplete response</span>}
        </div>
        <AssistantResponseRenderer
          jobId={managedJob.job.id}
          markdown={managedJob.answer?.text ?? ''}
          artifacts={trace.data?.artifacts ?? []}
          sql={[...(trace.data?.sql ?? []), ...(trace.data?.dax ?? [])]}
          dataSourceNames={dataSourceNames}
          traceLoading={trace.isLoading}
          traceUnavailable={trace.isError}
          streaming
        />
      </article>
    </div>
  );
});
