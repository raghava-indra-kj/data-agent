import { Button } from '@heroui/react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { useNavigate, useParams } from 'react-router';
import type { AppError } from '../../api/errors';
import { ArtifactRenderer } from '../../agent/components/ArtifactRenderer';
import { ExecutionTimeline } from '../../agent/components/ExecutionTimeline';
import { useExecutionTrace } from '../../agent/hooks/useExecutionTrace';
import { queryKeys } from '../../api/queryKeys';
import { PageError, PageLoading } from '../../components/PageState';
import { ManagementHeader } from '../../components/management/ManagementUI';
import { listDataSources } from '../../data-sources/api/data-source-api';
import { formatLocalDateTime, formatRelativeTime } from '../../lib/datetime';
import { useOrganization } from '../../organizations/OrganizationProvider';
import { getJobDestination, useJobManager } from '../JobManagerProvider';
import { JobDiagnosticsPanel } from '../components/JobDiagnosticsPanel';
import { JobStatusBadge } from '../components/JobStatusBadge';
import { useJob } from '../hooks/useJobs';
import { formatJobDuration, jobContext, jobTypeLabel } from '../job-display';
import { getSafeJobEventLabel } from '../sse/job-events';
import { isActiveJobStatus } from '../types';
import '../jobs.css';

export function JobDetailPage() {
  const { jobId = '' } = useParams();
  const navigate = useNavigate();
  const manager = useJobManager();
  const managed = manager.jobs.find((item) => item.job.id === jobId);
  const query = useJob(jobId);
  const trace = useExecutionTrace(jobId, Boolean(jobId));
  const { activeOrganization } = useOrganization();
  const orgId = activeOrganization?.id ?? null;
  const sources = useQuery({
    queryKey: queryKeys.dataSources.list(orgId),
    queryFn: listDataSources,
    enabled: Boolean(orgId),
    staleTime: 60_000,
  });
  const cancel = useMutation({ mutationFn: () => manager.cancel(jobId) });
  const sourceNames = Object.fromEntries(
    (sources.data ?? []).map((source) => [source.id, source.name]),
  );
  const job = managed?.job ?? query.data;
  if (query.isLoading && !job) return <PageLoading label="Loading job…" />;
  if (!job) return <PageError title="Unable to load this job" retry={() => void query.refetch()} />;
  const destination = getJobDestination(job);
  const context = jobContext(job, sourceNames);
  const durationMs =
    job.duration_ms ??
    (job.started_at && job.finished_at
      ? Date.parse(job.finished_at) - Date.parse(job.started_at)
      : null);
  const events = (managed?.events ?? [])
    .map((event) => ({ ...event, label: getSafeJobEventLabel(event) }))
    .filter((event) => event.label);
  return (
    <section className="management-page management-detail jobs-page">
      <ManagementHeader
        title={jobTypeLabel(job.job_type)}
        backTo="/jobs"
        backLabel="Back to jobs"
        badge={<JobStatusBadge status={job.status} />}
      >
        {isActiveJobStatus(job.status) && (
          <Button
            variant="secondary"
            isPending={cancel.isPending || Boolean(job.cancel_requested_at)}
            onPress={() => cancel.mutate()}
          >
            {job.cancel_requested_at ? 'Cancelling…' : 'Cancel job'}
          </Button>
        )}
        {destination && destination !== '/jobs/' + job.id && (
          <Button variant="primary" onPress={() => void navigate(destination)}>
            {job.conversation_id ? 'Open chat' : 'View data source'}
          </Button>
        )}
      </ManagementHeader>
      {context && <p className="job-progress-label">{context}</p>}
      {cancel.isError && (
        <p className="management-error" role="alert">
          {(cancel.error as unknown as AppError)?.message ||
            'Unable to cancel this job. Please try again.'}
        </p>
      )}
      {job.status === 'failed' && (
        <p className="job-failure" role="alert">
          {job.error_message ||
            'This job couldn’t be completed. Please try again from where you started.'}
        </p>
      )}
      {isActiveJobStatus(job.status) && (
        <p className="job-progress-label" role="status">
          {manager.currentLabel(job.id) ||
            (job.status === 'queued' ? 'Waiting to start…' : 'Working on your request…')}
        </p>
      )}
      <section className="management-panel" aria-label="Job overview">
        <dl className="job-overview">
          <div>
            <dt>Created</dt>
            <dd>{formatLocalDateTime(job.created_at)}</dd>
          </div>
          {job.finished_at && (
            <div>
              <dt>Finished</dt>
              <dd>{formatLocalDateTime(job.finished_at)}</dd>
            </div>
          )}
          {durationMs != null && (
            <div>
              <dt>Duration</dt>
              <dd>{formatJobDuration(durationMs)}</dd>
            </div>
          )}
        </dl>
      </section>
      <details className="job-details">
        <summary>
          Activity
          <ChevronDown size={15} aria-hidden="true" />
        </summary>
        <div className="job-details-body">
          {trace.isLoading ? (
            <PageLoading label="Loading activity…" />
          ) : trace.data ? (
            <ExecutionTimeline trace={trace.data} dataSourceNames={sourceNames} />
          ) : events.length ? (
            <ol className="job-event-list">
              {events.map((event) => (
                <li key={event.sequence}>
                  <span>{event.label}</span>
                  <time dateTime={event.created_at} title={formatLocalDateTime(event.created_at)}>
                    {formatRelativeTime(event.created_at)}
                  </time>
                </li>
              ))}
            </ol>
          ) : (
            <p className="management-note">
              {trace.isError
                ? 'Activity couldn’t be loaded. Please try again.'
                : 'No activity details available.'}
            </p>
          )}
          {trace.isError && (
            <Button size="sm" variant="secondary" onPress={() => void trace.refetch()}>
              Try again
            </Button>
          )}
        </div>
      </details>
      <details className="job-details">
        <summary>
          Technical details
          <ChevronDown size={15} aria-hidden="true" />
        </summary>
        <div className="job-details-body">
          <dl className="management-definition">
            <dt>Job ID</dt>
            <dd>{job.id}</dd>
            <dt>Attempts</dt>
            <dd>
              {job.attempt_count} of {job.max_attempts}
            </dd>
          </dl>
          <JobDiagnosticsPanel job={job} trace={trace.data} unavailable={trace.isError} />
        </div>
      </details>
      {trace.data?.artifacts?.length ? (
        <section className="management-panel">
          <h2>Results</h2>
          <ArtifactRenderer
            jobId={job.id}
            artifacts={trace.data.artifacts}
            sql={[...(trace.data.sql ?? []), ...(trace.data.dax ?? [])]}
            dataSourceNames={sourceNames}
          />
        </section>
      ) : null}
    </section>
  );
}
