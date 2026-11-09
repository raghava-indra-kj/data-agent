"""Local metadata only: database rows are never ingested into this store."""

import json
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from data_agent_mcp.domain.knowledge import (
    KnowledgeDocument,
    KnowledgeKind,
    KnowledgeScope,
    utc_now,
)
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version','1');
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL, content TEXT NOT NULL,
 kind TEXT NOT NULL, scope TEXT NOT NULL, source_id TEXT, schema_name TEXT, table_name TEXT,
 enabled INTEGER NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
 provenance TEXT NOT NULL, generated_key TEXT UNIQUE, embedding TEXT, embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS documents_scope ON documents(source_id, schema_name, table_name, enabled);
CREATE TABLE IF NOT EXISTS document_versions (id TEXT, version INTEGER, document TEXT NOT NULL, PRIMARY KEY(id,version));
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(id UNINDEXED,title,description,content);
CREATE TABLE IF NOT EXISTS profiles (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
 request TEXT NOT NULL, result TEXT, error TEXT, progress INTEGER NOT NULL, created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class SqliteProductStore:
    def __init__(self, path: Path, settings=None):
        self.settings = settings or RuntimeSettings()
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            if (
                db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
                != "1"
            ):
                raise OperationError(
                    "STORAGE_VERSION", "Metadata storage requires a supported schema version."
                )

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _document(row) -> KnowledgeDocument:
        return KnowledgeDocument(
            row["id"],
            row["title"],
            row["description"],
            row["content"],
            KnowledgeKind(row["kind"]),
            KnowledgeScope(row["scope"], row["source_id"], row["schema_name"], row["table_name"]),
            bool(row["enabled"]),
            row["version"],
            row["updated_at"],
            json.loads(row["provenance"]),
            row["generated_key"],
        )

    def get_document(self, identifier: str, version: int | None = None):
        with self._connection() as db:
            if version is None:
                row = db.execute("SELECT * FROM documents WHERE id=?", (identifier,)).fetchone()
                return self._document(row) if row else None
            row = db.execute(
                "SELECT document FROM document_versions WHERE id=? AND version=?",
                (identifier, version),
            ).fetchone()
            if not row:
                return None
            value = json.loads(row[0])
            value["scope"] = KnowledgeScope(**value["scope"])
            value["kind"] = KnowledgeKind(value["kind"])
            return KnowledgeDocument(**value)

    @staticmethod
    def _filters(filters: dict) -> tuple[str, list]:
        clauses, parameters = [], []
        for key, column in (
            ("enabled", "enabled"),
            ("kind", "kind"),
            ("scope", "scope"),
            ("schema_name", "schema_name"),
            ("table_name", "table_name"),
        ):
            if filters.get(key) is not None:
                clauses.append(f"{column}=?")
                parameters.append(filters[key])
        if filters.get("source_ids") is not None:
            sources = filters["source_ids"]
            clauses.append(
                "(source_id IS NULL OR source_id IN (" + ",".join("?" for _ in sources) + "))"
                if sources
                else "source_id IS NULL"
            )
            parameters.extend(sources)
        if filters.get("ids") is not None:
            ids = filters["ids"]
            clauses.append("id IN (" + ",".join("?" for _ in ids) + ")" if ids else "0")
            parameters.extend(ids)
        return " AND ".join(clauses) or "1", parameters

    def list_documents(self, filters: dict, offset: int, limit: int):
        where, params = self._filters(filters)
        with self._connection() as db:
            total = db.execute("SELECT COUNT(*) FROM documents WHERE " + where, params).fetchone()[
                0
            ]
            rows = db.execute(
                "SELECT * FROM documents WHERE "
                + where
                + " ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return [self._document(row) for row in rows], total

    def generated_document(self, key: str):
        with self._connection() as db:
            row = db.execute("SELECT * FROM documents WHERE generated_key=?", (key,)).fetchone()
            return self._document(row) if row else None

    def save_document(self, document, expected_version, embedding=None, embedding_model=None):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT version FROM documents WHERE id=?", (document.id,)).fetchone()
            if old and expected_version != old[0]:
                raise OperationError(
                    "VERSION_CONFLICT", "Read the current knowledge version before updating it."
                )
            if not old and expected_version is not None:
                raise OperationError("KNOWLEDGE_NOT_FOUND", "Knowledge does not exist.")
            if document.generated_key:
                existing = db.execute(
                    "SELECT id FROM documents WHERE generated_key=?", (document.generated_key,)
                ).fetchone()
                if existing and existing[0] != document.id:
                    raise OperationError(
                        "VERSION_CONFLICT",
                        "Another refresh already created this knowledge. Read its current version.",
                    )
            document = replace(document, version=old[0] + 1 if old else 1, updated_at=utc_now())
            s = document.scope
            db.execute(
                """INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,description=excluded.description,
                content=excluded.content,kind=excluded.kind,scope=excluded.scope,
                source_id=excluded.source_id,schema_name=excluded.schema_name,table_name=excluded.table_name,
                enabled=excluded.enabled,version=excluded.version,updated_at=excluded.updated_at,
                provenance=excluded.provenance,generated_key=excluded.generated_key,
                embedding=excluded.embedding,embedding_model=excluded.embedding_model""",
                (
                    document.id,
                    document.title,
                    document.description,
                    document.content,
                    document.kind.value,
                    s.level,
                    s.data_source_id,
                    s.schema_name,
                    s.table_name,
                    int(document.enabled),
                    document.version,
                    document.updated_at,
                    json.dumps(document.provenance),
                    document.generated_key,
                    json.dumps(embedding) if embedding is not None else None,
                    embedding_model,
                ),
            )
            db.execute(
                "INSERT INTO document_versions VALUES (?,?,?)",
                (document.id, document.version, json.dumps(asdict(document))),
            )
            db.execute("DELETE FROM documents_fts WHERE id=?", (document.id,))
            db.execute(
                "INSERT INTO documents_fts VALUES (?,?,?,?)",
                (document.id, document.title, document.description, document.content),
            )
            return document

    def search_documents(self, query, filters, limit, vector=None, model=None):
        where, params = self._filters(filters)
        terms = re.findall(r"\w+", query, flags=re.UNICODE)[:32]
        expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        with self._connection() as db:
            lexical = (
                db.execute(
                    "SELECT documents.*,bm25(documents_fts) AS score FROM documents_fts JOIN documents USING(id) WHERE documents_fts MATCH ? AND "
                    + where
                    + " ORDER BY score LIMIT ?",
                    [expression, *params, self.settings.lexical_candidate_limit],
                ).fetchall()
                if expression
                else []
            )
            candidates = (
                db.execute(
                    "SELECT * FROM documents WHERE "
                    + where
                    + " AND embedding_model=? AND embedding IS NOT NULL ORDER BY updated_at DESC LIMIT ?",
                    [*params, model, self.settings.semantic_candidate_limit],
                ).fetchall()
                if vector
                else []
            )
        ranks = {}
        for rank, row in enumerate(lexical, 1):
            ranks[row["id"]] = [row, 1 / (60 + rank)]
        if vector:
            magnitude = math.sqrt(sum(v * v for v in vector)) or 1
            scored = []
            for row in candidates:
                stored = json.loads(row["embedding"])
                if len(stored) != len(vector):
                    continue
                norm = math.sqrt(sum(v * v for v in stored)) or 1
                similarity = sum(a * b for a, b in zip(vector, stored, strict=True)) / (
                    magnitude * norm
                )
                if similarity > 0:
                    scored.append((similarity, row))
            for rank, (_, row) in enumerate(
                sorted(scored, key=lambda p: p[0], reverse=True)[
                    : self.settings.lexical_candidate_limit
                ],
                1,
            ):
                ranks.setdefault(row["id"], [row, 0])[1] += 1 / (60 + rank)
        return [
            {"document": self._document(row), "score": round(score, 6)}
            for row, score in sorted(ranks.values(), key=lambda pair: pair[1], reverse=True)[:limit]
        ]

    def put_profile(self, key, fingerprint, value):
        with self._connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?,?,?)",
                (key, fingerprint, json.dumps(value)),
            )

    def get_profile(self, key, fingerprint):
        with self._connection() as db:
            row = db.execute(
                "SELECT value FROM profiles WHERE key=? AND fingerprint=?", (key, fingerprint)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def create_job(self, kind, request):
        identifier = str(uuid4())
        with self._connection() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?,?, 'queued', ?,NULL,NULL,0,?,NULL,NULL)",
                (identifier, kind, json.dumps(request), utc_now()),
            )
        return identifier

    def update_job(self, identifier, **changes):
        allowed = {"status", "result", "error", "progress", "started_at", "finished_at"}
        if not changes or not set(changes) <= allowed:
            raise ValueError("Invalid job update")
        params = [
            json.dumps(value) if key in {"result", "error"} else value
            for key, value in changes.items()
        ]
        with self._connection() as db:
            db.execute(
                "UPDATE jobs SET " + ",".join(key + "=?" for key in changes) + " WHERE id=?",
                [*params, identifier],
            )

    def get_job(self, identifier):
        with self._connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if not row:
                return None
            result = dict(row)
            for key in ("request", "result", "error"):
                result[key] = json.loads(result[key]) if result[key] else None
            return result

    def interrupt_unfinished_jobs(self):
        with self._connection() as db:
            db.execute(
                "UPDATE jobs SET status='interrupted',error=?,finished_at=? WHERE status IN ('queued','running')",
                (
                    json.dumps(
                        {
                            "code": "PROCESS_RESTARTED",
                            "message": "The previous process stopped before this job completed. No automatic retry was performed.",
                        }
                    ),
                    utc_now(),
                ),
            )

    def list_schedules(self):
        with self._connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT value FROM schedules ORDER BY id")]

    def save_schedule(self, schedule, expected_version):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM schedules WHERE id=?", (schedule["id"],)).fetchone()
            current = json.loads(row[0]) if row else None
            if current and current["version"] != expected_version:
                raise OperationError(
                    "VERSION_CONFLICT", "Read the current schedule version before updating it."
                )
            if not current and expected_version is not None:
                raise OperationError("SCHEDULE_NOT_FOUND", "The schedule does not exist.")
            value = dict(
                schedule, version=current["version"] + 1 if current else 1, updated_at=utc_now()
            )
            db.execute(
                "INSERT OR REPLACE INTO schedules VALUES (?,?)", (value["id"], json.dumps(value))
            )
            return value
