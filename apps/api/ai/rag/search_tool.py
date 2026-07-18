# === TASK:WP-201:START ===
"""Knowledge search tool adapter with grounded retrieval and fallback.

Contracts implemented
---------------------
* search_knowledge_base — INT-06 tool contract
* fallback_response — INT-06 tool contract

Design notes
------------
* This module wraps the KnowledgeRepositoryService from WP-102 to provide
  the tool interface expected by the AI orchestration layer.
* The tool returns citation/provenance for each chunk.
* Insufficient/conflict conditions trigger fallback behavior.
* Retrieval filters by is_active, effective_date, and approval_status
  before returning chunks (enforced by upstream WP-102 repository).
* Provider/network calls are abstracted behind callable interfaces so tests
  can inject mocks/fakes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Import from upstream WP-102 foundation service
from apps.api.foundation.knowledge.repository.service import (
    KnowledgeChunkDTO,
    KnowledgeRepositoryService,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool-specific DTOs (INT-06)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSearchRequest:
    """Input for search_knowledge_base tool (INT-06).

    Fields
    ------
    query : str
        The user's natural-language query text.
    domains : list[str] | None
        Optional list of domain codes to restrict search.
    top_k : int
        Number of results to return (1..20, default 5).
    threshold : float
        Minimum similarity threshold (0..1, default 0.0).
    """

    query: str
    domains: Optional[List[str]] = None
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
class CitationDTO:
    """Citation with provenance for grounded responses.

    Fields follow INT-04 / data-contracts.md citation requirements.
    """

    chunk_id: str
    content: str
    domain: str
    sub_topic: str
    source_id: str
    source_section: str
    source_page: str
    version: str
    effective_date: str
    score: float = 0.0

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
            "effective_date": self.effective_date,
            "score": self.score,
        }


@dataclass(frozen=True)
class ToolSearchResult:
    """Output from search_knowledge_base tool (INT-06).

    Fields
    ------
    chunks : list of CitationDTO
        The ranked result chunks with citation metadata.
    has_results : bool
        True if any chunks were returned.
    sufficient : bool
        True if the result set is considered sufficient for a grounded answer.
    conflict : bool
        True if any of the returned chunks have known content conflicts.
    metadata : dict
        Additional metadata (e.g. elapsed_ms, total_candidates).
    """

    chunks: List[CitationDTO]
    has_results: bool = True
    sufficient: bool = True
    conflict: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "has_results": self.has_results,
            "sufficient": self.sufficient,
            "conflict": self.conflict,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FallbackRequest:
    """Input for fallback_response tool (INT-06).

    Fields
    ------
    query : str
        The original user query that triggered fallback.
    domain : str | None
        Optional domain context for the fallback.
    reason : str
        The reason for fallback (e.g. "no_results", "conflict", "insufficient").
    """

    query: str
    domain: Optional[str] = None
    reason: str = "no_results"

    def __post_init__(self) -> None:
        if not self.query or not self.query.strip():
            raise ValueError("query must be non-empty")
        if not self.reason or not self.reason.strip():
            raise ValueError("reason must be non-empty")


@dataclass(frozen=True)
class FallbackResult:
    """Output from fallback_response tool (INT-06).

    Fields
    ------
    message : str
        The fallback message to return to the user.
    channels : list[str]
        List of suggested follow-up channels (e.g. "reception", "hotline").
    metadata : dict
        Additional metadata.
    """

    message: str
    channels: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "channels": list(self.channels),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Error codes (INT-06, INT-07)
# ---------------------------------------------------------------------------

KNOWLEDGE_UNAVAILABLE = "KNOWLEDGE_UNAVAILABLE"
NO_GROUNDED_RESULT = "NO_GROUNDED_RESULT"
CONTENT_CONFLICT = "CONTENT_CONFLICT"
CONFIG_UNAVAILABLE = "CONFIG_UNAVAILABLE"


class KnowledgeSearchError(Exception):
    """Base exception for knowledge search tool errors."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class KnowledgeUnavailableError(KnowledgeSearchError):
    """Raised when the knowledge repository is unavailable."""

    def __init__(self, message: str = "Knowledge repository unavailable") -> None:
        super().__init__(KNOWLEDGE_UNAVAILABLE, message, retryable=True)


class NoGroundedResultError(KnowledgeSearchError):
    """Raised when no grounded results are found."""

    def __init__(self, message: str = "No grounded results found") -> None:
        super().__init__(NO_GROUNDED_RESULT, message, retryable=False)


class ContentConflictError(KnowledgeSearchError):
    """Raised when content conflicts are detected."""

    def __init__(self, message: str = "Content conflict detected") -> None:
        super().__init__(CONTENT_CONFLICT, message, retryable=False)


class ConfigUnavailableError(KnowledgeSearchError):
    """Raised when configuration is unavailable for fallback."""

    def __init__(self, message: str = "Configuration unavailable") -> None:
        super().__init__(CONFIG_UNAVAILABLE, message, retryable=True)


class ToolTimeoutError(KnowledgeUnavailableError):
    """Raised when a synchronous dependency exceeds its tool SLA."""


# ---------------------------------------------------------------------------
# Abstract interfaces for testability
# ---------------------------------------------------------------------------

FallbackTemplateProvider = Callable[[str, Optional[str]], str]
"""Signature: ``get_template(reason: str, domain: str | None) -> str``.

Returns the fallback message template for the given reason and domain.
"""

ChannelResolver = Callable[[Optional[str]], List[str]]
"""Signature: ``resolve_channels(domain: str | None) -> list[str]``.

Returns the list of follow-up channels for the given domain.
"""


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class KnowledgeSearchTool:
    """Tool adapter for knowledge search with fallback support.

    This class wraps the KnowledgeRepositoryService to provide the tool
    interface expected by the AI orchestration layer (INT-06). It handles:

    * Converting tool requests to repository requests
    * Mapping results to citation format
    * Detecting insufficient/conflict conditions
    * Providing fallback responses when needed

    The tool enforces the INT-06 contract:
    * Timeout: 800ms for search
    * Retry: 1 transient retry
    * Errors: KNOWLEDGE_UNAVAILABLE, NO_GROUNDED_RESULT, CONTENT_CONFLICT
    """

    # Default fallback templates
    DEFAULT_FALLBACK_TEMPLATES: Dict[str, str] = {
        "no_results": (
            "Xin lỗi, tôi không tìm thấy thông tin phù hợp với câu hỏi của bạn. "
            "Vui lòng liên hệ reception để được hỗ trợ thêm."
        ),
        "insufficient": (
            "Thông tin tôi tìm được chưa đủ để trả lời chính xác câu hỏi của bạn. "
            "Vui lòng liên hệ reception để được hỗ trợ thêm."
        ),
        "conflict": (
            "Tôi phát hiện thông tin mâu thuẫn về chủ đề này. "
            "Vui lòng liên hệ reception để được xác nhận."
        ),
        "default": (
            "Tôi không thể trả lời câu hỏi này ngay bây giờ. "
            "Vui lòng liên hệ reception để được hỗ trợ."
        ),
    }

    # Default channels for fallback
    DEFAULT_CHANNELS: List[str] = ["reception", "hotline"]
    SEARCH_RETRIES = 1
    FALLBACK_RETRIES = 1
    FALLBACK_TIMEOUT_MS = 100

    def __init__(
        self,
        *,
        repository: KnowledgeRepositoryService,
        fallback_template_provider: Optional[FallbackTemplateProvider] = None,
        channel_resolver: Optional[ChannelResolver] = None,
        timeout_ms: int = 800,
    ) -> None:
        """Initialize the knowledge search tool.

        Parameters
        ----------
        repository : KnowledgeRepositoryService
            The upstream knowledge repository service from WP-102.
        fallback_template_provider : callable, optional
            Custom provider for fallback message templates.
        channel_resolver : callable, optional
            Custom resolver for follow-up channels.
        timeout_ms : int
            Timeout in milliseconds (default 800ms per INT-06).
        """
        self._repository = repository
        self._fallback_template_provider = fallback_template_provider
        self._channel_resolver = channel_resolver
        self._timeout_ms = timeout_ms
        self._fallback_cache: Dict[tuple[str, Optional[str]], FallbackResult] = {}

    def _run_with_policy(
        self,
        operation: Callable[[], Any],
        *,
        timeout_ms: int,
        retries: int,
        operation_name: str,
    ) -> tuple[Any, int]:
        """Run a dependency with bounded retry and elapsed-time enforcement."""
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                value = operation()
                if (time.monotonic() - started) * 1000 > timeout_ms:
                    raise ToolTimeoutError(
                        f"{operation_name} exceeded {timeout_ms}ms"
                    )
                return value, attempt + 1
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    raise
        raise last_error or RuntimeError(f"{operation_name} failed")

    # ------------------------------------------------------------------
    # search_knowledge_base tool (INT-06)
    # ------------------------------------------------------------------

    def search(self, request: ToolSearchRequest) -> ToolSearchResult:
        """Execute the search_knowledge_base tool.

        Steps
        -----
        1. Validate the request.
        2. Convert to KnowledgeSearchRequest for the repository.
        3. Execute the search via the repository service.
        4. Map results to CitationDTO with scores.
        5. Determine sufficient/conflict flags.
        6. Return the tool result.

        Raises
        ------
        KnowledgeUnavailableError
            If the repository is unavailable.
        """
        start_time = time.monotonic()

        try:
            # Step 1-2 — validate and convert request
            domain_filter = request.domains[0] if request.domains else None
            repo_request = KnowledgeSearchRequest(
                query=request.query,
                domain_filter=domain_filter,
                top_k=request.top_k,
                threshold=request.threshold,
            )

            # Step 3 — execute search via repository
            response, attempts = self._run_with_policy(
                lambda: self._repository.search(repo_request),
                timeout_ms=self._timeout_ms,
                retries=self.SEARCH_RETRIES,
                operation_name="knowledge search",
            )

            # Step 4 — map to CitationDTO with scores
            citations = [
                self._chunk_to_citation(chunk, idx)
                for idx, chunk in enumerate(response.chunks)
            ]

            # Step 5 — determine flags
            has_results = len(citations) > 0
            sufficient = response.result_sufficient and has_results
            conflict = response.conflict_flag

            elapsed_ms = (time.monotonic() - start_time) * 1000

            # Step 6 — build result
            return ToolSearchResult(
                chunks=citations,
                has_results=has_results,
                sufficient=sufficient,
                conflict=conflict,
                metadata={
                    "elapsed_ms": elapsed_ms,
                    "attempts": attempts,
                    "result_count": len(citations),
                    **response.metadata,
                },
            )

        except KnowledgeSearchError:
            raise
        except Exception as e:
            logger.exception("Knowledge search failed")
            raise KnowledgeUnavailableError(str(e)) from e

    # ------------------------------------------------------------------
    # fallback_response tool (INT-06)
    # ------------------------------------------------------------------

    def fallback(self, request: FallbackRequest) -> FallbackResult:
        """Execute the fallback_response tool.

        Steps
        -----
        1. Get the fallback message template.
        2. Resolve follow-up channels.
        3. Return the fallback result.

        Raises
        ------
        ConfigUnavailableError
            If the fallback configuration is unavailable.
        """
        try:
            cache_key = (request.reason, request.domain)
            cached = self._fallback_cache.get(cache_key)
            if cached is not None:
                return cached

            # Step 1 — get fallback template
            if self._fallback_template_provider:
                message, _ = self._run_with_policy(
                    lambda: self._fallback_template_provider(
                        request.reason, request.domain
                    ),
                    timeout_ms=self.FALLBACK_TIMEOUT_MS,
                    retries=self.FALLBACK_RETRIES,
                    operation_name="fallback template lookup",
                )
            else:
                message = self.DEFAULT_FALLBACK_TEMPLATES.get(
                    request.reason, self.DEFAULT_FALLBACK_TEMPLATES["default"]
                )

            # Step 2 — resolve channels
            if self._channel_resolver:
                channels, _ = self._run_with_policy(
                    lambda: self._channel_resolver(request.domain),
                    timeout_ms=self.FALLBACK_TIMEOUT_MS,
                    retries=self.FALLBACK_RETRIES,
                    operation_name="fallback channel lookup",
                )
            else:
                channels = list(self.DEFAULT_CHANNELS)

            # Step 3 — build result
            result = FallbackResult(
                message=message,
                channels=channels,
                metadata={"reason": request.reason, "domain": request.domain},
            )
            self._fallback_cache[cache_key] = result
            return result

        except ConfigUnavailableError:
            raise
        except Exception as e:
            logger.exception("Fallback response failed")
            raise ConfigUnavailableError(str(e)) from e

    # ------------------------------------------------------------------
    # Convenience method: search with auto-fallback
    # ------------------------------------------------------------------

    def search_with_fallback(
        self, request: ToolSearchRequest
    ) -> ToolSearchResult | FallbackResult:
        """Execute search with automatic fallback on insufficient/conflict.

        This method combines search and fallback in a single call,
        returning either a successful search result or a fallback response.

        The method triggers fallback when:
        * No results are found (has_results=False)
        * Results are insufficient (sufficient=False)
        * Content conflicts are detected (conflict=True)
        """
        result = self.search(request)

        # Determine if fallback is needed
        needs_fallback = (
            not result.has_results
            or not result.sufficient
            or result.conflict
        )

        if not needs_fallback:
            return result

        # Determine fallback reason
        if not result.has_results:
            reason = "no_results"
        elif result.conflict:
            reason = "conflict"
        else:
            reason = "insufficient"

        domain = request.domains[0] if request.domains else None

        return self.fallback(FallbackRequest(
            query=request.query,
            domain=domain,
            reason=reason,
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chunk_to_citation(
        self, chunk: KnowledgeChunkDTO, rank: int
    ) -> CitationDTO:
        """Map a KnowledgeChunkDTO to a CitationDTO.

        The citation includes provenance metadata required for grounded
        responses per INT-04. The score is derived from the rank position
        (higher rank = lower score).
        """
        # Derive score from rank (inverse relationship)
        # Rank 0 gets score 1.0, subsequent ranks get decreasing scores
        score = max(0.0, 1.0 - (rank * 0.1))

        return CitationDTO(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            domain=chunk.domain,
            sub_topic=chunk.sub_topic,
            source_id=chunk.source_id,
            source_section=chunk.source_section,
            source_page=chunk.source_page,
            version=chunk.version,
            effective_date=chunk.effective_date,
            score=score,
        )


__all__ = [
    # DTOs
    "ToolSearchRequest",
    "CitationDTO",
    "ToolSearchResult",
    "FallbackRequest",
    "FallbackResult",
    # Errors
    "KnowledgeSearchError",
    "KnowledgeUnavailableError",
    "NoGroundedResultError",
    "ContentConflictError",
    "ConfigUnavailableError",
    # Error codes
    "KNOWLEDGE_UNAVAILABLE",
    "NO_GROUNDED_RESULT",
    "CONTENT_CONFLICT",
    "CONFIG_UNAVAILABLE",
    # Interfaces
    "FallbackTemplateProvider",
    "ChannelResolver",
    # Tool
    "KnowledgeSearchTool",
]
# === TASK:WP-201:END ===
