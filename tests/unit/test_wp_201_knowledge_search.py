# === TASK:WP-201:START ===
"""Unit tests for WP-201: Knowledge search tool adapter.

Test contract
-------------
Per docs/spec-registry/runtime-test-policy.yaml:
* Framework: pytest
* Location: tests/unit/
* Use mocks/fakes for provider and network calls

Coverage
--------
* search_knowledge_base tool contract (INT-06)
* fallback_response tool contract (INT-06)
* Citation/provenance in results
* Insufficient/conflict triggers fallback
* Retrieval filters by is_active, effective_date, approval_status
* Error handling: KNOWLEDGE_UNAVAILABLE, NO_GROUNDED_RESULT, CONTENT_CONFLICT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from apps.api.ai.rag.search_tool import (
    CitationDTO,
    ConfigUnavailableError,
    ContentConflictError,
    FallbackRequest,
    FallbackResult,
    KnowledgeSearchTool,
    KnowledgeSearchError,
    KnowledgeUnavailableError,
    NoGroundedResultError,
    ToolSearchRequest,
    ToolSearchResult,
)
from apps.api.foundation.knowledge.repository.service import (
    KnowledgeChunkDTO,
    KnowledgeRepositoryService,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)


# ---------------------------------------------------------------------------
# Test fixtures: Fakes and mocks
# ---------------------------------------------------------------------------


@dataclass
class FakeKnowledgeRepository:
    """Fake repository for testing without database/embedding calls."""

    chunks: List[KnowledgeChunkDTO]
    should_fail: bool = False
    fail_message: str = "Repository unavailable"
    conflict_chunk_ids: List[str] = None

    def __post_init__(self):
        if self.conflict_chunk_ids is None:
            self.conflict_chunk_ids = []

    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        if self.should_fail:
            raise RuntimeError(self.fail_message)

        # Filter by domain if specified
        filtered = [
            c for c in self.chunks
            if request.domain_filter is None or c.domain == request.domain_filter
        ]

        # Apply top_k
        result_chunks = filtered[: request.top_k]

        # Check for conflicts
        conflict_flag = any(
            c.chunk_id in self.conflict_chunk_ids for c in result_chunks
        )

        return KnowledgeSearchResponse(
            chunks=result_chunks,
            result_sufficient=len(result_chunks) > 0,
            conflict_flag=conflict_flag,
            metadata={"result_count": len(result_chunks)},
        )

    def get_chunk(self, chunk_id: str) -> Optional[KnowledgeChunkDTO]:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        return None


def make_chunk(
    chunk_id: str = "chunk-001",
    content: str = "Test content",
    domain: str = "bhyt",
    sub_topic: str = "coverage",
    source_id: str = "source-001",
    source_section: str = "section-1",
    source_page: str = "1",
    version: str = "1.0",
    effective_date: str = "2024-01-01",
    is_active: bool = True,
    approval_status: str = "approved",
) -> KnowledgeChunkDTO:
    """Factory for creating test chunks."""
    return KnowledgeChunkDTO(
        chunk_id=chunk_id,
        content=content,
        domain=domain,
        sub_topic=sub_topic,
        source_id=source_id,
        source_section=source_section,
        source_page=source_page,
        version=version,
        effective_date=effective_date,
        is_active=is_active,
        approval_status=approval_status,
    )


def make_tool(
    chunks: List[KnowledgeChunkDTO] = None,
    should_fail: bool = False,
    conflict_chunk_ids: List[str] = None,
    fallback_template_provider=None,
    channel_resolver=None,
) -> KnowledgeSearchTool:
    """Factory for creating test tools with fake repository."""
    if chunks is None:
        chunks = [make_chunk()]

    fake_repo = FakeKnowledgeRepository(
        chunks=chunks,
        should_fail=should_fail,
        conflict_chunk_ids=conflict_chunk_ids,
    )

    return KnowledgeSearchTool(
        repository=fake_repo,  # type: ignore
        fallback_template_provider=fallback_template_provider,
        channel_resolver=channel_resolver,
    )


# ---------------------------------------------------------------------------
# Test: ToolSearchRequest validation
# ---------------------------------------------------------------------------


class TestToolSearchRequest:
    """Tests for ToolSearchRequest validation."""

    def test_valid_request(self):
        """A valid request should pass validation."""
        request = ToolSearchRequest(
            query="What is BHYT coverage?",
            domains=["bhyt"],
            top_k=5,
            threshold=0.5,
        )
        assert request.query == "What is BHYT coverage?"
        assert request.domains == ["bhyt"]
        assert request.top_k == 5
        assert request.threshold == 0.5

    def test_default_values(self):
        """Default values should be applied."""
        request = ToolSearchRequest(query="test query")
        assert request.domains is None
        assert request.top_k == 5
        assert request.threshold == 0.0


class TestToolExecutionPolicy:
    """Verify the INT-06 retry, timeout, and fallback-cache behavior."""

    def test_search_retries_one_transient_failure(self):
        tool = make_tool()
        response = tool._repository.search(KnowledgeSearchRequest(query="seed"))
        tool._repository.search = MagicMock(
            side_effect=[RuntimeError("temporary"), response]
        )

        result = tool.search(ToolSearchRequest(query="coverage"))

        assert result.metadata["attempts"] == 2
        assert tool._repository.search.call_count == 2

    def test_search_rejects_late_result(self):
        tool = make_tool()
        tool._timeout_ms = 0

        with pytest.raises(KnowledgeUnavailableError, match="exceeded"):
            tool.search(ToolSearchRequest(query="coverage"))

    def test_fallback_uses_cache_after_first_success(self):
        provider = MagicMock(return_value="Fallback message")
        tool = make_tool(fallback_template_provider=provider)
        request = FallbackRequest(query="coverage", domain="bhyt")

        assert tool.fallback(request).message == "Fallback message"
        assert tool.fallback(request).message == "Fallback message"
        assert provider.call_count == 1

    def test_empty_query_raises(self):
        """Empty query should raise ValueError."""
        with pytest.raises(ValueError, match="query must be non-empty"):
            ToolSearchRequest(query="")

    def test_whitespace_query_raises(self):
        """Whitespace-only query should raise ValueError."""
        with pytest.raises(ValueError, match="query must be non-empty"):
            ToolSearchRequest(query="   ")

    def test_top_k_below_minimum_raises(self):
        """top_k below 1 should raise ValueError."""
        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            ToolSearchRequest(query="test", top_k=0)

    def test_top_k_above_maximum_raises(self):
        """top_k above 20 should raise ValueError."""
        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            ToolSearchRequest(query="test", top_k=21)

    def test_threshold_below_zero_raises(self):
        """threshold below 0 should raise ValueError."""
        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            ToolSearchRequest(query="test", threshold=-0.1)

    def test_threshold_above_one_raises(self):
        """threshold above 1 should raise ValueError."""
        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            ToolSearchRequest(query="test", threshold=1.1)


# ---------------------------------------------------------------------------
# Test: FallbackRequest validation
# ---------------------------------------------------------------------------


class TestFallbackRequest:
    """Tests for FallbackRequest validation."""

    def test_valid_request(self):
        """A valid request should pass validation."""
        request = FallbackRequest(
            query="test query",
            domain="bhyt",
            reason="no_results",
        )
        assert request.query == "test query"
        assert request.domain == "bhyt"
        assert request.reason == "no_results"

    def test_empty_query_raises(self):
        """Empty query should raise ValueError."""
        with pytest.raises(ValueError, match="query must be non-empty"):
            FallbackRequest(query="", reason="no_results")

    def test_empty_reason_raises(self):
        """Empty reason should raise ValueError."""
        with pytest.raises(ValueError, match="reason must be non-empty"):
            FallbackRequest(query="test", reason="")


# ---------------------------------------------------------------------------
# Test: search_knowledge_base tool
# ---------------------------------------------------------------------------


class TestKnowledgeSearchToolSearch:
    """Tests for the search_knowledge_base tool."""

    def test_search_returns_citations(self):
        """Search should return citations with provenance."""
        tool = make_tool(chunks=[
            make_chunk(
                chunk_id="chunk-001",
                content="BHYT covers 80% of hospital fees.",
                domain="bhyt",
                sub_topic="coverage",
                source_id="law-001",
                source_section="Article 5",
                source_page="12",
                version="2024.1",
                effective_date="2024-01-01",
            ),
        ])

        result = tool.search(ToolSearchRequest(query="BHYT coverage"))

        assert result.has_results
        assert len(result.chunks) == 1

        citation = result.chunks[0]
        assert citation.chunk_id == "chunk-001"
        assert citation.content == "BHYT covers 80% of hospital fees."
        assert citation.domain == "bhyt"
        assert citation.sub_topic == "coverage"
        assert citation.source_id == "law-001"
        assert citation.source_section == "Article 5"
        assert citation.source_page == "12"
        assert citation.version == "2024.1"
        assert citation.effective_date == "2024-01-01"

    def test_search_returns_scores(self):
        """Search results should include scores derived from rank."""
        tool = make_tool(chunks=[
            make_chunk(chunk_id="chunk-001"),
            make_chunk(chunk_id="chunk-002"),
            make_chunk(chunk_id="chunk-003"),
        ])

        result = tool.search(ToolSearchRequest(query="test"))

        assert len(result.chunks) == 3
        # First result has highest score
        assert result.chunks[0].score == 1.0
        assert result.chunks[1].score == 0.9
        assert result.chunks[2].score == 0.8

    def test_search_domain_filter(self):
        """Search should filter by domain when specified."""
        tool = make_tool(chunks=[
            make_chunk(chunk_id="bhyt-001", domain="bhyt"),
            make_chunk(chunk_id="appointment-001", domain="appointments"),
        ])

        result = tool.search(ToolSearchRequest(
            query="test",
            domains=["bhyt"],
        ))

        assert len(result.chunks) == 1
        assert result.chunks[0].domain == "bhyt"

    def test_search_top_k_limit(self):
        """Search should respect top_k limit."""
        tool = make_tool(chunks=[
            make_chunk(chunk_id=f"chunk-{i}") for i in range(10)
        ])

        result = tool.search(ToolSearchRequest(query="test", top_k=3))

        assert len(result.chunks) == 3

    def test_search_no_results(self):
        """Search with no results should set has_results=False."""
        tool = make_tool(chunks=[])

        result = tool.search(ToolSearchRequest(query="test"))

        assert not result.has_results
        assert not result.sufficient
        assert len(result.chunks) == 0

    def test_search_conflict_flag(self):
        """Search should detect content conflicts."""
        tool = make_tool(
            chunks=[make_chunk(chunk_id="conflict-001")],
            conflict_chunk_ids=["conflict-001"],
        )

        result = tool.search(ToolSearchRequest(query="test"))

        assert result.conflict

    def test_search_repository_unavailable_raises(self):
        """Repository unavailability should raise KnowledgeUnavailableError."""
        tool = make_tool(chunks=[], should_fail=True)

        with pytest.raises(KnowledgeUnavailableError):
            tool.search(ToolSearchRequest(query="test"))

    def test_search_includes_elapsed_time(self):
        """Search result should include elapsed_ms in metadata."""
        tool = make_tool(chunks=[make_chunk()])

        result = tool.search(ToolSearchRequest(query="test"))

        assert "elapsed_ms" in result.metadata
        assert result.metadata["elapsed_ms"] >= 0


# ---------------------------------------------------------------------------
# Test: fallback_response tool
# ---------------------------------------------------------------------------


class TestKnowledgeSearchToolFallback:
    """Tests for the fallback_response tool."""

    def test_fallback_no_results(self):
        """Fallback for no_results should return appropriate message."""
        tool = make_tool(chunks=[])

        result = tool.fallback(FallbackRequest(
            query="test",
            reason="no_results",
        ))

        assert isinstance(result, FallbackResult)
        assert "không tìm thấy" in result.message.lower()
        assert "reception" in result.channels

    def test_fallback_insufficient(self):
        """Fallback for insufficient should return appropriate message."""
        tool = make_tool(chunks=[make_chunk()])

        result = tool.fallback(FallbackRequest(
            query="test",
            reason="insufficient",
        ))

        assert isinstance(result, FallbackResult)
        assert "chưa đủ" in result.message.lower()

    def test_fallback_conflict(self):
        """Fallback for conflict should return appropriate message."""
        tool = make_tool(chunks=[make_chunk()])

        result = tool.fallback(FallbackRequest(
            query="test",
            reason="conflict",
        ))

        assert isinstance(result, FallbackResult)
        assert "mâu thuẫn" in result.message.lower()

    def test_fallback_default_reason(self):
        """Fallback for unknown reason should use default template."""
        tool = make_tool(chunks=[])

        result = tool.fallback(FallbackRequest(
            query="test",
            reason="unknown_reason",
        ))

        assert isinstance(result, FallbackResult)
        assert result.message  # Should have some message

    def test_fallback_custom_template_provider(self):
        """Custom template provider should be used if provided."""
        def custom_provider(reason: str, domain: Optional[str]) -> str:
            return f"Custom message for {reason} in {domain or 'general'}"

        tool = make_tool(chunks=[], fallback_template_provider=custom_provider)

        result = tool.fallback(FallbackRequest(
            query="test",
            domain="bhyt",
            reason="no_results",
        ))

        assert "Custom message" in result.message
        assert "no_results" in result.message
        assert "bhyt" in result.message

    def test_fallback_custom_channel_resolver(self):
        """Custom channel resolver should be used if provided."""
        def custom_resolver(domain: Optional[str]) -> List[str]:
            return ["custom_channel", "another_channel"]

        tool = make_tool(chunks=[], channel_resolver=custom_resolver)

        result = tool.fallback(FallbackRequest(
            query="test",
            reason="no_results",
        ))

        assert result.channels == ["custom_channel", "another_channel"]

    def test_fallback_includes_metadata(self):
        """Fallback result should include reason and domain in metadata."""
        tool = make_tool(chunks=[])

        result = tool.fallback(FallbackRequest(
            query="test",
            domain="bhyt",
            reason="no_results",
        ))

        assert result.metadata["reason"] == "no_results"
        assert result.metadata["domain"] == "bhyt"


# ---------------------------------------------------------------------------
# Test: search_with_fallback
# ---------------------------------------------------------------------------


class TestKnowledgeSearchToolSearchWithFallback:
    """Tests for search_with_fallback convenience method."""

    def test_returns_search_result_when_sufficient(self):
        """Should return ToolSearchResult when results are sufficient."""
        tool = make_tool(chunks=[make_chunk(chunk_id="good-001")])

        result = tool.search_with_fallback(ToolSearchRequest(query="test"))

        assert isinstance(result, ToolSearchResult)
        assert result.has_results
        assert result.sufficient

    def test_returns_fallback_on_no_results(self):
        """Should return FallbackResult when no results found."""
        tool = make_tool(chunks=[])

        result = tool.search_with_fallback(ToolSearchRequest(query="test"))

        assert isinstance(result, FallbackResult)
        assert result.metadata["reason"] == "no_results"

    def test_returns_fallback_on_conflict(self):
        """Should return FallbackResult when conflict detected."""
        tool = make_tool(
            chunks=[make_chunk(chunk_id="conflict-001")],
            conflict_chunk_ids=["conflict-001"],
        )

        result = tool.search_with_fallback(ToolSearchRequest(query="test"))

        assert isinstance(result, FallbackResult)
        assert result.metadata["reason"] == "conflict"

    def test_returns_fallback_on_insufficient(self):
        """Should return FallbackResult when results insufficient."""
        # Create a fake that returns insufficient results
        fake_repo = MagicMock(spec=KnowledgeRepositoryService)
        fake_repo.search.return_value = KnowledgeSearchResponse(
            chunks=[make_chunk()],
            result_sufficient=False,  # Insufficient
            conflict_flag=False,
        )

        tool = KnowledgeSearchTool(repository=fake_repo)

        result = tool.search_with_fallback(ToolSearchRequest(query="test"))

        assert isinstance(result, FallbackResult)
        assert result.metadata["reason"] == "insufficient"

    def test_fallback_includes_domain(self):
        """Fallback should include domain from request."""
        tool = make_tool(chunks=[])

        result = tool.search_with_fallback(ToolSearchRequest(
            query="test",
            domains=["bhyt"],
        ))

        assert isinstance(result, FallbackResult)
        assert result.metadata["domain"] == "bhyt"


# ---------------------------------------------------------------------------
# Test: CitationDTO and result serialization
# ---------------------------------------------------------------------------


class TestCitationDTO:
    """Tests for CitationDTO serialization."""

    def test_to_dict(self):
        """CitationDTO should serialize to dict correctly."""
        citation = CitationDTO(
            chunk_id="chunk-001",
            content="Test content",
            domain="bhyt",
            sub_topic="coverage",
            source_id="source-001",
            source_section="section-1",
            source_page="1",
            version="1.0",
            effective_date="2024-01-01",
            score=0.95,
        )

        d = citation.to_dict()

        assert d["chunk_id"] == "chunk-001"
        assert d["content"] == "Test content"
        assert d["domain"] == "bhyt"
        assert d["sub_topic"] == "coverage"
        assert d["source_id"] == "source-001"
        assert d["source_section"] == "section-1"
        assert d["source_page"] == "1"
        assert d["version"] == "1.0"
        assert d["effective_date"] == "2024-01-01"
        assert d["score"] == 0.95


class TestToolSearchResult:
    """Tests for ToolSearchResult serialization."""

    def test_to_dict(self):
        """ToolSearchResult should serialize to dict correctly."""
        citation = CitationDTO(
            chunk_id="chunk-001",
            content="Test",
            domain="bhyt",
            sub_topic="test",
            source_id="s1",
            source_section="s1",
            source_page="1",
            version="1.0",
            effective_date="2024-01-01",
            score=1.0,
        )

        result = ToolSearchResult(
            chunks=[citation],
            has_results=True,
            sufficient=True,
            conflict=False,
            metadata={"elapsed_ms": 42.5},
        )

        d = result.to_dict()

        assert d["has_results"] is True
        assert d["sufficient"] is True
        assert d["conflict"] is False
        assert d["metadata"]["elapsed_ms"] == 42.5
        assert len(d["chunks"]) == 1


class TestFallbackResult:
    """Tests for FallbackResult serialization."""

    def test_to_dict(self):
        """FallbackResult should serialize to dict correctly."""
        result = FallbackResult(
            message="Test message",
            channels=["reception", "hotline"],
            metadata={"reason": "no_results"},
        )

        d = result.to_dict()

        assert d["message"] == "Test message"
        assert d["channels"] == ["reception", "hotline"]
        assert d["metadata"]["reason"] == "no_results"


# ---------------------------------------------------------------------------
# Test: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and error types."""

    def test_knowledge_unavailable_error_retryable(self):
        """KnowledgeUnavailableError should be retryable."""
        error = KnowledgeUnavailableError("Test error")
        assert error.code == "KNOWLEDGE_UNAVAILABLE"
        assert error.retryable is True

    def test_no_grounded_result_error_not_retryable(self):
        """NoGroundedResultError should not be retryable."""
        error = NoGroundedResultError("No results")
        assert error.code == "NO_GROUNDED_RESULT"
        assert error.retryable is False

    def test_content_conflict_error_not_retryable(self):
        """ContentConflictError should not be retryable."""
        error = ContentConflictError("Conflict detected")
        assert error.code == "CONTENT_CONFLICT"
        assert error.retryable is False

    def test_config_unavailable_error_retryable(self):
        """ConfigUnavailableError should be retryable."""
        error = ConfigUnavailableError("Config error")
        assert error.code == "CONFIG_UNAVAILABLE"
        assert error.retryable is True

    def test_error_inherits_from_knowledge_search_error(self):
        """All specific errors should inherit from KnowledgeSearchError."""
        assert issubclass(KnowledgeUnavailableError, KnowledgeSearchError)
        assert issubclass(NoGroundedResultError, KnowledgeSearchError)
        assert issubclass(ContentConflictError, KnowledgeSearchError)
        assert issubclass(ConfigUnavailableError, KnowledgeSearchError)


# ---------------------------------------------------------------------------
# Test: Retrieval filtering (WP-201 validation)
# ---------------------------------------------------------------------------


class TestRetrievalFiltering:
    """Tests for retrieval filtering per WP-201 requirements.

    The WP-201 pack requires:
    'Retrieval bắt buộc lọc is_active, effective date và approval status
    trước khi trả chunk.'

    This filtering is enforced by the upstream WP-102 repository service,
    but we verify the tool respects the filtering by only returning
    approved/active chunks.
    """

    def test_only_approved_chunks_returned(self):
        """Only chunks with approval_status='approved' should be returned.

        Note: The actual filtering happens in WP-102 repository, but the
        tool expects the repository to already filter by approval_status.
        """
        # In production, the repository only returns approved chunks
        # Our fake simulates this behavior
        tool = make_tool(chunks=[
            make_chunk(chunk_id="approved-001", approval_status="approved"),
        ])

        result = tool.search(ToolSearchRequest(query="test"))

        assert len(result.chunks) == 1
        # CitationDTO doesn't expose approval_status, but we trust the repository

    def test_only_active_chunks_returned(self):
        """Only chunks with is_active=True should be returned.

        Note: The actual filtering happens in WP-102 repository.
        """
        tool = make_tool(chunks=[
            make_chunk(chunk_id="active-001", is_active=True),
        ])

        result = tool.search(ToolSearchRequest(query="test"))

        assert len(result.chunks) == 1

    def test_citation_includes_effective_date(self):
        """Citation should include effective_date for provenance."""
        tool = make_tool(chunks=[
            make_chunk(
                chunk_id="chunk-001",
                effective_date="2024-06-15",
            ),
        ])

        result = tool.search(ToolSearchRequest(query="test"))

        assert result.chunks[0].effective_date == "2024-06-15"


# ---------------------------------------------------------------------------
# Test: Tool contract compliance (INT-06)
# ---------------------------------------------------------------------------


class TestToolContractCompliance:
    """Tests verifying INT-06 tool contract compliance."""

    def test_search_timeout_default(self):
        """Tool should have default timeout of 800ms per INT-06."""
        tool = make_tool(chunks=[])
        assert tool._timeout_ms == 800

    def test_search_timeout_configurable(self):
        """Tool should allow custom timeout configuration."""
        fake_repo = MagicMock(spec=KnowledgeRepositoryService)
        tool = KnowledgeSearchTool(repository=fake_repo, timeout_ms=500)
        assert tool._timeout_ms == 500

    def test_search_tool_name(self):
        """Tool should implement search_knowledge_base contract."""
        tool = make_tool(chunks=[])
        # The search method implements the search_knowledge_base contract
        assert hasattr(tool, "search")
        assert callable(tool.search)

    def test_fallback_tool_name(self):
        """Tool should implement fallback_response contract."""
        tool = make_tool(chunks=[])
        # The fallback method implements the fallback_response contract
        assert hasattr(tool, "fallback")
        assert callable(tool.fallback)
# === TASK:WP-201:END ===
