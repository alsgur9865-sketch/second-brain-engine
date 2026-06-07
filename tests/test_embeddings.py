# File: tests/test_embeddings.py
# get_embedder 팩토리가 provider별로 올바른 클래스/base_url/model을 만드는지 (네트워크 0).

from types import SimpleNamespace

import pytest

from app.embeddings import OllamaEmbedder, OpenAIEmbedder, get_embedder


def _settings(**kw):
    base = dict(
        embedding_provider="ollama",
        embed_model="",
        embed_base_url="",
        embed_api_key="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_ollama_기본프리셋():
    emb = get_embedder(_settings(embedding_provider="ollama"))
    assert isinstance(emb, OllamaEmbedder)
    assert emb.model == "bge-m3"
    assert emb.provider == "ollama"
    assert emb.url == "http://localhost:11434/api/embed"


def test_lmstudio_openai호환_로컬_키없음():
    emb = get_embedder(_settings(embedding_provider="lmstudio", embed_model="bge-m3"))
    assert isinstance(emb, OpenAIEmbedder)
    assert emb.url == "http://localhost:1234/v1/embeddings"
    assert emb.model == "bge-m3"
    assert emb.headers == {}          # 키 없으면 인증 헤더 없음
    assert emb.provider == "lmstudio"


def test_gemini_openai호환_엔드포인트():
    emb = get_embedder(_settings(embedding_provider="gemini", embed_api_key="AIzaXXX"))
    assert isinstance(emb, OpenAIEmbedder)
    assert emb.url == "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"
    assert emb.model == "gemini-embedding-001"
    assert emb.headers == {"Authorization": "Bearer AIzaXXX"}


def test_voyage_기본모델():
    emb = get_embedder(_settings(embedding_provider="voyage", embed_api_key="vk"))
    assert emb.url == "https://api.voyageai.com/v1/embeddings"
    assert emb.model == "voyage-3.5"


def test_사용자값이_프리셋_기본을_덮어쓴다():
    emb = get_embedder(_settings(
        embedding_provider="openai",
        embed_base_url="http://localhost:9999/v1",
        embed_model="my-model",
    ))
    assert emb.url == "http://localhost:9999/v1/embeddings"
    assert emb.model == "my-model"


def test_알수없는_provider는_에러():
    with pytest.raises(ValueError, match="알 수 없는"):
        get_embedder(_settings(embedding_provider="bogus"))
