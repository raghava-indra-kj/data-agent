import { dataSourceType } from '../../components/management/management-labels';
import { Button } from '@heroui/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Database, Eye, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import type { AppError } from '../../api/errors';
import type { DataSource } from '../../api/types';
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
import { useJobManager } from '../../jobs/JobManagerProvider';
import { useOrganization } from '../../organizations/OrganizationProvider';
import * as api from '../api/data-source-api';

export function DataSourcesPage() {
  const navigate = useNavigate();
  const { activeOrganization } = useOrganization();
  const orgId = activeOrganization?.id ?? null;
  const canManage = activeOrganization?.role === 'owner' || activeOrganization?.role === 'admin';
  const client = useQueryClient();
  const jobs = useJobManager();
  const [search, setSearch] = useState('');
  const [deleting, setDeleting] = useState<DataSource | null>(null);
  const query = useQuery({
    queryKey: queryKeys.dataSources.list(orgId),
    queryFn: api.listDataSources,
    enabled: Boolean(orgId),
  });
  const test = useMutation({
    mutationFn: api.testDataSource,
    onSuccess: async ({ job_id }) => {
      await jobs.registerJob(job_id);
      notifications.info('Connection test started.');
    },
    onError: (error: AppError) =>
      notifications.error('Unable to test the connection', error.message),
  });
  if (query.isLoading) return <PageLoading label="Loading data sources…" />;
  if (query.isError)
    return <PageError title="Unable to load data sources" retry={() => void query.refetch()} />;
  const visible = (query.data ?? []).filter((source) =>
    (source.name + ' ' + dataSourceType(source.display_type))
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <section className="management-page" aria-label="Data sources">
      <ManagementHeader title="Data sources">
        <ManagementSearch label="Search data sources" value={search} onChange={setSearch} />
        {canManage && (
          <Button variant="primary" onPress={() => void navigate('/data-sources/new')}>
            <Plus size={15} aria-hidden="true" />
            Add data source
          </Button>
        )}
      </ManagementHeader>
      {test.isError && (
        <p role="alert" className="management-error">
          {test.error.message}
        </p>
      )}
      <div className="management-list">
        {visible.map((source) => (
          <article className="management-row" key={source.id}>
            <Link to={'/data-sources/' + source.id} className="management-row-link">
              <span className="management-row-icon">
                <Database size={17} aria-hidden="true" />
              </span>
              <span className="management-row-title">{source.name}</span>
            </Link>
            <div className="management-row-tags">
              <span className="management-badge">{dataSourceType(source.display_type)}</span>
              <ManagementStatus
                status={test.isPending && test.variables === source.id ? 'running' : source.status}
              />
            </div>
            <ManagementMenu
              name={source.name}
              disabled={test.isPending}
              actions={[
                { id: 'view', label: 'View data source', icon: <Eye size={15} /> },
                ...(source.kind !== 'powerbi' ? [{ id: 'knowledge', label: 'View knowledge', icon: <BookOpen size={15} /> }] : []),
                ...(canManage
                  ? [
                      ...(source.kind !== 'powerbi' ? [{ id: 'edit', label: 'Edit data source', icon: <Pencil size={15} /> },
                      { id: 'test', label: 'Test connection', icon: <RefreshCw size={15} /> }] : []),
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
                if (key === 'view') void navigate('/data-sources/' + source.id);
                if (key === 'knowledge') void navigate('/knowledge/' + source.id);
                if (key === 'edit') void navigate('/data-sources/' + source.id + '/edit');
                if (key === 'test') test.mutate(source.id);
                if (key === 'delete') setDeleting(source);
              }}
            />
          </article>
        ))}
      </div>
      {visible.length === 0 && (
        <div className="management-empty">
          <Database size={26} aria-hidden="true" />
          <h2>{search ? 'No matching data sources' : 'No data sources yet'}</h2>
          {search ? (
            <Button variant="secondary" onPress={() => setSearch('')}>
              Clear search
            </Button>
          ) : (
            <p>
              {canManage
                ? 'Connect a database or upload an Excel workbook to get started.'
                : 'Ask a workspace admin to add a data source.'}
            </p>
          )}
        </div>
      )}
      {deleting && (
        <ManagementDeleteDialog
          title="Delete data source?"
          description={'Remove “' + deleting.name + '” from this workspace? This can’t be undone.'}
          confirmLabel="Delete data source"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await api.deleteDataSource(deleting.id);
            await client.invalidateQueries({ queryKey: queryKeys.dataSources.all(orgId) });
            await client.invalidateQueries({ queryKey: queryKeys.knowledge.all(orgId) });
            notifications.success('Data source deleted.');
          }}
        />
      )}
    </section>
  );
}
