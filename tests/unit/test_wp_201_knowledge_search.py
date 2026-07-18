# === TASK:WP-201:START ===
import pytest
from unittest.mock import MagicMock
from packages.contracts.dto import SearchCandidateDTO
from apps.api.ai.rag import (
    reciprocal_rank_fusion,
    rerank_candidates,
    map_citations_to_response,
    search_hospital_information,
    check_sufficiency_and_conflicts
)

def test_reciprocal_rank_fusion_logic():
    # 2 vector candidates
    v1 = SearchCandidateDTO("c1", "content 1", 0.9, "bhyt", "sub1", "s1", "p1", "v1")
    v2 = SearchCandidateDTO("c2", "content 2", 0.8, "bhyt", "sub1", "s1", "p1", "v1")
    
    # 2 lexical candidates (c2 overlaps, c3 is unique)
    l1 = SearchCandidateDTO("c2", "content 2", 0.5, "bhyt", "sub1", "s1", "p1", "v1")
    l2 = SearchCandidateDTO("c3", "content 3", 0.4, "bhyt", "sub1", "s1", "p1", "v1")
    
    fused = reciprocal_rank_fusion([v1, v2], [l1, l2], k=60)
    
    # c2 should have higher score than c1 because it appears in both
    assert fused[0].chunk_id == "c2"
    assert fused[1].chunk_id == "c1"
    assert fused[2].chunk_id == "c3"
    assert fused[0].vector_rank == 2
    assert fused[0].lexical_rank == 1
    assert fused[0].fused_rank == 1
    assert fused[1].vector_rank == 1
    assert fused[1].lexical_rank is None
    assert fused[1].fused_rank == 2

def test_reranker_adapter_fallback_on_failure(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "fake")
    c1 = SearchCandidateDTO("c1", "content 1", 0.9, "bhyt", "sub1", "s1", "p1", "v1")
    
    # Reranking with invalid API response should gracefully fall back to original
    reranked, applied, error = rerank_candidates(
        "query", [c1], api_key="fake", base_url="https://invalid.url", provider="jina"
    )
    assert not applied
    assert error is not None
    assert reranked[0].chunk_id == "c1"

def test_citation_mapping():
    c1 = SearchCandidateDTO("c1", "Giá dịch vụ khám bệnh là 150.000 VND.", 0.9, "bhyt", "sub1", "s1", "p1", "v1")
    
    response = "Giá khám bệnh là 150.000 VND. [[c1]]"
    grounded, citations = map_citations_to_response(response, [c1])
    
    assert grounded
    assert len(citations) == 1
    assert citations[0].chunk_id == "c1"
    assert citations[0].matched_text == "Giá khám bệnh là 150.000 VND."

def test_citation_mapping_rejects_missing_or_unknown_chunk_id():
    c1 = SearchCandidateDTO("c1", "Bệnh viện mở cửa lúc 8:00.", 0.9, "general", "hours", "s1", "p1", "v1")

    assert not map_citations_to_response("Bệnh viện mở cửa lúc 8:00.", [c1])[0]
    assert not map_citations_to_response("Bệnh viện mở cửa lúc 8:00. [[fake]]", [c1])[0]

def test_citation_mapping_rejects_unsupported_number():
    c1 = SearchCandidateDTO("c1", "Bệnh viện mở cửa lúc 8:00.", 0.9, "general", "hours", "s1", "p1", "v1")

    grounded, _ = map_citations_to_response("Bệnh viện mở cửa lúc 9:00. [[c1]]", [c1])

    assert not grounded

def test_sufficiency_conflict_detection():
    c1 = SearchCandidateDTO("c1", "Giá dịch vụ: 150.000 VND.", 0.9, "bhyt", "khám bệnh", "s1", "p1", "v1")
    c2 = SearchCandidateDTO("c2", "Giá dịch vụ: 200.000 VND.", 0.8, "bhyt", "khám bệnh", "s1", "p1", "v1")
    
    # Two candidates in the same subtopic but different prices -> conflict
    sufficient, reason = check_sufficiency_and_conflicts([c1, c2])
    assert not sufficient
    assert "Conflict detected" in reason

    # No conflict when price matches
    c3 = SearchCandidateDTO("c3", "Giá dịch vụ: 150.000 VND.", 0.8, "bhyt", "khám bệnh", "s1", "p1", "v1")
    sufficient, reason = check_sufficiency_and_conflicts([c1, c3])
    assert sufficient
# === TASK:WP-201:END ===
