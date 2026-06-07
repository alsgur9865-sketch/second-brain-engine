# File: app/embeddings.py
# 임베딩 프로바이더 추상화. 새 프로바이더는 EmbeddingProvider 상속 + get_embedder에 한 줄 추가.
# 인터페이스를 얇게 유지 — embed(텍스트 리스트) → 벡터 리스트, 이게 전부.

from abc import ABC, abstractmethod

import httpx


class EmbeddingProvider(ABC):
    """모든 임베딩 프로바이더의 공통 계약."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 묶음을 벡터 묶음으로 변환."""
        raise NotImplementedError


class OllamaEmbedder(EmbeddingProvider):
    """로컬 Ollama 임베딩 (기본). 추가 인프라 0 — 이미 깔린 Ollama 사용."""

    def __init__(self, base_url: str, model: str):
        self.url = f"{base_url.rstrip('/')}/api/embed"
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        # 일부 ollama 버전 + bge-m3는 배치 input(2개 이상)에서 500을 낸다 → 단건씩 호출
        out: list[list[float]] = []
        for text in texts:
            r = httpx.post(
                self.url,
                json={"model": self.model, "input": text},
                timeout=120,
            )
            r.raise_for_status()
            out.append(r.json()["embeddings"][0])
        return out


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI 호환 임베딩. 교체 시 SB_EMBEDDING_PROVIDER=openai."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.url = f"{base_url.rstrip('/')}/embeddings"
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        r = httpx.post(
            self.url,
            headers=self.headers,
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        return [item["embedding"] for item in r.json()["data"]]


def get_embedder(settings) -> EmbeddingProvider:
    """설정값으로 프로바이더 인스턴스 생성 (팩토리)."""
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        return OpenAIEmbedder(
            settings.openai_api_key,
            settings.openai_base_url,
            settings.openai_embed_model,
        )
    if provider == "ollama":
        return OllamaEmbedder(
            settings.ollama_base_url,
            settings.ollama_embed_model,
        )
    raise ValueError(f"알 수 없는 embedding_provider: {settings.embedding_provider!r}")
