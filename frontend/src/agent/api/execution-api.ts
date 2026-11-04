import { API_BASE_URL, apiClient, withAuthRefresh } from '../../api/client';
import type { components } from '../../api/generated/schema';

type Schemas = components['schemas'];
export type ExecutionTrace = Schemas['JobExecutionTraceResponse'];
export type ToolExecution = Schemas['ToolExecutionResponse'];
export type SqlExecution = Schemas['SQLExecutionResponse'];
export type DaxExecution = Schemas['DaxExecutionResponse'];
export type QueryExecution = SqlExecution | DaxExecution;
export type ModelExecution = Schemas['ModelExecutionResponse'];
export type JobArtifact = Schemas['JobArtifactResponse'];

export function getExecutionTrace(jobId: string): Promise<ExecutionTrace> {
  return withAuthRefresh(() => apiClient.GET('/api/v1/jobs/{job_id}/execution', {
    params: { path: { job_id: jobId } },
  }));
}

export function getHtmlArtifactUrl(jobId: string, artifactId: string): string {
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}/html`;
}
