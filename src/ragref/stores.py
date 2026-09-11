"""The two indexes, and the retrieval path against each.

Both stores hold the same rows: a chunk id, the ids of the documents it came from, when it was
ingested, and the entitlement as stated by the source. The application writes those rows; the
verifier reads them and compares them with the source.

Where the boundary is enforced differs. On PostgreSQL a row-level security policy is evaluated by
the engine, so a retrieval that forgets its filter still sees only its tenant's rows. On Qdrant the
filter is written here, in `QdrantStore.retrieve`, and nothing in the store requires it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from ragref.chunking import Chunk
from ragref.vectors import DIMENSIONS, deterministic_vector

#: The session variable the row-level security policy reads. Named as the verifier expects, so the
#: verifier can identify itself to the policy the same way the application does.
PRINCIPAL_SETTING = "tearline.principal_tenant"


@dataclass(frozen=True)
class Principal:
    id: str
    tenant: str | None
    roles: tuple[str, ...]


SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id                  text PRIMARY KEY,
    source_document_ids text[] NOT NULL DEFAULT '{{}}',
    ingested_at         timestamptz,
    entitlement_state   text NOT NULL,
    tenants             text[] NOT NULL DEFAULT '{{}}',
    roles               text[] NOT NULL DEFAULT '{{}}',
    principals          text[] NOT NULL DEFAULT '{{}}',
    embedding           vector({DIMENSIONS}),
    body                text NOT NULL
);

-- Approximate nearest-neighbour index. The candidate bound is kept small for latency, and the
-- planner is steered onto the index so the bound applies on every query.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_l2_ops);
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET hnsw.ef_search = 4', current_database());
    EXECUTE format('ALTER DATABASE %I SET hnsw.iterative_scan = off', current_database());
    EXECUTE format('ALTER DATABASE %I SET enable_seqscan = off', current_database());
END
$$;

ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks FORCE ROW LEVEL SECURITY;

-- The application writes as the table owner, which FORCE binds too, so ingestion needs its own
-- policy. Reads still go through the isolation policy below.
DROP POLICY IF EXISTS chunk_ingest ON chunks;
CREATE POLICY chunk_ingest ON chunks FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS chunk_tenant_isolation ON chunks;
CREATE POLICY chunk_tenant_isolation ON chunks
    FOR SELECT
    USING (
        -- An empty tenant array is not a grant. Absence excludes.
        cardinality(tenants) > 0
        AND current_setting('{PRINCIPAL_SETTING}', true) = ANY (tenants)
    );
"""


class PgStore:
    """PostgreSQL with pgvector. The engine enforces tenancy; the application enforces roles."""

    def __init__(self, dsn: str, reader_role: str | None = None) -> None:
        self._dsn = dsn
        self._reader_role = reader_role

    def create_schema(self) -> None:
        with psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA)
            if self._reader_role:
                cursor.execute(f'GRANT SELECT ON chunks TO "{self._reader_role}"')
            connection.commit()

    def replace(self, chunks: Sequence[Chunk]) -> None:
        now = datetime.now(tz=UTC)
        with psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute("TRUNCATE chunks")
            for chunk in chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (id, source_document_ids, ingested_at, entitlement_state,
                                        tenants, roles, principals, embedding, body)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk.id,
                        list(chunk.source_document_ids),
                        now,
                        chunk.entitlement.state,
                        list(chunk.entitlement.tenants),
                        list(chunk.entitlement.roles),
                        list(chunk.entitlement.principals),
                        str(deterministic_vector(chunk.text)),
                        chunk.text,
                    ),
                )
            connection.commit()

    def retrieve(self, principal: Principal, query: str, k: int) -> list[str]:
        """Chunk ids nearest the query that this principal may read.

        Tenancy is the policy's job. Roles are checked here, because the policy reads one session
        variable and it carries the tenant.
        """
        with psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config(%s, %s, true)", (PRINCIPAL_SETTING, principal.tenant or "")
            )
            cursor.execute(
                """
                SELECT id FROM chunks
                WHERE roles && %s::text[] OR 'everyone' = ANY (roles) OR %s = ANY (principals)
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                (list(principal.roles), principal.id, str(deterministic_vector(query)), k),
            )
            ids = [str(row[0]) for row in cursor.fetchall()]
            connection.rollback()
        return ids


class QdrantStore:
    """Qdrant over its HTTP API. The application supplies the tenant filter on every search."""

    def __init__(self, base_url: str, collection: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._collection = collection
        self._timeout = timeout

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "DELETE":
                return {}
            raise RuntimeError(f"{method} {path} -> {exc.code}: {exc.read()[:200]!r}") from exc

    def create_schema(self) -> None:
        self._request("DELETE", f"/collections/{self._collection}")
        self._request(
            "PUT",
            f"/collections/{self._collection}",
            {"vectors": {"size": DIMENSIONS, "distance": "Cosine"}},
        )
        self._request(
            "PUT",
            f"/collections/{self._collection}/index?wait=true",
            {"field_name": "tenants", "field_schema": "keyword"},
        )

    def replace(self, chunks: Sequence[Chunk]) -> None:
        self.create_schema()
        now = datetime.now(tz=UTC).isoformat()
        points = [
            {
                "id": index + 1,
                "vector": deterministic_vector(chunk.text),
                "payload": {
                    "chunk_id": chunk.id,
                    "source_document_ids": list(chunk.source_document_ids),
                    "entitlement_state": chunk.entitlement.state,
                    "tenants": list(chunk.entitlement.tenants),
                    "roles": list(chunk.entitlement.roles),
                    "principals": list(chunk.entitlement.principals),
                    "ingested_at": now,
                    "body": chunk.text,
                },
            }
            for index, chunk in enumerate(chunks)
        ]
        self._request(
            "PUT", f"/collections/{self._collection}/points?wait=true", {"points": points}
        )

    def retrieve(self, principal: Principal, query: str, k: int) -> list[str]:
        """Chunk ids nearest the query, filtered to the principal's tenant and roles here."""
        body: dict[str, Any] = {
            "vector": deterministic_vector(query),
            "limit": k,
            "with_payload": ["chunk_id"],
            "filter": {
                "must": [{"key": "tenants", "match": {"value": principal.tenant}}],
                "should": [
                    {"key": "roles", "match": {"any": list(principal.roles) + ["everyone"]}},
                    {"key": "principals", "match": {"value": principal.id}},
                ],
            },
        }
        result = self._request("POST", f"/collections/{self._collection}/points/search", body)
        return [str(point["payload"]["chunk_id"]) for point in result["result"]]
