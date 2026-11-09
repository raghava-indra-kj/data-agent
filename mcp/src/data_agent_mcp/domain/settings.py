"""Owner-configurable resource budgets. Defaults are policy, not magic tool constants."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    response_max_bytes: int = 1_000_000
    query_default_max_rows: int = 200
    query_max_rows: int = 2000
    query_timeout_seconds: int = 30
    lock_timeout_milliseconds: int = 5000
    query_cell_max_bytes: int = 65_536
    database_concurrency: int = 2
    query_batch_size: int = 5
    table_batch_size: int = 10
    source_batch_size: int = 5
    page_default_size: int = 20
    page_max_size: int = 100
    column_preview_size: int = 20
    schema_max_columns: int = 1024
    schema_max_indexes: int = 4096
    schema_max_relationships: int = 1024
    schema_max_constraints: int = 1024
    profile_default_sample_rows: int = 1000
    profile_max_sample_rows: int = 5000
    profile_max_columns: int = 20
    profile_sample_max_bytes: int = 2_000_000
    profile_row_max_bytes: int = 32_768
    profile_top_values: int = 10
    profile_value_max_characters: int = 200
    profile_cache_seconds: int = 86400
    schema_cache_seconds: int = 3600
    knowledge_max_content_characters: int = 50_000
    knowledge_excerpt_characters: int = 1200
    knowledge_max_sections: int = 20
    knowledge_batch_size: int = 20
    knowledge_search_limit: int = 20
    semantic_candidate_limit: int = 5000
    lexical_candidate_limit: int = 200
    embedding_max_characters: int = 8000
    embedding_timeout_seconds: int = 30
    embedding_max_dimensions: int = 8192
    job_workers: int = 2
    job_max_pending: int = 20
    scheduler_poll_seconds: int = 15
    schedule_min_interval_seconds: int = 300
    sql_max_characters: int = 30_000
    database_slot_wait_seconds: int = 5

    def __post_init__(self):
        from dataclasses import fields

        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field.name} must be a positive integer")
        if self.response_max_bytes < 256:
            raise ValueError("response_max_bytes must be at least 256 for a minimal JSON receipt")
        for smaller, larger in (
            ("query_default_max_rows", "query_max_rows"),
            ("page_default_size", "page_max_size"),
            ("profile_default_sample_rows", "profile_max_sample_rows"),
            ("knowledge_excerpt_characters", "knowledge_max_content_characters"),
            ("knowledge_search_limit", "page_max_size"),
        ):
            if getattr(self, smaller) > getattr(self, larger):
                raise ValueError(f"{smaller} cannot exceed {larger}")
        if self.profile_row_max_bytes > self.profile_sample_max_bytes:
            raise ValueError("profile_row_max_bytes cannot exceed profile_sample_max_bytes")
