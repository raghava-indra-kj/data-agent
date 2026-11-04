import { useEffect, useState } from 'react';
import { Button, Modal } from '@heroui/react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Database, Search, Table2, X } from 'lucide-react';
import type { AppError } from '../../api/errors';
import type { DataSource } from '../../api/types';
import { queryKeys } from '../../api/queryKeys';
import { listSourceTables } from '../../data-sources/api/data-source-api';
import { useOrganization } from '../../organizations/OrganizationProvider';
import { normalizeTableScope, tableIdentity, tableScopeLabel } from './table-scope';
import type { SourceTableScope, TableIdentifier } from './table-scope';
import './TableScopeSelector.css';

type Props = {
  dataSources: DataSource[];
  sourceIds: string[];
  value: SourceTableScope[];
  onChange(scope: SourceTableScope[]): void;
  disabled?: boolean;
};

function SourceTables({
  source,
  scope,
  onChange,
}: {
  source: { id: string; name: string };
  scope: SourceTableScope;
  onChange(scope: SourceTableScope): void;
}) {
  const { activeOrganization } = useOrganization();
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  const queryKey = queryKeys.dataSources.tables(activeOrganization?.id ?? null, source.id, query);
  const catalog = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) =>
      listSourceTables(source.id, query, pageParam?.cursor, pageParam?.version, signal),
    initialPageParam: undefined as { cursor: string; version: string } | undefined,
    getNextPageParam: (page) =>
      page.next_cursor
        ? { cursor: page.next_cursor, version: page.knowledge_version_id }
        : undefined,
    enabled: Boolean(activeOrganization?.id),
    retry: false,
    staleTime: 30_000,
  });
  const tables = catalog.data?.pages.flatMap((page) => page.items) ?? [];
  const selected = scope.tables ?? [];
  const selectedIds = new Set(selected.map(tableIdentity));
  const schemas = [...new Set(tables.map((table) => table.schema ?? ''))];
  const toggle = (table: TableIdentifier) => {
    const next = selectedIds.has(tableIdentity(table))
      ? selected.filter((item) => tableIdentity(item) !== tableIdentity(table))
      : [...selected, { schema: table.schema ?? null, name: table.name }];
    onChange({ ...scope, mode: 'selected', tables: next });
  };
  return (
    <section className="table-scope-source" aria-label={source.name}>
      <div className="table-scope-source-header">
        <h3 title={source.name}>
          <Database size={14} aria-hidden="true" />
          <span>{source.name}</span>
        </h3>
        <div className="table-scope-modes" role="radiogroup" aria-label={`Tables for ${source.name}`}>
          <label className={scope.mode === 'all' ? 'is-active' : ''}>
            <input
              type="radio"
              name={`table-mode-${source.id}`}
              checked={scope.mode === 'all'}
              onChange={() => onChange({ ...scope, mode: 'all', tables: [] })}
            />
            All tables
          </label>
          <label className={scope.mode === 'selected' ? 'is-active' : ''}>
            <input
              type="radio"
              name={`table-mode-${source.id}`}
              checked={scope.mode === 'selected'}
              onChange={() => onChange({ ...scope, mode: 'selected', tables: selected })}
            />
            Choose tables
          </label>
        </div>
      </div>
      <div className="table-scope-list-toolbar">
        <div className="table-scope-search db-icon-search">
          <Search size={15} aria-hidden="true" />
          <input
            className="db-icon-search__input"
            aria-label="Search tables or schemas"
            type="search"
            value={search}
            placeholder="Search tables…"
            onChange={(event) => setSearch(event.target.value)}
          />
          {search && (
            <button type="button" aria-label="Clear table search" onClick={() => setSearch('')}>
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      {scope.mode === 'selected' && selected.length > 0 && (
        <aside className="table-scope-selection" aria-label="Selected tables summary">
          <div className="table-scope-selection-header">
            <span>Selected</span>
            <button
              type="button"
              onClick={() => onChange({ ...scope, mode: 'selected', tables: [] })}
            >
              Clear all
            </button>
          </div>
          <ul className="table-scope-selected-list">
            {selected.map((table) => (
              <li key={tableIdentity(table)}>
                <span title={table.schema ? table.schema + '.' + table.name : table.name}>
                  {table.name}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${table.schema ? `${table.schema}.` : ''}${table.name}`}
                  onClick={() => toggle(table)}
                >
                  <X size={12} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
      {selected.length >= 500 && (
        <p className="table-scope-limit" role="status">
          You’ve selected 500 tables. Choose All tables to include more.
        </p>
      )}
      <div className="table-scope-catalog" aria-label="Tables" tabIndex={0}>
        {catalog.isPending && (
          <div className="table-scope-empty" role="status">
            <p>Loading tables…</p>
          </div>
        )}
        {catalog.isError && (
          <div role="alert" className="table-scope-empty table-scope-error">
            <p>
              {(catalog.error as unknown as AppError)?.message ||
                'Unable to load tables. Please try again.'}
            </p>
            <Button
              size="sm"
              variant="secondary"
              onPress={() => void client.resetQueries({ queryKey, exact: true })}
            >
              Try again
            </Button>
          </div>
        )}
        {!catalog.isPending && !catalog.isError && tables.length === 0 && (
          <div className="table-scope-empty">
            <p>{query ? 'No tables match your search.' : 'No tables or views are available.'}</p>
            {query && (
              <Button size="sm" variant="secondary" onPress={() => setSearch('')}>
                Clear search
              </Button>
            )}
          </div>
        )}
        {schemas.map((schema) => {
          const schemaTables = tables.filter((table) => (table.schema ?? '') === schema);
          return (
            <div
              key={schema}
              className="table-scope-schema"
              role="group"
              aria-label={schema || 'Tables'}
            >
              <div className="table-scope-schema-header" aria-hidden="true">
                <span>{schema || 'Tables'}</span>
                {!catalog.hasNextPage && (
                  <span>
                    {schemaTables.length} {schemaTables.length === 1 ? 'table' : 'tables'}
                  </span>
                )}
              </div>
              {schemaTables.map((table) => {
                const checked = scope.mode === 'selected' && selectedIds.has(tableIdentity(table));
                return (
                  <label
                    key={tableIdentity(table)}
                    className={`table-scope-row ${checked ? 'is-selected' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!selectedIds.has(tableIdentity(table)) && selected.length >= 500}
                      onChange={() => toggle(table)}
                    />
                    <span
                      className="table-scope-name"
                      title={table.schema ? table.schema + '.' + table.name : table.name}
                    >
                      {table.name}
                    </span>
                    {table.object_type === 'view' && (
                      <span className="table-scope-object-type">View</span>
                    )}
                    {typeof table.column_count === 'number' && (
                      <span className="table-scope-column-count">
                        {table.column_count} {table.column_count === 1 ? 'column' : 'columns'}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          );
        })}
        {catalog.hasNextPage && (
          <div className="table-scope-load-more">
            <Button
              size="sm"
              variant="secondary"
              isPending={catalog.isFetchingNextPage}
              onPress={() => void catalog.fetchNextPage()}
            >
              Load more tables
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}

export function TableScopeSelector({
  dataSources,
  sourceIds,
  value,
  onChange,
  disabled = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<SourceTableScope[]>([]);
  const [activeSourceId, setActiveSourceId] = useState(sourceIds[0] ?? '');
  const scope = normalizeTableScope(sourceIds, value);
  const valid = draft.every((item) => item.mode === 'all' || (item.tables?.length ?? 0) > 0);
  const openDialog = () => {
    setDraft(structuredClone(scope));
    setActiveSourceId(sourceIds[0] ?? '');
    setOpen(true);
  };
  const sources = sourceIds.map(
    (id) =>
      dataSources.find((source) => source.id === id) ?? { id, name: 'Unavailable data source' },
  );
  const displayedScope = normalizeTableScope(sourceIds, draft);
  const activeSource = sources.find((source) => source.id === activeSourceId) ?? sources[0];
  const selectedCount = displayedScope.reduce(
    (count, item) => count + (item.tables?.length ?? 0),
    0,
  );
  const allCount = displayedScope.filter((item) => item.mode === 'all').length;
  const summary = selectedCount
    ? `${selectedCount} table${selectedCount === 1 ? '' : 's'} selected${allCount ? ` · all tables in ${allCount} other source${allCount === 1 ? '' : 's'}` : ''}`
    : allCount === 1
      ? 'All tables'
      : `All tables in ${allCount} sources`;
  return (
    <>
      <button
        type="button"
        className={`chat-composer-chip table-scope-trigger ${open || sourceIds.length > 0 ? 'active' : ''}`}
        disabled={disabled || sourceIds.length === 0}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={openDialog}
        title={
          sourceIds.length
            ? `${tableScopeLabel(scope)} · Choose tables for the agent to start with`
            : 'Select a data source first'
        }
      >
        <Table2 size={12} aria-hidden="true" />
        <span>{tableScopeLabel(scope)}</span>
        <ChevronDown size={11} aria-hidden="true" />
      </button>
      <Modal.Backdrop isOpen={open} onOpenChange={setOpen} className="table-scope-backdrop">
        <Modal.Container
          size="lg"
          scroll="inside"
          placement="center"
          className="table-scope-container"
        >
          <Modal.Dialog className="table-scope-dialog">
            <Modal.Header className="table-scope-header">
              <Modal.Heading>Choose tables</Modal.Heading>
              <Button
                isIconOnly
                variant="ghost"
                size="sm"
                aria-label="Close table selection"
                onPress={() => setOpen(false)}
              >
                <X size={17} aria-hidden="true" />
              </Button>
            </Modal.Header>
            <Modal.Body className="table-scope-body">
              {sources.length > 1 && (
                <nav className="table-scope-source-nav" aria-label="Data sources">
                  {sources.map((source) => {
                    const item = displayedScope.find((entry) => entry.data_source_id === source.id);
                    const count = item?.tables?.length ?? 0;
                    return (
                      <button
                        key={source.id}
                        type="button"
                        aria-label={`${source.name}, ${item?.mode === 'all' ? 'all tables' : `${count} table${count === 1 ? '' : 's'} selected`}`}
                        aria-pressed={source.id === activeSource?.id}
                        onClick={() => setActiveSourceId(source.id)}
                      >
                        <Database size={13} aria-hidden="true" />
                        <span>{source.name}</span>
                      </button>
                    );
                  })}
                </nav>
              )}
              {activeSource &&
                (() => {
                  if (dataSources.find((source) => source.id === activeSource.id)?.kind === 'powerbi') return <p className="p-4 text-sm">Power BI uses your authorized semantic model. Open the report to choose page filters and slicers for a question.</p>;
                  const item = displayedScope.find(
                    (entry) => entry.data_source_id === activeSource.id,
                  ) ?? { data_source_id: activeSource.id, mode: 'all' as const, tables: [] };
                  return (
                    <SourceTables
                      key={activeSource.id}
                      source={activeSource}
                      scope={item}
                      onChange={(next) =>
                        setDraft((current) =>
                          normalizeTableScope(sourceIds, current).map((entry) =>
                            entry.data_source_id === activeSource.id ? next : entry,
                          ),
                        )
                      }
                    />
                  );
                })()}
            </Modal.Body>
            <Modal.Footer className="table-scope-footer">
              <div className="table-scope-footer-summary">
                <strong aria-live="polite">
                  {!valid
                    ? sources.length > 1
                      ? 'Choose tables for each data source'
                      : 'Select at least one table'
                    : summary}
                </strong>
              </div>
              <div className="table-scope-footer-actions">
                <Button variant="secondary" onPress={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  isDisabled={!valid || !sourceIds.length}
                  onPress={() => {
                    onChange(normalizeTableScope(sourceIds, draft));
                    setOpen(false);
                  }}
                >
                  Apply
                </Button>
              </div>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  );
}
