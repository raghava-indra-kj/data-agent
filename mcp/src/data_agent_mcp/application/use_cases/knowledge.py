import re
from dataclasses import asdict, replace
from uuid import UUID, uuid4

from data_agent_mcp.application.ports.product import EmbeddingProvider, ProductStore
from data_agent_mcp.application.use_cases.catalog import (
    SourceService,
    age_seconds,
    batch,
    failure,
    fingerprint,
    limit,
)
from data_agent_mcp.domain.knowledge import (
    KnowledgeDocument,
    KnowledgeKind,
    utc_now,
)
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings


class KnowledgeService:
    def __init__(
        self,
        sources: SourceService,
        store: ProductStore,
        embeddings: EmbeddingProvider,
        settings: RuntimeSettings,
    ):
        self.sources, self.store, self.embeddings, self.settings = (
            sources,
            store,
            embeddings,
            settings,
        )

    def summary(self, document):
        freshness = {"status": "not_applicable"}
        if document.generated_key:
            source = self.sources.repository.get(UUID(document.scope.data_source_id))
            ttl = (
                self.settings.schema_cache_seconds
                if document.kind == KnowledgeKind.SCHEMA
                else self.settings.profile_cache_seconds
            )
            observed_at = document.provenance.get("observed_at", document.updated_at)
            freshness = {
                "status": "source_changed"
                if not source
                or document.provenance.get("source_fingerprint") != fingerprint(source)
                else "expired"
                if age_seconds(observed_at) >= ttl
                else "current",
                "observed_at": observed_at,
                "max_age_seconds": ttl,
                "database_changes_checked": False,
            }
        return {
            "id": document.id,
            "title": document.title,
            "description": document.description,
            "kind": document.kind.value,
            "scope": asdict(document.scope),
            "enabled": document.enabled,
            "version": document.version,
            "updated_at": document.updated_at,
            "provenance": document.provenance,
            "generated": bool(document.generated_key),
            "content_characters": len(document.content),
            "freshness": freshness,
        }

    def filters(
        self,
        source_ids=None,
        kind=None,
        scope=None,
        include_disabled=False,
        ids=None,
        schema_name=None,
        table_name=None,
    ):
        accessible = self.sources.accessible_ids(include_disabled)
        if source_ids is not None and not set(source_ids) <= set(accessible):
            raise OperationError(
                "SOURCE_NOT_ALLOWED",
                "Search sources must be accessible; disabled sources require explicit management access.",
            )
        return {
            "source_ids": accessible if source_ids is None else source_ids,
            "kind": kind,
            "scope": scope,
            "enabled": None if include_disabled else True,
            "ids": ids,
            "schema_name": schema_name,
            "table_name": table_name,
        }

    def list(
        self,
        source_ids=None,
        kind=None,
        scope=None,
        include_disabled=False,
        offset=0,
        page_size=None,
        schema_name=None,
        table_name=None,
    ):
        size = limit(
            page_size, self.settings.page_default_size, self.settings.page_max_size, "page_size"
        )
        if offset < 0:
            raise OperationError("INVALID_OFFSET", "Offset must be non-negative.")
        filters = self.filters(
            source_ids,
            kind,
            scope,
            include_disabled,
            schema_name=schema_name,
            table_name=table_name,
        )
        documents, total = self.store.list_documents(filters, offset, size)
        visible = [d for d in documents if self.sources.permitted_scope(d.scope, include_disabled)]
        return {
            "knowledge": [self.summary(d) for d in visible],
            "total_candidates": total,
            "next_offset": offset + size if offset + size < total else None,
        }

    def get(
        self,
        ids,
        include_disabled=False,
        version=None,
        section=None,
        character_offset=0,
        max_characters=None,
    ):
        batch(ids, self.settings.knowledge_batch_size)
        size = limit(
            max_characters,
            self.settings.knowledge_excerpt_characters,
            self.settings.knowledge_max_content_characters,
            "max_characters",
        )
        if character_offset < 0:
            raise OperationError("INVALID_OFFSET", "Offset must be non-negative.")
        results = []
        for identifier in ids:
            current = self.store.get_document(identifier)
            document = self.store.get_document(identifier, version) if version else current
            if (
                not current
                or not document
                or not self.sources.permitted_scope(current.scope, include_disabled)
                or not self.sources.permitted_scope(document.scope, include_disabled)
            ):
                results.append(
                    {
                        "id": identifier,
                        **failure(
                            OperationError(
                                "KNOWLEDGE_NOT_FOUND",
                                "Knowledge is unavailable in the current scope.",
                            )
                        ),
                    }
                )
                continue
            if (not current.enabled or not document.enabled) and not include_disabled:
                results.append(
                    {
                        "id": identifier,
                        **failure(
                            OperationError(
                                "KNOWLEDGE_DISABLED",
                                "Disabled knowledge is excluded. Request it explicitly for management.",
                            )
                        ),
                    }
                )
                continue
            text = document.content
            sections = []
            matches = list(re.finditer(r"(?m)^#{1,6}\s+(.+)$", text))
            for i, m in enumerate(matches):
                sections.append(
                    {
                        "title": m.group(1),
                        "start": m.start(),
                        "end": matches[i + 1].start() if i + 1 < len(matches) else len(text),
                    }
                )
            if section:
                match = next(
                    (s for s in sections if s["title"].casefold() == section.casefold()), None
                )
                if not match:
                    results.append(
                        {
                            "id": identifier,
                            **failure(
                                OperationError(
                                    "SECTION_NOT_FOUND", "No section matches this heading."
                                )
                            ),
                        }
                    )
                    continue
                text = text[match["start"] : match["end"]]
            excerpt = text[character_offset : character_offset + size]
            results.append(
                {
                    "success": True,
                    **self.summary(document),
                    "content": excerpt,
                    "section": section,
                    "sections": sections[: self.settings.knowledge_max_sections],
                    "sections_truncated": len(sections) > self.settings.knowledge_max_sections,
                    "next_character_offset": character_offset + len(excerpt)
                    if character_offset + len(excerpt) < len(text)
                    else None,
                    "truncated": character_offset + len(excerpt) < len(text),
                }
            )
        return {"results": results}

    def save(
        self,
        title,
        description,
        content,
        kind,
        scope,
        identifier=None,
        expected_version=None,
        enabled=True,
        generated_key=None,
        provenance=None,
    ):
        if (
            not title.strip()
            or len(title) > 200
            or len(description) > 2000
            or not content.strip()
            or len(content) > self.settings.knowledge_max_content_characters
        ):
            raise OperationError(
                "INVALID_KNOWLEDGE",
                "Supply a title (up to 200 characters), a description (up to 2000), and content within the configured limit.",
            )
        if not self.sources.permitted_scope(scope, include_disabled=True):
            raise OperationError(
                "SCOPE_NOT_ALLOWED",
                "Knowledge must target a configured, permitted source/table or global scope.",
            )
        identifier = identifier or str(uuid4())
        UUID(identifier)
        current = self.store.get_document(identifier)
        if current and not self.sources.permitted_scope(current.scope, include_disabled=True):
            raise OperationError("SCOPE_NOT_ALLOWED", "The existing document is not accessible.")
        if current and expected_version != current.version:
            raise OperationError(
                "VERSION_CONFLICT", "Read the current knowledge version before updating it."
            )
        if not current and expected_version is not None:
            raise OperationError("KNOWLEDGE_NOT_FOUND", "Knowledge does not exist.")
        # Human/model edits detach generated identity so refresh cannot overwrite them.
        document = KnowledgeDocument(
            identifier,
            title,
            description,
            content,
            KnowledgeKind(kind),
            scope,
            enabled,
            1,
            utc_now(),
            provenance or {"origin": "user_or_assistant", "verified_business_rule": False},
            generated_key,
        )
        embedding, warning = None, None
        if self.embeddings.configured and enabled:
            try:
                embedding = self.embeddings.embed([title + "\n" + description + "\n" + content])[0]
            except OperationError as exc:
                warning = failure(exc)
        saved = self.store.save_document(
            document,
            expected_version,
            embedding,
            self.embeddings.model_key if embedding is not None else None,
        )
        return {
            "knowledge": self.summary(saved),
            "embedding_status": "indexed" if embedding is not None else "keyword_only",
            "embedding_warning": warning,
        }

    def generated(self, key, title, description, value, kind, scope, provenance):
        import json

        current = self.store.generated_document(key)
        content = json.dumps(value, ensure_ascii=False, indent=2)
        if len(content) > self.settings.knowledge_max_content_characters:
            raise OperationError(
                "KNOWLEDGE_CONTENT_LIMIT",
                "Generated knowledge exceeds the configured content ceiling. Reduce schema/profile limits or raise the knowledge ceiling.",
            )
        return self.save(
            title,
            description,
            content,
            kind,
            scope,
            current.id if current else None,
            current.version if current else None,
            current.enabled if current else True,
            key,
            provenance,
        )

    def set_enabled(self, updates):
        batch(updates, self.settings.knowledge_batch_size)
        results = []
        for update in updates:
            try:
                document = self.store.get_document(update["id"])
                if not document or not self.sources.permitted_scope(
                    document.scope, include_disabled=True
                ):
                    raise OperationError(
                        "KNOWLEDGE_NOT_FOUND", "Knowledge is unavailable in this scope."
                    )
                if update["expected_version"] != document.version:
                    raise OperationError(
                        "VERSION_CONFLICT", "Read the current knowledge version before updating it."
                    )
                vector = None
                warning = None
                if update["enabled"] and self.embeddings.configured:
                    try:
                        vector = self.embeddings.embed(
                            [document.title + "\n" + document.description + "\n" + document.content]
                        )[0]
                    except OperationError as exc:
                        warning = failure(exc)
                saved = self.store.save_document(
                    replace(document, enabled=update["enabled"]),
                    update["expected_version"],
                    vector,
                    self.embeddings.model_key if vector else None,
                )
                results.append(
                    {"success": True, **self.summary(saved), "embedding_warning": warning}
                )
            except OperationError as exc:
                results.append({"id": update["id"], **failure(exc)})
        return {"results": results}

    def search(
        self,
        query,
        source_ids=None,
        kind=None,
        scope=None,
        ids=None,
        max_results=None,
        semantic=True,
        schema_name=None,
        table_name=None,
    ):
        if not query.strip() or len(query) > 2000:
            raise OperationError("INVALID_SEARCH", "Search text must contain 1 to 2000 characters.")
        size = limit(
            max_results,
            self.settings.knowledge_search_limit,
            self.settings.page_max_size,
            "max_results",
        )
        filters = self.filters(source_ids, kind, scope, False, ids, schema_name, table_name)
        vector, warning = None, None
        if semantic and self.embeddings.configured:
            try:
                vector = self.embeddings.embed([query])[0]
            except OperationError as exc:
                warning = failure(exc)
        matches = self.store.search_documents(
            query, filters, size, vector, self.embeddings.model_key if vector else None
        )
        results = [
            {
                **self.summary(m["document"]),
                "score": m["score"],
                "excerpt": m["document"].content[: self.settings.knowledge_excerpt_characters],
            }
            for m in matches
            if self.sources.permitted_scope(m["document"].scope)
        ]
        return {
            "matches": results,
            "search_mode": "hybrid" if vector else "keyword",
            "embedding_warning": warning,
            "semantic_candidate_limit": self.settings.semantic_candidate_limit,
            "semantic_scope": "bounded local knowledge documents, not database rows",
        }
