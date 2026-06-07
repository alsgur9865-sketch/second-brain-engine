# File: app/embeddings.py
# 임베딩 백엔드 추상화 + 프리셋. provider 이름만 바꾸면 백엔드가 교체된다.
# OpenAI 호환(LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini)은 한 클래스로 처리하고,
# provider 이름은 base_url/기본모델 프리셋만 결정한다. 인터페이스는 embed()가 전부.

from abc import ABC, abstractmethod

import httpx


class EmbeddingProvider(ABC):
    """모든 임베딩 백엔드의 공통 계약."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 묶음을 벡터 묶음으로 변환."""
        raise NotImplementedError


class OllamaEmbedder(EmbeddingProvider):
    """로컬 Ollama 임베딩. 추가 인프라 0 — 이미 깔린 Ollama 사용."""

    def __init__(self, base_url: str, model: str):
        self.url = f"{base_url.rstrip('/')}/api/embed"
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        # 일부 ollama 버전 + bge-m3는 배치 input에서 500을 낸다 → 단건씩 호출
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
    """OpenAI 호환 임베딩. LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini 공용.

    base_url만 프리셋으로 갈아끼우면 된다. 로컬 서버는 보통 키가 없으므로,
    api_key가 비면 Authorization 헤더를 붙이지 않는다.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.url = f"{base_url.rstrip('/')}/embeddings"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
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


# provider 이름 → (종류, 기본 base_url, 기본 모델). 사용자 .env 값이 비면 이 기본을 쓴다.
PRESETS: dict[str, dict[str, str]] = {
    "ollama":   {"kind": "ollama", "base_url": "http://localhost:11434", "model": "bge-m3"},
    "lmstudio": {"kind": "openai", "base_url": "http://localhost:1234/v1", "model": ""},
    "llamacpp": {"kind": "openai", "base_url": "http://localhost:8080/v1", "model": ""},
    "tei":      {"kind": "openai", "base_url": "http://localhost:8080/v1", "model": ""},
    "openai":   {"kind": "openai", "base_url": "https://api.openai.com/v1",
                 "model": "text-embedding-3-small"},
    "voyage":   {"kind": "openai", "base_url": "https://api.voyageai.com/v1",
                 "model": "voyage-3.5"},
    "gemini":   {"kind": "openai",
                 "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                 "model": "gemini-embedding-001"},
}


def get_embedder(settings) -> EmbeddingProvider:
    """프리셋 + 설정값으로 임베더 생성. 우선순위: 사용자 값(.env) > 프리셋 기본."""
    provider = settings.embedding_provider.lower()
    preset = PRESETS.get(provider)
    if preset is None:
        raise ValueError(
            f"알 수 없는 embedding_provider: {settings.embedding_provider!r} "
            f"(지원: {', '.join(PRESETS)})"
        )
    base_url = settings.embed_base_url or preset["base_url"]
    model = settings.embed_model or preset["model"]
    if preset["kind"] == "ollama":
        emb: EmbeddingProvider = OllamaEmbedder(base_url, model)
    else:
        emb = OpenAIEmbedder(settings.embed_api_key, base_url, model)
    emb.provider = provider   # 컬렉션 모델별 분리(index.py)에서 사용
    return emb
