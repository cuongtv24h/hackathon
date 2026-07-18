# === TASK:MVP-RUNTIME-01:START ===
"""Runtime composition for the grounded Information Assistance capability.

This module is the application composition root for PC-01.  It translates
environment configuration into concrete adapters while keeping provider keys
and database URLs out of API responses and logs.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

import requests

from apps.api.ai.guardrails.service import GuardrailService
from apps.api.ai.orchestrator.information_assistance.pipeline import InformationAssistancePipeline
from apps.api.ai.providers.llm_provider import RuntimeLLMAdapter, create_runtime_provider_chain
from apps.api.ai.rag.search_tool import KnowledgeSearchTool, ToolSearchRequest
from apps.api.foundation.knowledge.repository.service import KnowledgeRepositoryService


class RuntimeDependencyError(RuntimeError):
    """Raised when a required Pilot runtime dependency is unavailable."""


def _vector_literal(values: List[float]) -> str:
    if len(values) != 1024:
        raise RuntimeDependencyError("Query embedding must contain exactly 1024 values")
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def create_jina_query_embedding_provider(
    environment: Optional[Dict[str, str]] = None,
    post: Callable[..., Any] = requests.post,
) -> Callable[[str], List[float]]:
    """Create the real Jina query embedder used by vector retrieval.

    Documents are indexed with ``retrieval.passage`` in WP-008. Runtime user
    queries must use ``retrieval.query`` so both sides share Jina's retrieval
    space.  This function never returns provider response bodies to callers.
    """
    env = environment if environment is not None else os.environ
    api_key = env.get("JINA_API_KEY")
    if not api_key:
        raise RuntimeDependencyError("JINA_API_KEY is required for RAG retrieval")
    model = env.get("EMBEDDING_MODEL", "jina-embeddings-v5-text-small")
    dimensions = int(env.get("EMBEDDING_DIMENSIONS", "1024"))
    if model != "jina-embeddings-v5-text-small" or dimensions != 1024:
        raise RuntimeDependencyError("Pilot retrieval requires jina-embeddings-v5-text-small at 1024 dimensions")
    base_url = env.get("EMBEDDING_BASE_URL", "https://api.jina.ai/v1").rstrip("/")

    def embed(query: str) -> List[float]:
        if not query or not query.strip():
            raise ValueError("query must be non-empty")
        try:
            response = post(
                base_url + "/embeddings",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={
                    "model": model,
                    "input": [query],
                    "task": "retrieval.query",
                    "dimensions": dimensions,
                    "normalized": True,
                },
                timeout=8,
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeDependencyError("Jina query embedding is unavailable") from exc
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise RuntimeDependencyError("Jina returned an invalid query embedding")
        return [float(value) for value in vector]

    return embed


def _load_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeDependencyError("psycopg is required for Supabase retrieval") from exc
    return psycopg, dict_row


def create_supabase_knowledge_repository(
    database_url: str,
    embed_provider: Callable[[str], List[float]],
) -> KnowledgeRepositoryService:
    """Create the approved-only pgvector repository used by PC-01."""
    if not database_url:
        raise RuntimeDependencyError("DATABASE_URL is required for RAG retrieval")
    psycopg, dict_row = _load_psycopg()

    def search_chunks(*, embedding, domain_filter, top_k, threshold):
        vector = _vector_literal(embedding)
        filters = ""
        parameters: List[Any] = [vector]
        if domain_filter:
            filters = " AND domain.domain_code = %s"
            parameters.append(domain_filter)
        parameters.extend([threshold, top_k])
        query = """
            SELECT chunk.chunk_id::text AS chunk_id,
                   chunk.content,
                   domain.domain_code AS domain,
                   COALESCE(chunk.sub_topic, '') AS sub_topic,
                   chunk.source_id,
                   COALESCE(chunk.metadata->>'source_section', '') AS source_section,
                   COALESCE(chunk.page_numbers->>0, '') AS source_page,
                   chunk.source_version AS version,
                   chunk.is_active,
                   chunk.approval_status,
                   COALESCE(chunk.effective_date::text, '') AS effective_date,
                   chunk.tags,
                   COALESCE((chunk.metadata->>'is_mock')::boolean, false) AS is_mock,
                   true AS answerable,
                   chunk.source_path
              FROM knowledge_chunks AS chunk
              JOIN knowledge_domains AS domain ON domain.domain_id = chunk.domain_id
             WHERE chunk.is_active = true
               AND chunk.approval_status IN ('approved_for_pilot', 'approved')
               AND (chunk.effective_date IS NULL OR chunk.effective_date <= CURRENT_DATE)
               AND (1 - (chunk.embedding <=> %s::vector)) >= %s
        """ + filters + " ORDER BY chunk.embedding <=> %s::vector LIMIT %s"
        # The distance vector occurs twice; retain a clear parameter order.
        parameters = [vector, threshold] + ([domain_filter] if domain_filter else []) + [vector, top_k]
        try:
            with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    # The Pilot index has 100 lists over a modest corpus. A
                    # higher probe count prevents approximate ivfflat scans
                    # from returning an empty candidate set for valid queries.
                    cursor.execute("SET LOCAL ivfflat.probes = 20")
                    cursor.execute(query, parameters)
                    return list(cursor.fetchall())
        except Exception as exc:
            raise RuntimeDependencyError("Supabase knowledge retrieval is unavailable") from exc

    def get_chunk(chunk_id: str):
        try:
            with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT chunk.chunk_id::text AS chunk_id, chunk.content,
                               domain.domain_code AS domain, COALESCE(chunk.sub_topic, '') AS sub_topic,
                               chunk.source_id, COALESCE(chunk.metadata->>'source_section', '') AS source_section,
                               COALESCE(chunk.page_numbers->>0, '') AS source_page,
                               chunk.source_version AS version, chunk.is_active, chunk.approval_status,
                               COALESCE(chunk.effective_date::text, '') AS effective_date, chunk.tags,
                               COALESCE((chunk.metadata->>'is_mock')::boolean, false) AS is_mock,
                               true AS answerable, chunk.source_path
                          FROM knowledge_chunks AS chunk
                          JOIN knowledge_domains AS domain ON domain.domain_id = chunk.domain_id
                         WHERE chunk.chunk_id = %s::uuid
                           AND chunk.is_active = true
                           AND chunk.approval_status IN ('approved_for_pilot', 'approved')
                        """,
                        [chunk_id],
                    )
                    return cursor.fetchone()
        except Exception as exc:
            raise RuntimeDependencyError("Supabase knowledge retrieval is unavailable") from exc

    def check_conflicts(chunk_ids: List[str]) -> List[str]:
        if not chunk_ids:
            return []
        try:
            with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DISTINCT jsonb_array_elements_text(source_chunk_ids) AS chunk_id
                          FROM content_conflicts
                         WHERE state IN ('open', 'investigating')
                           AND source_chunk_ids ?| %s::text[]
                        """,
                        [chunk_ids],
                    )
                    return [row["chunk_id"] for row in cursor.fetchall()]
        except Exception as exc:
            raise RuntimeDependencyError("Supabase content-conflict check is unavailable") from exc

    return KnowledgeRepositoryService(
        embed_provider=embed_provider,
        chunk_repo=search_chunks,
        chunk_by_id_repo=get_chunk,
        conflict_check=check_conflicts,
    )


class InformationKnowledgeSearchAdapter:
    """Adapt the tool contract to the PC-01 pipeline search protocol."""

    def __init__(self, tool: KnowledgeSearchTool) -> None:
        self._tool = tool

    def search(self, query: str, *, top_k: int = 5, filters=None) -> Dict[str, Any]:
        domains = None
        if isinstance(filters, dict) and filters.get("domains"):
            domains = list(filters["domains"])
        return self._tool.search(ToolSearchRequest(query=query, domains=domains, top_k=top_k)).to_dict()


def build_information_assistance_pipeline() -> InformationAssistancePipeline:
    """Build PC-01 with real RAG, guardrails and multi-provider LLM fallback."""
    database_url = os.environ.get("DATABASE_URL")
    embed_provider = create_jina_query_embedding_provider()
    repository = create_supabase_knowledge_repository(database_url or "", embed_provider)
    try:
        search_timeout_ms = int(os.environ.get("RAG_SEARCH_TIMEOUT_MS", "8000"))
    except ValueError as exc:
        raise RuntimeDependencyError("RAG_SEARCH_TIMEOUT_MS must be a positive integer") from exc
    if search_timeout_ms <= 0:
        raise RuntimeDependencyError("RAG_SEARCH_TIMEOUT_MS must be a positive integer")
    knowledge_tool = KnowledgeSearchTool(
        repository=repository,
        timeout_ms=search_timeout_ms,
    )
    try:
        llm_provider = RuntimeLLMAdapter(create_runtime_provider_chain())
    except ValueError:
        # Retain grounded retrieval and citations if model credentials are not
        # configured. The pipeline will never invent an answer from model
        # background knowledge in this degraded state.
        llm_provider = None
    return InformationAssistancePipeline(
        knowledge_search=InformationKnowledgeSearchAdapter(knowledge_tool),
        llm_provider=llm_provider,
        guardrail_service=GuardrailService(),
    )


__all__ = [
    "RuntimeDependencyError",
    "InformationKnowledgeSearchAdapter",
    "create_jina_query_embedding_provider",
    "create_supabase_knowledge_repository",
    "build_information_assistance_pipeline",
]
# === TASK:MVP-RUNTIME-01:END ===
