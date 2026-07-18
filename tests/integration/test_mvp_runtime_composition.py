# === TASK:MVP-RUNTIME-01:START ===
"""Runtime composition tests for the real PC-01 dependency graph."""

from unittest.mock import Mock

import pytest

from apps.api.core.runtime_dependencies import (
    InformationKnowledgeSearchAdapter,
    RuntimeDependencyError,
    _vector_literal,
    create_jina_query_embedding_provider,
)


class FakeEmbeddingResponse:
    def __init__(self, vector):
        self._vector = vector

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"embedding": self._vector}]}


def test_jina_query_embedder_uses_query_task_and_1024_dimensions():
    post = Mock(return_value=FakeEmbeddingResponse([0.1] * 1024))
    embed = create_jina_query_embedding_provider(
        {"JINA_API_KEY": "test-key", "EMBEDDING_BASE_URL": "https://jina.example/v1"},
        post=post,
    )

    vector = embed("Giá khám BHYT là bao nhiêu?")

    assert len(vector) == 1024
    assert post.call_args.kwargs["json"]["task"] == "retrieval.query"
    assert post.call_args.kwargs["json"]["dimensions"] == 1024


def test_jina_query_embedder_rejects_wrong_dimension():
    embed = create_jina_query_embedding_provider(
        {"JINA_API_KEY": "test-key"},
        post=Mock(return_value=FakeEmbeddingResponse([0.1] * 1023)),
    )

    with pytest.raises(RuntimeDependencyError, match="invalid query embedding"):
        embed("test")


def test_vector_literal_rejects_non_pilot_dimension():
    with pytest.raises(RuntimeDependencyError, match="1024"):
        _vector_literal([0.0] * 768)


def test_information_search_adapter_preserves_pipeline_contract():
    result = Mock()
    result.to_dict.return_value = {"chunks": [], "has_results": False, "sufficient": False, "conflict": False}
    tool = Mock()
    tool.search.return_value = result

    adapter = InformationKnowledgeSearchAdapter(tool)
    response = adapter.search("Giờ khám", top_k=3, filters={"domains": ["quy_trinh"]})

    assert response["has_results"] is False
    request = tool.search.call_args.args[0]
    assert request.query == "Giờ khám"
    assert request.top_k == 3
    assert request.domains == ["quy_trinh"]
# === TASK:MVP-RUNTIME-01:END ===
