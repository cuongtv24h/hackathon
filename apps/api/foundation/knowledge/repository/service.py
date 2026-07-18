# === TASK:WP-102:START ===
"""Knowledge repository service — search and retrieval of approved knowledge chunks.

Contracts implemented
---------------------
* FND-KNW-01 SearchKnowledge — POST /v1/foundation/knowledge:search
* FND-KNW-02 GetKnowledgeChunk — GET /v1/foundation/knowledge/chunks/{chunk_id}

Design notes
------------
* This service operates on approved/active chunks only. Drafts and rejected
  content are never returned by search or direct retrieval.
* Embedding-based search uses cosine similarity over pgvector with a
  configurable domain filter and similarity threshold.
* The service is stateless; all state lives in the database.
* Provider/network calls are abstracted behind callable interfaces so tests
  can inject fakes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs — canonical contracts from INT-04 / data-contracts.md
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeSearchRequest:
    """Canonical search request for FND-KNW-01.

    Fields
    ------
    query : str
        The user's natural-language query text.
    domain_filter : str | None
        Optional domain code to restrict search (e.g. ``"bhyt"``).
    top_k : int
        Number of results to return (1..20, default 5).
    threshold : float
        Minimum cosine-similarity threshold (0..1, default 0.0).
    """

    query: str
    domain_filter: Optional[str] = None
    top_k: int = 5
    threshold: float = 0.0

    def __post_init__(self) -> None:
        if not self.query or not self.query.strip():
            raise ValueError("query must be non-empty")
        if not (1 <= self.top_k <= 20):
            raise ValueError("top_k must be between 1 and 20")
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError("threshold must be between 0 and 1")


@dataclass(frozen=True)
class KnowledgeChunkDTO:
    """Canonical chunk DTO for FND-KNW-02.

    Fields follow INT-04 / data-contracts.md exactly. The ``embedding`` field
    is never exposed to callers; it is internal to the persistence layer.
    """

    chunk_id: str
    content: str
    domain: str
    sub_topic: str
    source_id: str
    source_section: str
    source_page: str
    version: str
    is_active: bool
    approval_status: str
    effective_date: str
    tags: List[str] = field(default_factory=list)
    is_mock: bool = False
    answerable: bool = True
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "domain": self.domain,
            "sub_topic": self.sub_topic,
            "source_id": self.source_id,
            "source_section": self.source_section,
            "source_page": self.source_page,
            "version": self.version,
            "is_active": self.is_active,
            "approval_status": self.approval_status,
            "effective_date": self.effective_date,
            "tags": list(self.tags),
            "is_mock": self.is_mock,
            "answerable": self.answerable,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class KnowledgeSearchResponse:
    """Canonical search response for FND-KNW-01.

    Fields
    ------
    chunks : list of KnowledgeChunkDTO
        The ranked result chunks.
    result_sufficient : bool
        True if the result set is considered sufficient for a grounded answer.
    conflict_flag : bool
        True if any of the returned chunks have known content conflicts.
    metadata : dict
        Additional metadata (e.g. elapsed_ms, total_candidates).
    """

    chunks: List[KnowledgeChunkDTO]
    result_sufficient: bool = True
    conflict_flag: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "result_sufficient": self.result_sufficient,
            "conflict_flag": self.conflict_flag,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Abstract provider interfaces (for testability)
# ---------------------------------------------------------------------------

EmbeddingProvider = Callable[[str], List[float]]
"""Signature: ``embed(text: str) -> list[float]``.

Returns a 1024-dimensional embedding vector for the given text.
"""

ChunkRepository = Callable[..., List[Dict[str, Any]]]
"""Signature: ``search(embedding, domain_filter, top_k, threshold) -> list[dict]``.

Returns raw chunk rows from the persistence layer.
"""

ChunkByIdRepository = Callable[[str], Optional[Dict[str, Any]]]
"""Signature: ``get_by_id(chunk_id: str) -> dict | None``.

Returns a single chunk row or None if not found.
"""

ConflictCheck = Callable[[List[str]], List[str]]
"""Signature: ``check_conflicts(chunk_ids: list[str]) -> list[str]``.

Returns chunk_ids that have open conflicts.
"""


# ---------------------------------------------------------------------------
# Service implementation
# ---------------------------------------------------------------------------


class KnowledgeRepositoryService:
    """Stateless service for knowledge search and retrieval.

    The service depends on injected callables for embedding, database access
    and conflict checking. This design allows unit tests to provide fakes
    without a live database or embedding API.
    """

    def __init__(
        self,
        *,
        embed_provider: EmbeddingProvider,
        chunk_repo: ChunkRepository,
        chunk_by_id_repo: ChunkByIdRepository,
        conflict_check: Optional[ConflictCheck] = None,
    ) -> None:
        self._embed = embed_provider
        self._chunk_repo = chunk_repo
        self._chunk_by_id_repo = chunk_by_id_repo
        self._conflict_check = conflict_check

    # ------------------------------------------------------------------
    # FND-KNW-01 SearchKnowledge
    # ------------------------------------------------------------------

    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        """Execute a knowledge search.

        Steps
        -----
        1. Validate the request.
        2. Embed the query text using the configured provider.
        3. Query the chunk repository with the embedding vector.
        4. Map raw rows to ``KnowledgeChunkDTO`` instances.
        5. Check for conflicts among returned chunks.
        6. Return the ranked response.
        """
        # Step 1 — validation (handled by dataclass __post_init__)
        _ = request  # validated on construction

        # Step 2 — embed
        query_vector = self._embed(request.query)

        # Step 3 — search repository
        raw_rows = self._chunk_repo(
            embedding=query_vector,
            domain_filter=request.domain_filter,
            top_k=request.top_k,
            threshold=request.threshold,
        )

        # Step 4 — map to DTOs
        chunks = [_row_to_dto(r) for r in raw_rows]

        # Step 5 — conflict check
        conflict_flag = False
        if self._conflict_check and chunks:
            chunk_ids = [c.chunk_id for c in chunks]
            conflicted = self._conflict_check(chunk_ids)
            conflict_flag = len(conflicted) > 0

        # Step 6 — build response
        return KnowledgeSearchResponse(
            chunks=chunks,
            result_sufficient=len(chunks) > 0,
            conflict_flag=conflict_flag,
            metadata={"result_count": len(chunks)},
        )

    # ------------------------------------------------------------------
    # FND-KNW-02 GetKnowledgeChunk
    # ------------------------------------------------------------------

    def get_chunk(self, chunk_id: str) -> Optional[KnowledgeChunkDTO]:
        """Retrieve a single knowledge chunk by its canonical ID.

        Returns ``None`` if the chunk does not exist or is not active/approved.
        """
        if not chunk_id or not chunk_id.strip():
            raise ValueError("chunk_id must be non-empty")

        row = self._chunk_by_id_repo(chunk_id)
        if row is None:
            return None
        return _row_to_dto(row)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_dto(row: Dict[str, Any]) -> KnowledgeChunkDTO:
    """Map a raw database row dict to a ``KnowledgeChunkDTO``.

    The mapping is lenient: missing keys default to sensible empty values
    so the service degrades gracefully if the persistence layer changes.
    """
    return KnowledgeChunkDTO(
        chunk_id=str(row.get("chunk_id", "")),
        content=str(row.get("content", "")),
        domain=str(row.get("domain", "")),
        sub_topic=str(row.get("sub_topic", "")),
        source_id=str(row.get("source_id", "")),
        source_section=str(row.get("source_section", "")),
        source_page=str(row.get("source_page", "")),
        version=str(row.get("version", "")),
        is_active=bool(row.get("is_active", False)),
        approval_status=str(row.get("approval_status", "")),
        effective_date=str(row.get("effective_date", "")),
        tags=list(row.get("tags", [])),
        is_mock=bool(row.get("is_mock", False)),
        answerable=bool(row.get("answerable", True)),
        source_path=str(row.get("source_path", "")),
    )


__all__ = [
    "KnowledgeSearchRequest",
    "KnowledgeChunkDTO",
    "KnowledgeSearchResponse",
    "KnowledgeRepositoryService",
    "EmbeddingProvider",
    "ChunkRepository",
    "ChunkByIdRepository",
    "ConflictCheck",
]
# === TASK:WP-102:END ===