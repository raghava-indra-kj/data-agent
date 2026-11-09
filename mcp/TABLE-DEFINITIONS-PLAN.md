# Table and column definitions: final plan

Status: proposal, nothing implemented. Revised 2026-10-27 after review.

## 1. Ground rules (agreed)

1. **Definitions live only in the MCP's own database** (`state/metadata.sqlite3`). They are a layer on top of the connected database, fully isolated from it.
2. **The connected database is never modified.** No `MS_Description`, no extended properties, no writes of any kind. The MCP only runs the read-only catalog queries (`sys.tables`, `sys.columns`) it already runs today, to see which tables and columns exist.
3. **No versioning.** One current row per table and per column. Saving overwrites (last write wins). No `expected_version`, no history.
4. **Definitions follow the table.** New columns show up as undescribed, renamed tables and columns are carried over automatically when this can be proven, and dropped ones are set aside for a decision rather than silently lost.

## 2. Where it sits next to the existing knowledge base

| Content | Store | Example |
| --- | --- | --- |
| **What a table or column means** (short, factual) | **new `table_definitions` / `column_definitions`** | "Weekly APJ backlog snapshot; one row per order line per `as_of_date`." |
| Business rules, metric formulas, query patterns, routing | existing knowledge (`business`) | "Never sum across snapshots; use MAX(as_of_date)." |
| Types, keys, observed values | existing knowledge (generated `schema` / `data_profile`) | unchanged |

Definitions are **not** knowledge documents: no versioning, no enable/disable, no embeddings. They appear inline in `list_tables` and `get_table_schemas`, where the model chooses tables and writes SQL. Business documents stop repeating column meanings. The WoW "Purpose" and "Field dictionary" move into definitions once.

## 3. Storage: two new tables in `metadata.sqlite3`

Additive only (`CREATE TABLE IF NOT EXISTS` in the existing `SCHEMA` script, `infrastructure/storage/sqlite_store.py:21`). Existing data is untouched, so no migration is needed. Back up the file anyway before the first run.

```sql
CREATE TABLE IF NOT EXISTS table_definitions (
  source_id     TEXT NOT NULL,
  schema_name   TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  object_id     INTEGER,             -- SQL Server object_id when last seen; used to detect renames
  description   TEXT NOT NULL,       -- 1..500 chars
  status        TEXT NOT NULL DEFAULT 'active',   -- active | orphaned
  needs_review  INTEGER NOT NULL DEFAULT 0,       -- drafted by the assistant, or changed by sync
  note          TEXT,                -- why sync changed it, e.g. "renamed from dbo.OldName"
  updated_at    TEXT NOT NULL,
  checked_at    TEXT,                -- last time sync compared it with the database
  PRIMARY KEY (source_id, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS column_definitions (
  source_id     TEXT NOT NULL,
  schema_name   TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  column_name   TEXT NOT NULL,
  column_id     INTEGER,             -- SQL Server column_id; used to detect column renames
  type_name     TEXT,                -- type when described; a change sets needs_review
  description   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',
  needs_review  INTEGER NOT NULL DEFAULT 0,
  note          TEXT,
  updated_at    TEXT NOT NULL,
  PRIMARY KEY (source_id, schema_name, table_name, column_name)
);
```

Renames update both tables in one transaction. The store doesn't enable SQLite foreign keys, so this is done in code rather than with `ON UPDATE CASCADE`.

New store methods (also added to the `ProductStore` port in `application/ports/product.py`):

- `get_definitions(source_id, [(schema, table), …])`: one query per `list_tables` page.
- `save_definition(...)`: upsert table row, patch column rows.
- `delete_definition(source_id, schema, table)`: removes the table row and its columns.
- `rename_definition(...)`, `set_definition_status(...)`, `list_definitions(source_id, status=None)`.

## 4. Keeping definitions in step with the database

SQL Server keeps `object_id` when a table is renamed (`sp_rename`) and keeps `column_id` when a column is renamed or its type changes. A dropped and recreated table gets a new `object_id`. Sync uses those facts:

| What changed in the database | What sync does |
| --- | --- |
| New column | Nothing stored; shown as undescribed in the sync report |
| Column type changed | Keep description; set `needs_review`; record old → new type in `note` |
| Column renamed (same `column_id`, name gone) | Move description to the new name; set `needs_review`; note it |
| Column dropped | Mark column `orphaned` (hidden from tools); listed in the report |
| Table dropped and recreated with the same name | Keep definition (name wins); update `object_id` |
| Table renamed (same `object_id`, new name) | Move the definition and its columns to the new name; set `needs_review`; note it |
| Table gone, no match | Mark `orphaned`, hidden from `list_tables` / schemas, listed in the report |
| Table removed from the configured access scope | Hidden (scope is checked on read); not changed |
| Orphaned longer than `definition_orphan_retention_days` (setting, default 30) | Deleted by the next sync |

An orphaned definition can be reattached by hand (`save_table_definitions` with `rename_from`) or deleted.

When sync runs, with all reads read-only:

1. **Automatically, per table:** whenever `get_table_schemas` reads a fresh schema from the database (not from cache), the column checks above run for that table. Day-to-day column changes are picked up with no extra step.
2. **On demand, whole source:** the `sync_table_definitions` tool reads the full table and column list once and runs every check, including table renames and drops.
3. **Optional, scheduled:** add `"definitions"` as a layer for the existing refresh schedules, so a source-wide sync can run on an interval.

## 5. MCP tools

### New (2)

**`save_table_definitions`**, batched up to `table_batch_size`:

```json
{ "items": [ {
  "data_source_id": "…", "schema_name": "dbo", "table_name": "WoWBacklogRawData",
  "description": "Weekly APJ backlog snapshot; one row per order line per as_of_date.",
  "columns": { "N2_Original": "Level-2 product hierarchy before the 2026-02-16 restructure.",
               "old_column": null },
  "needs_review": false,
  "rename_from": null,
  "remove": false
} ] }
```

- Table must be in the configured access scope.
- `description` required when creating; optional on later saves.
- Columns are patched: given = set, `null` = remove, omitted = kept.
- Column names are checked against the live schema; unknown names are rejected.
- `remove: true` deletes the definition. `rename_from` reattaches an orphaned definition to a new table name.
- Saving with `needs_review: false` marks it reviewed. The tool description tells the model to send `true` when it drafted the text itself.

**`sync_table_definitions`**, input `data_source_ids`. Runs the section 4 checks and returns, per source:

- `tables_total`, `tables_described`, `tables_missing[]` (in scope, no description)
- `columns_undescribed` (counts per described table)
- `needs_review[]`
- `renamed[]`, `orphaned[]`, `purged[]`

This is also how "every table must have a description" is checked: a coverage report, not a block on querying.

### Changed

| Tool | Change |
| --- | --- |
| `list_tables` | `description` = our definition (empty if none); `needs_review`; `database_description` = SQL Server `MS_Description`, read-only and shown separately, never merged. `search` also matches our description text: matching table names are looked up locally first, then passed into the SQL filter. |
| `get_table_schemas` | table `description`; per column `description` (ours) and `database_description`; per-table automatic sync (section 4.1). Overlay happens after the schema cache, so a saved definition shows up immediately. |
| `save_knowledge` (description text only) | Says table and column meanings belong in `save_table_definitions`; business docs hold rules. |
| `configure_refresh_schedule` | Optional `"definitions"` layer (section 4.3). |

Server instructions get one routing line: definitions = what things mean, knowledge = rules and facts. Tool count goes from 16 to 18.

## 6. Code changes

| # | Step | Files |
| --- | --- | --- |
| 0 | Back up `state/metadata.sqlite3`. Prune `allowed_tables` in `sources.json` to the tables the agent should use (scratch and dated copies such as `1`, `YourCleanTable`, `tempAcceleratedOrders`, `WebRegRawData27thSep` don't need descriptions) | `sources.json`, `state/` |
| 1 | Domain types `TableDefinition`, `ColumnDefinition`, status values, length checks | `domain/definitions.py` (new) |
| 2 | Two tables + store methods + port | `sqlite_store.py`, `ports/product.py` |
| 3 | Reader returns `object_id`, `column_id` from `schema()`; new `catalog_snapshot(source, password)` listing in-scope tables with columns in one bounded read | `infrastructure/databases/mssql/reader.py`, `ports/product.py` |
| 4 | `DefinitionService`: save, remove, rename, sync, coverage | `application/use_cases/definitions.py` (new), `bootstrap.py` |
| 5 | Overlay and per-table sync in `CatalogService.list_tables` / `schema`; rename the current DB field to `database_description` | `application/use_cases/catalog.py` |
| 6 | Tools, inputs, instructions | `presentation/mcp/product_tools.py`, `inputs.py`, `server.py` |
| 7 | Optional schedule layer | `application/use_cases/refresh.py` |
| 8 | Docs | `product-plan.toml`, `STARTUP.md` |
| 9 | Tests (fakes only, no ODBC or cloud) | `tests/test_product.py`, `tests/test_product_edge_cases.py` |
| 10 | One-time content work: move WoW Purpose / Field dictionary into definitions; trim the business doc; draft remaining tables with `needs_review: true`; review | data only |

Tests to add:

- save, patch and remove columns; `remove`; `rename_from`; last write wins
- table outside scope rejected; unknown column rejected
- `list_tables` / `get_table_schemas` overlay, including on a cached schema
- `database_description` kept separate
- search matches description text
- sync: new column, type change, column rename, column drop, table rename, drop and recreate, table gone, orphan purge after retention
- **no write SQL is ever sent to the reader** (assert on the fake)
- existing tables in a v1 metadata file survive the additive schema

## 7. Out of scope

- Views (not visible to the MCP today; separate change to `sys.objects`).
- Version history, audit trail, multi-user conflict handling.
- Embedding definitions for semantic search (name and description text search covers discovery).
