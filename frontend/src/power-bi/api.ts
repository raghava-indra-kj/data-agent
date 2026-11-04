import { apiClient, withAuthRefresh } from '../api/client';
import type { components } from '../api/generated/schema';

export type PowerBIReport = components['schemas']['ReportResponse'];
export type ReportContext = components['schemas']['ReportContext'];
export type ReportCandidate = components['schemas']['ReportCandidate'];
export const features = () => withAuthRefresh(() => apiClient.GET('/api/v1/power-bi/features'));
export const connections = () =>
  withAuthRefresh(() => apiClient.GET('/api/v1/power-bi/connections'));
export const startConnection = () =>
  withAuthRefresh(() =>
    apiClient.POST('/api/v1/power-bi/connections/start', { credentials: 'include' }),
  );
export const disconnect = (id: string) =>
  withAuthRefresh(() =>
    apiClient.DELETE('/api/v1/power-bi/connections/{connection_id}', {
      params: { path: { connection_id: id } },
    }),
  );
export const resolveReport = (query: string) =>
  withAuthRefresh(() => apiClient.POST('/api/v1/power-bi/reports/resolve', { body: { query } }));
export const discoverReports = (query: string) =>
  withAuthRefresh(() => apiClient.POST('/api/v1/power-bi/reports/discover', { body: { query } }));
export const createSource = (body: components['schemas']['PowerBICreate']) =>
  withAuthRefresh(() => apiClient.POST('/api/v1/data-sources/power-bi', { body }));
export const reports = (sourceId: string) =>
  withAuthRefresh(() =>
    apiClient.GET('/api/v1/data-sources/{source_id}/power-bi/reports', {
      params: { path: { source_id: sourceId } },
    }),
  );
export const refreshSource = (sourceId: string) =>
  withAuthRefresh(() =>
    apiClient.POST('/api/v1/data-sources/{source_id}/power-bi/refresh', {
      params: { path: { source_id: sourceId } },
    }),
  );
// Never put embedding tokens in query caches, URLs, storage or analytics.
export const embedConfig = (bindingId: string) =>
  withAuthRefresh(() =>
    apiClient.POST('/api/v1/power-bi/reports/{binding_id}/embed-config', {
      params: { path: { binding_id: bindingId } },
      cache: 'no-store',
    }),
  );
