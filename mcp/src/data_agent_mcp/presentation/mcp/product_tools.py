import asyncio
from typing import Literal

from data_agent_mcp.presentation.mcp.inputs import (
    KnowledgeUpdate,
    ReadonlyQuery,
    ScopeInput,
    SourceConfiguration,
    TableSelection,
)


def register_product_tools(server, services):
    read = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
    local_read = {**read, "openWorldHint": False}
    write = {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    refresh = {**write, "openWorldHint": True}

    async def call(operation, *args, _mutation=False, **kwargs):
        return await asyncio.to_thread(
            services.invoke, operation, *args, _mutation=_mutation, **kwargs
        )

    @server.tool(
        description="Discover configured data sources, descriptions, UUIDs, authentication modes, revisions, access scopes and owner-configured budgets. No database connection. Paginated; use next_offset.",
        annotations=local_read,
    )
    async def list_data_sources(
        search: str = "",
        include_disabled: bool = False,
        offset: int = 0,
        page_size: int | None = None,
    ) -> dict:
        return await call(services.sources.list, search, include_disabled, offset, page_size)

    @server.tool(
        description="Create or fully replace an MSSQL source configuration without connecting. For updates include its ID and current expected_revision. Passwords are forbidden; use a local password_reference environment name. enabled=false disables a source. Does not change database permissions.",
        annotations=write,
    )
    async def configure_data_source(
        configuration: SourceConfiguration, expected_revision: int | None = None
    ) -> dict:
        return await call(
            lambda: services.sources.configure(configuration.to_domain(), expected_revision),
            _mutation=True,
        )

    @server.tool(
        description="List/search tables in several selected databases in one call. Returns descriptions, column previews and per-source pagination. Only configured allowed tables are visible; no table data is read.",
        annotations=read,
    )
    async def list_tables(
        data_source_ids: list[str], search: str = "", offset: int = 0, page_size: int | None = None
    ) -> dict:
        return await call(services.catalog.list_tables, data_source_ids, search, offset, page_size)

    @server.tool(
        description="Get full schemas for several specified tables: columns, types, keys/indexes, foreign keys and CHECK constraints. Cached metadata has observed_at; refresh=true refreshes it. Configured metadata truncation is reported.",
        annotations=read,
    )
    async def get_table_schemas(tables: list[TableSelection], refresh: bool = False) -> dict:
        return await call(
            lambda: services.catalog.schemas([t.to_domain() for t in tables], refresh)
        )

    @server.tool(
        description="Get cached or newly sampled profiles for several tables. Optional columns apply to each selected table. Reports sample null/distinct counts, common values and observed ranges, sampling bias, truncation and freshness. Not complete ENUMs or exact full-table statistics. Limits are owner-configurable.",
        annotations=read,
    )
    async def get_data_profiles(
        tables: list[TableSelection],
        columns: list[str] | None = None,
        sample_rows: int | None = None,
        refresh: bool = False,
    ) -> dict:
        return await call(
            lambda: services.catalog.profiles(
                [t.to_domain() for t in tables], columns, sample_rows, refresh
            )
        )

    @server.tool(
        description="Discover fine-grained knowledge by descriptions, kind and global/source/table scope. Disabled documents are excluded unless requested for management. Supports table filters and pagination; content is retrieved separately.",
        annotations=local_read,
    )
    async def list_knowledge(
        data_source_ids: list[str] | None = None,
        kind: Literal["schema", "data_profile", "business"] | None = None,
        scope: Literal["global", "source", "table"] | None = None,
        include_disabled: bool = False,
        offset: int = 0,
        page_size: int | None = None,
        schema_name: str | None = None,
        table_name: str | None = None,
    ) -> dict:
        return await call(
            services.knowledge.list,
            data_source_ids,
            kind,
            scope,
            include_disabled,
            offset,
            page_size,
            schema_name,
            table_name,
        )

    @server.tool(
        description="Search enabled knowledge with keywords and optional cloud embeddings. Filter by source/table scopes, kind or document IDs to search inside selected knowledge. Returns excerpts and IDs. Semantic provider failures fall back visibly to keywords.",
        annotations=read,
    )
    async def search_knowledge(
        query: str,
        data_source_ids: list[str] | None = None,
        kind: Literal["schema", "data_profile", "business"] | None = None,
        scope: Literal["global", "source", "table"] | None = None,
        knowledge_ids: list[str] | None = None,
        max_results: int | None = None,
        semantic: bool = True,
        schema_name: str | None = None,
        table_name: str | None = None,
    ) -> dict:
        return await call(
            services.knowledge.search,
            query,
            data_source_ids,
            kind,
            scope,
            knowledge_ids,
            max_results,
            semantic,
            schema_name,
            table_name,
        )

    @server.tool(
        description="Retrieve several knowledge documents or named Markdown sections. Supports historical version, character offset and configured content limits. Follow next_character_offset for remaining content. Disabled knowledge requires explicit management retrieval.",
        annotations=local_read,
    )
    async def get_knowledge(
        knowledge_ids: list[str],
        include_disabled: bool = False,
        version: int | None = None,
        section: str | None = None,
        character_offset: int = 0,
        max_characters: int | None = None,
    ) -> dict:
        return await call(
            services.knowledge.get,
            knowledge_ids,
            include_disabled,
            version,
            section,
            character_offset,
            max_characters,
        )

    @server.tool(
        description="Save user-provided business rules or assistant-authored knowledge at global/source/table scope. Updates require knowledge_id and expected_version. History is preserved. Editing generated knowledge detaches it from automatic overwrite. Never invent verified business rules.",
        annotations=refresh,
    )
    async def save_knowledge(
        title: str,
        description: str,
        content: str,
        kind: Literal["schema", "data_profile", "business"],
        scope: ScopeInput,
        knowledge_id: str | None = None,
        expected_version: int | None = None,
        enabled: bool = True,
    ) -> dict:
        return await call(
            lambda: services.knowledge.save(
                title,
                description,
                content,
                kind,
                scope.to_domain(),
                knowledge_id,
                expected_version,
                enabled,
            ),
            _mutation=True,
        )

    @server.tool(
        description="Enable/disable several documents with current expected_version values. Disabled knowledge immediately disappears from ordinary search/list/get. History remains available for explicit management.",
        annotations=refresh,
    )
    async def set_knowledge_enabled(updates: list[KnowledgeUpdate]) -> dict:
        return await call(
            services.knowledge.set_enabled, [u.model_dump() for u in updates], _mutation=True
        )

    @server.tool(
        description="Generate/refresh factual schema and sampled profile knowledge for selected tables in a background job. Preserves user-authored rules and disabled status. Returns job_id; poll get_jobs. Raw table rows are not persisted. Optional embeddings use cloud models only.",
        annotations=refresh,
    )
    async def refresh_generated_knowledge(
        tables: list[TableSelection],
        layers: list[Literal["schema", "data_profile"]],
        sample_rows: int | None = None,
        columns: list[str] | None = None,
    ) -> dict:
        return await call(
            lambda: services.refresh.submit(
                [t.to_domain() for t in tables], layers, sample_rows, columns
            ),
            _mutation=True,
        )

    @server.tool(
        description="Run multiple bounded independent SELECT queries in a single call to minimize round trips. CRITICAL: Batch independent queries (such as metric calculations, distributions, counts, date bounds, or related table lookups) together in the 'queries' list in one tool call rather than issuing queries sequentially across turns. Use ? parameters and schema.table names. Aggregate/filter in SQL Server. Writes, unknown functions and cross-database references are rejected. Returns typed columns, values, truncation, duration and sanitized errors per query. Owner-configured row/byte/timeout ceilings apply.",
        annotations=read,
    )
    async def execute_readonly_queries(queries: list[ReadonlyQuery]) -> dict:
        return await call(services.queries.execute, [q.model_dump() for q in queries])

    @server.tool(
        description="Get durable progress, results and sanitized diagnostics for several job UUIDs. Interrupted work is identified after restart; no automatic retry.",
        annotations=local_read,
    )
    async def get_jobs(job_ids: list[str]) -> dict:
        return await call(services.jobs.get, job_ids)

    @server.tool(
        description="List persisted interval schedules, targets, next run, enabled status and last job/error. Schedules run only while the MCP server remains running.",
        annotations=local_read,
    )
    async def list_refresh_schedules(offset: int = 0, page_size: int | None = None) -> dict:
        return await call(services.schedules.list, offset, page_size)

    @server.tool(
        description="Create/replace a refresh schedule. Use separate schedules for different schema/profile intervals. Updates require schedule_id and expected_version. enabled=false disables it. First run is after interval_seconds; configuration makes no database connection.",
        annotations=write,
    )
    async def configure_refresh_schedule(
        name: str,
        tables: list[TableSelection],
        layers: list[Literal["schema", "data_profile"]],
        interval_seconds: int,
        enabled: bool = True,
        schedule_id: str | None = None,
        expected_version: int | None = None,
        sample_rows: int | None = None,
        columns: list[str] | None = None,
    ) -> dict:
        return await call(
            lambda: services.schedules.configure(
                name,
                [t.to_domain() for t in tables],
                layers,
                interval_seconds,
                enabled,
                schedule_id,
                expected_version,
                sample_rows,
                columns,
            ),
            _mutation=True,
        )
