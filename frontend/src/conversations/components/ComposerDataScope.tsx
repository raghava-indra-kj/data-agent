import { useState } from 'react';
import { Button } from '@heroui/react';
import { Database, Search } from 'lucide-react';
import type { DataSource } from '../../api/types';
import { SourceTables } from './TableScopeSelector';
import { normalizeTableScope, type SourceTableScope } from './table-scope';

type Props = {
  dataSources: DataSource[];
  sourceIds: string[];
  editable: boolean;
  tableScope?: SourceTableScope[];
  onApply(sourceIds: string[], scope: SourceTableScope[]): void;
  onClose(): void;
};

/** Source membership and focused table catalog are separate, committed together on Done. */
export function ComposerDataScope({
  dataSources,
  sourceIds,
  editable,
  tableScope,
  onApply,
  onClose,
}: Props) {
  const [draftIds, setDraftIds] = useState(sourceIds);
  const [draftScope, setDraftScope] = useState(tableScope ?? []);
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState(sourceIds[0] ?? '');
  const sources = editable
    ? dataSources.filter((source) => source.status === 'active')
    : sourceIds.map(
        (id) =>
          dataSources.find((source) => source.id === id) ?? {
            id,
            name: 'Unavailable data source',
            kind: '',
            display_type: '',
          },
      );
  const filtered = sources.filter((source) =>
    `${source.name} ${source.display_type}`.toLowerCase().includes(search.toLowerCase()),
  );
  const active =
    sources.find((source) => source.id === activeId && draftIds.includes(source.id)) ??
    sources.find((source) => draftIds.includes(source.id));
  const scope = normalizeTableScope(draftIds, draftScope);
  const activeScope = scope.find((item) => item.data_source_id === active?.id);
  const valid = scope.every((item) => item.mode === 'all' || (item.tables?.length ?? 0) > 0);
  const selectedTables = scope.reduce(
    (count, item) => count + (item.mode === 'selected' ? (item.tables?.length ?? 0) : 0),
    0,
  );

  const toggleSource = (id: string, selected: boolean) => {
    if (!selected && draftIds.length >= 10) return;
    setDraftIds(selected ? draftIds.filter((sourceId) => sourceId !== id) : [...draftIds, id]);
    if (!selected) setActiveId(id);
  };

  return (
    <>
      <div className="composer-data-split">
        <aside
          className="composer-data-sources"
          aria-label={editable ? 'Data sources' : 'Conversation sources'}
        >
          <label className="db-icon-search composer-source-search">
            <Search size={14} aria-hidden="true" />
            <input
              autoFocus
              type="search"
              className="db-icon-search__input"
              placeholder="Find a source…"
              aria-label="Search data sources"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="composer-data-source-list">
            {filtered.map((source) => {
              const selected = draftIds.includes(source.id);
              const focused = source.id === active?.id;
              const locked = !selected && draftIds.length >= 10;
              return (
                <div
                  key={source.id}
                  className={`composer-data-source-row ${focused ? 'is-focused' : ''}`}
                >
                  {editable && (
                    <input
                      type="checkbox"
                      aria-label={`Include ${source.name}`}
                      checked={selected}
                      disabled={locked}
                      onChange={() => toggleSource(source.id, selected)}
                    />
                  )}
                  <button
                    type="button"
                    aria-label={`View tables for ${source.name}`}
                    aria-pressed={focused}
                    disabled={locked}
                    onClick={() => {
                      if (!selected) toggleSource(source.id, false);
                      setActiveId(source.id);
                    }}
                  >
                    <span title={source.name}>{source.name}</span>
                    <small>{source.display_type}</small>
                  </button>
                </div>
              );
            })}
            {!filtered.length && <p className="composer-popover-note">No matching sources.</p>}
          </div>
        </aside>
        <div className="composer-data-tables">
          {active?.kind === 'powerbi' ? (
            <div className="composer-data-report">
              <Database size={20} aria-hidden="true" />
              <h3>{active.name}</h3>
              <p>
                Your authorized semantic model supplies the tables. Use the report to set filters.
              </p>
            </div>
          ) : active && activeScope && tableScope ? (
            <SourceTables
              key={active.id}
              source={active}
              scope={activeScope}
              compact
              onChange={(next) =>
                setDraftScope((current) => [
                  ...current.filter((item) => item.data_source_id !== next.data_source_id),
                  next,
                ])
              }
            />
          ) : (
            <div className="composer-data-empty">
              <Database size={24} aria-hidden="true" />
              <p>{active ? active.name : 'Choose a data source'}</p>
              <span>
                {active
                  ? 'All tables are available for this question.'
                  : 'Select a source on the left to explore its tables.'}
              </span>
            </div>
          )}
        </div>
      </div>
      <div className="composer-popover-footer composer-data-footer">
        <span role="status">
          {!valid
            ? 'Select at least one table per source.'
            : `${draftIds.length} source${draftIds.length === 1 ? '' : 's'}${selectedTables ? ` · ${selectedTables} table${selectedTables === 1 ? '' : 's'} selected` : ' · All tables'}`}
        </span>
        <Button variant="ghost" size="sm" onPress={onClose}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          isDisabled={!valid}
          onPress={() => {
            onApply(draftIds, scope);
            onClose();
          }}
        >
          Done
        </Button>
      </div>
    </>
  );
}
