import { dataSourceType } from '../../components/management/management-labels';
import { Button } from '@heroui/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, ChevronDown, Pencil, RefreshCw, Table, Trash2, Upload } from 'lucide-react';
import { Fragment, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import type { AppError } from '../../api/errors';
import { queryKeys } from '../../api/queryKeys';
import { PageError, PageLoading } from '../../components/PageState';
import {
  ManagementDeleteDialog,
  ManagementHeader,
  ManagementMenu,
  ManagementSearch,
  ManagementStatus,
} from '../../components/management/ManagementUI';
import { notifications } from '../../components/notifications';
import { formatLocalDateTime } from '../../lib/datetime';
import { safeDisplayEntries, safeJsonStringify } from '../../lib/security';
import { useJobManager } from '../../jobs/JobManagerProvider';
import { useOrganization } from '../../organizations/OrganizationProvider';
import * as api from '../api/data-source-api';
import { ConnectionDiagnosticsPanel } from '../components/ConnectionDiagnosticsPanel';
import { PowerBIDetails } from '../../power-bi/PowerBIDetails';

const configLabels: Record<string, string> = {
  host: 'Host',
  port: 'Port',
  database: 'Database',
  schema_name: 'Schema',
  ssl_mode: 'SSL mode',
  ssl: 'SSL',
  encrypt: 'Encryption',
  trust_server_certificate: 'Trust server certificate',
  odbc_driver: 'ODBC driver',
  authentication_mode: 'Authentication',
};
export function DataSourceDetailPage() {
  const { dataSourceId = '' } = useParams();
  const { activeOrganization } = useOrganization();
  const orgId = activeOrganization?.id ?? null;
  const canManage = activeOrganization?.role === 'owner' || activeOrganization?.role === 'admin';
  const jobs = useJobManager();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [search, setSearch] = useState('');
  const replacementRef = useRef<HTMLInputElement>(null);
  const sourceQuery = useQuery({
    queryKey: queryKeys.dataSources.detail(orgId, dataSourceId),
    queryFn: () => api.getDataSource(dataSourceId),
    enabled: Boolean(dataSourceId),
  });
  const schemaQuery = useQuery({
    queryKey: queryKeys.dataSources.schema(orgId, dataSourceId),
    queryFn: () => api.getDataSourceSchema(dataSourceId),
    enabled: Boolean(sourceQuery.data && sourceQuery.data.kind !== 'powerbi'),
    staleTime: 60000,
  });
  const test = useMutation({
    mutationFn: () => api.testDataSource(dataSourceId),
    onSuccess: async ({ job_id }) => {
      await jobs.registerJob(job_id);
      notifications.info('Connection test started.');
    },
    onError: (error: AppError) =>
      notifications.error('Unable to start connection test', error.message),
  });
  const replacement = useMutation({
    mutationFn: (file: File) => api.replaceExcelDataSource(dataSourceId, file),
    onSuccess: async ({ job_id }) => {
      await jobs.registerJob(job_id);
      notifications.info('Workbook replacement started.');
    },
    onError: (error: AppError) => notifications.error('Unable to replace workbook', error.message),
  });
  const testing =
    test.isPending ||
    Boolean(
      jobs.activeJobs?.some(
        ({ job }) =>
          job.job_type === 'datasource_test' && job.input.data_source_id === dataSourceId,
      ),
    );
  if (sourceQuery.isLoading) return <PageLoading label="Loading data source…" />;
  if (sourceQuery.isError || !sourceQuery.data)
    return (
      <PageError title="Unable to load this data source" retry={() => void sourceQuery.refetch()} />
    );
  const source = sourceQuery.data;
  if (source.kind === 'powerbi') return <PowerBIDetails source={source} />;
  const tables = (schemaQuery.data?.tables ?? []).filter((table) =>
    ((table.schema ?? '') + '.' + table.name)
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <section className="management-page management-detail">
      <ManagementHeader
        title={source.name}
        backTo="/data-sources"
        backLabel="Back to data sources"
        badge={<ManagementStatus status={source.status} />}
      >
        {canManage && (
          <Button variant="secondary" isPending={testing} onPress={() => test.mutate()}>
            <RefreshCw size={14} aria-hidden="true" />
            {testing ? 'Testing…' : 'Test connection'}
          </Button>
        )}
        <ManagementMenu
          name={source.name}
          actions={[
            { id: 'knowledge', label: 'View knowledge', icon: <BookOpen size={15} /> },
            ...(canManage
              ? [
                  { id: 'edit', label: 'Edit data source', icon: <Pencil size={15} /> },
                  ...(source.display_type === 'excel'
                    ? [
                        {
                          id: 'replace',
                          label: 'Replace workbook',
                          icon: <Upload size={15} />,
                          disabled: replacement.isPending,
                        },
                      ]
                    : []),
                  {
                    id: 'delete',
                    label: 'Delete data source',
                    icon: <Trash2 size={15} />,
                    danger: true,
                  },
                ]
              : []),
          ]}
          onAction={(key) => {
            if (key === 'knowledge') void navigate('/knowledge/' + source.id);
            if (key === 'edit') void navigate('/data-sources/' + source.id + '/edit');
            if (key === 'delete') setDeleting(true);
            if (key === 'replace') replacementRef.current?.click();
          }}
        />
      </ManagementHeader>
      {(test.isError || replacement.isError) && (
        <p className="management-error" role="alert">
          {test.error?.message || replacement.error?.message}
        </p>
      )}
      <ConnectionDiagnosticsPanel
        diagnostics={source.last_connection_diagnostics}
        code={source.last_error_code}
        sourceId={source.id}
        canManage={canManage}
        testing={testing}
        onTest={() => test.mutate()}
      />
      <div className="management-details-grid">
        <section className="management-panel" aria-labelledby="source-connection">
          <h2 id="source-connection">Connection</h2>
          <dl className="management-definition">
            <dt>Type</dt>
            <dd>{dataSourceType(source.display_type)}</dd>
            {safeDisplayEntries(source.config).map(([key, value]) => (
              <Fragment key={key}>
                <dt>
                  {configLabels[key] ??
                    key.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())}
                </dt>
                <dd>
                  {value && typeof value === 'object' ? (
                    <pre>{safeJsonStringify(value)}</pre>
                  ) : typeof value === 'boolean' ? (
                    value ? (
                      'Yes'
                    ) : (
                      'No'
                    )
                  ) : (
                    String(value ?? '—')
                  )}
                </dd>
              </Fragment>
            ))}
            {source.display_type === 'excel' && (
              <>
                <dt>Workbook</dt>
                <dd>{source.active_file?.original_filename ?? 'Preparing workbook…'}</dd>
              </>
            )}
            <dt>Last tested</dt>
            <dd>
              {source.last_tested_at
                ? formatLocalDateTime(source.last_tested_at)
                : 'Not tested yet'}
            </dd>
          </dl>
          <p className="management-note">
            <Link to={'/knowledge/' + source.id}>View schema and business knowledge</Link>
          </p>
        </section>
        <section className="management-panel" aria-labelledby="source-schema">
          <div className="management-panel-heading">
            <h2 id="source-schema">Tables and views</h2>
          </div>
          {schemaQuery.isError ? (
            <div role="alert">
              <h3>Unable to load schema</h3>
              <p className="management-error">
                {schemaQuery.error?.message || 'Please check the connection and try again.'}
              </p>
              <Button variant="secondary" size="sm" onPress={() => void schemaQuery.refetch()}>
                Retry schema inspection
              </Button>
            </div>
          ) : schemaQuery.isLoading ? (
            <PageLoading label="Loading schema…" />
          ) : (
            <>
              <ManagementSearch
                label="Search tables and views"
                value={search}
                onChange={setSearch}
              />
              <div className="management-schema-list">
                {tables.map((table) => (
                  <details key={(table.schema ?? '') + '.' + table.name}>
                    <summary>
                      <Table size={14} aria-hidden="true" />
                      <span>
                        {table.schema ? table.schema + '.' : ''}
                        {table.name}
                      </span>
                      <ChevronDown size={14} aria-hidden="true" />
                    </summary>
                    <div className="management-table-scroll">
                      <table aria-label={table.name + ' columns'}>
                        <thead>
                          <tr>
                            <th>Column</th>
                            <th>Type</th>
                            <th>Nullable</th>
                          </tr>
                        </thead>
                        <tbody>
                          {table.columns.map((column) => (
                            <tr key={column.name}>
                              <td>{column.name}</td>
                              <td>{column.native_type}</td>
                              <td>
                                {column.nullable === null
                                  ? 'Unknown'
                                  : column.nullable
                                    ? 'Yes'
                                    : 'No'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                ))}
              </div>
              {!tables.length && (
                <p className="management-note">
                  {search ? 'No matching tables or views.' : 'No tables or views available.'}
                </p>
              )}
            </>
          )}
        </section>
      </div>
      <input
        ref={replacementRef}
        className="hidden"
        type="file"
        accept=".xlsx"
        aria-label="Replacement workbook"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = '';
          if (file) replacement.mutate(file);
        }}
      />
      {deleting && (
        <ManagementDeleteDialog
          title="Delete data source?"
          description={'Remove “' + source.name + '” from this workspace? This can’t be undone.'}
          confirmLabel="Delete data source"
          onClose={() => setDeleting(false)}
          onConfirm={async () => {
            await api.deleteDataSource(source.id);
            await client.invalidateQueries({ queryKey: queryKeys.dataSources.all(orgId) });
            await client.invalidateQueries({ queryKey: queryKeys.knowledge.all(orgId) });
            void navigate('/data-sources');
          }}
        />
      )}
    </section>
  );
}
