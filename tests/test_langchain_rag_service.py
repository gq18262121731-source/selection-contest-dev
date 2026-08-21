from __future__ import annotations

import json
from pathlib import Path

from agent.langchain_rag_service import LangChainRAGService
from agent.langgraph_health_agent import HealthAgentService as DeviceHealthAgentService
from backend.api.chat_api import CommunityAnalysisRequest, DeviceAnalysisRequest
from backend.config import get_settings
from backend.services.voice_service import VoiceService


def _build_settings(tmp_path: Path):
    return get_settings().model_copy(
        update={
            "chroma_path": str(tmp_path / "chroma"),
            "qwen_api_key": "test-key",
            "qwen_model": "qwen-plus",
            "qwen_embedding_model": "text-embedding-v3",
            "qwen_rerank_model": "qwen-reranker-v1",
            "qwen_enable_rerank": True,
        }
    )


def test_rag_service_exposes_file_fingerprints_and_retrieves_hits(tmp_path: Path, monkeypatch) -> None:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "oxygen.md").write_text(
        "# 血氧说明\n\n血氧低于 93% 要复测，低于 90% 要尽快就医。\n",
        encoding="utf-8",
    )
    (knowledge_dir / "pressure.md").write_text(
        "# 血压说明\n\n晨起血压偏高时先静坐复测，不建议自己加药。\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(LangChainRAGService, "_build_vector_store", lambda self: None)
    monkeypatch.setattr(LangChainRAGService, "_build_reranker", lambda self: None)

    rag = LangChainRAGService(_build_settings(tmp_path), knowledge_dir)

    stats = rag.stats()

    assert stats["document_count"] == 2
    assert stats["file_count"] == 2
    assert stats["docs_hash"]
    assert stats["files"]
    assert any(item["source"] == "oxygen.md" for item in stats["files"])
    assert all(item["sha256"] for item in stats["files"])
    assert all(item["chunk_count"] >= 1 for item in stats["files"])
    assert all(chunk.metadata.get("source_fingerprint") for chunk in rag._chunks)

    results = rag.retrieve("血氧低怎么办", top_k=2, allow_rerank=False)

    assert results
    assert results[0]["source_path"] == "oxygen.md"
    assert "血氧" in results[0]["snippet"]


def test_rag_service_writes_manifest_when_vector_store_is_ready(tmp_path: Path, monkeypatch) -> None:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "faq.md").write_text(
        "# 常规问答\n\n老人头晕时先看血压、血氧和近期饮水情况。\n",
        encoding="utf-8",
    )

    class FakeCollection:
        def count(self) -> int:
            return 0

    class FakeChroma:
        def __init__(self, *args, **kwargs) -> None:
            self._collection = FakeCollection()
            self.added_ids: list[str] = []

        def add_documents(self, documents, ids):
            self.added_ids.extend(ids)

    monkeypatch.setattr("agent.langchain_rag_service.Chroma", FakeChroma)
    monkeypatch.setattr(LangChainRAGService, "_build_reranker", lambda self: None)

    rag = LangChainRAGService(_build_settings(tmp_path), knowledge_dir)

    manifest_path = Path(rag.stats()["fingerprint_manifest"])

    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["docs_hash"] == rag.stats()["docs_hash"]
    assert payload["vector_collection"] == rag.stats()["vector_collection"]
    assert payload["files"][0]["source"] == "faq.md"


def test_health_agent_retrieve_node_enables_qwen_rerank(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)

    class FakeRAG:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def search(self, query: str, top_k: int, *, network_online: bool, allow_rerank: bool | None):
            self.calls.append(bool(allow_rerank))
            return [f"hit:{query}:{top_k}"]

    rag = FakeRAG()
    service = DeviceHealthAgentService(settings, rag)

    result = service._retrieve_node({"question": "血氧低怎么办"})

    assert result["knowledge_hits"] == ["hit:血氧低怎么办:3"]
    assert rag.calls == [True]


def test_chat_requests_accept_qwen_alias() -> None:
    community_payload = CommunityAnalysisRequest(
        question="请简短说明老人血氧低怎么办。",
        mode="qwen",
        provider="qwen",
    )
    device_payload = DeviceAnalysisRequest(
        device_mac="AA:BB:CC:DD:EE:FF",
        question="老人头晕时先看什么？",
        mode="qwen",
    )

    assert community_payload.mode == "qwen"
    assert community_payload.provider == "qwen"
    assert device_payload.mode == "qwen"


def test_voice_service_uses_qwen_voice_models(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path).model_copy(
        update={
            "qwen_asr_model": "Qwen3-ASR-Flash",
            "qwen_tts_model": "Qwen3-TTS-Flash",
        }
    )
    voice_service = VoiceService(settings)

    assert settings.qwen_asr_model_name == "Qwen3-ASR-Flash"
    assert settings.qwen_tts_model_name == "Qwen3-TTS-Flash"
    assert voice_service._settings.qwen_asr_model_name == "Qwen3-ASR-Flash"
    assert voice_service._settings.qwen_tts_model_name == "Qwen3-TTS-Flash"
