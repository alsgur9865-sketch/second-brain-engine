# 교체형 임베딩 백엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.env`의 `SB_EMBEDDING_PROVIDER` 한 줄 + (클라우드면) API 키 한 줄만 바꿔 임베딩 백엔드를 교체하고, 모델이 바뀌면 엔진이 모델별 인덱스를 자동으로 새로 빌드한다.

**Architecture:** OpenAI 호환이 사실상 표준이라 `OpenAIEmbedder` 하나가 LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini를 모두 처리한다. provider 이름은 base_url/기본모델 **프리셋**만 결정한다. 컬렉션 이름을 `{base}__{provider}_{model}`로 자동 분리하면 기존 증분 `sync()`가 새 컬렉션을 자동 full 빌드해 준다 — 별도 재인덱싱 코드 불필요.

**Tech Stack:** Python 3.11, FastAPI, Chroma, httpx, pydantic-settings, pytest, ruff.

---

## 사전 지식 (구현자가 알아야 할 것)

- **검증 명령** (이 프로젝트 전용, cwd reset 때문에 절대경로 필수):
  - pytest: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine -q`
  - ruff: `/d/project/second-brain-engine/.venv/Scripts/ruff.exe check /d/project/second-brain-engine`
  - git: `git -C "D:/project/second-brain-engine" <cmd>`
- Bash 도구는 git-bash(POSIX). 드라이브는 `/d/...`. PowerShell cmdlet 금지.
- `.env*` 파일은 Read/Bash 권한으로 막혀 있다. 존재 확인은 `git -C ... ls-files`로. 편집이 막히면 사용자에게 직접 수정 요청.
- LF→CRLF 경고는 정상, 무해.
- 현재 임베딩 인터페이스: `EmbeddingProvider.embed(texts: list[str]) -> list[list[float]]`. 이것만이 계약이다.

## 파일 구조

| 파일 | 동작 | 책임 |
|---|---|---|
| `app/config.py` | 수정 | 임베딩 설정을 공통 4필드(`embedding_provider`/`embed_model`/`embed_base_url`/`embed_api_key`)로 정리 |
| `app/embeddings.py` | 수정 | `PRESETS` dict + `get_embedder` 팩토리. OpenAI 호환은 한 클래스로. 새 임베딩 클래스 없음 |
| `app/index.py` | 수정 | `_collection_slug`/`_collection_name` + `BrainIndex.__init__`이 모델별 컬렉션 이름 생성 |
| `app/main.py` | 수정 | `/health`에 `model`·`collection` 노출 |
| `tests/test_embeddings.py` | 생성 | 팩토리 단위 테스트(네트워크 0) |
| `tests/test_index.py` | 수정 | 컬렉션 이름 슬러그·분리 테스트 |
| `docker-compose.yml` | 수정 | `SB_OLLAMA_*` → 새 이름 |
| `.env.example` | 수정 | 새 설정 이름 + 전환 예시 |
| `README.md` | 수정 | 백엔드 전환 섹션 |
| `progress.md` | 수정 | 진행 기록 + 임베딩 서술 갱신 |

---

## Task 1: 설정 통합 + 프리셋 팩토리

**Files:**
- Modify: `app/config.py` (전체 교체)
- Modify: `app/embeddings.py` (전체 교체)
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: 팩토리 테스트를 먼저 작성 (`tests/test_embeddings.py`)**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine/tests/test_embeddings.py -q`
Expected: FAIL — 현재 `get_embedder`는 `settings.embed_base_url` 등을 모르고 `provider` 속성도 없어 AttributeError/오류.

- [ ] **Step 3: `app/config.py` 전체 교체**

```python
# File: app/config.py
# 엔진 전체 설정. 환경변수(SB_ 접두사) 또는 .env 파일로 주입.
# 임베딩 교체는 embedding_provider 한 줄 + (클라우드면) embed_api_key 로 끝난다.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- 노트 / 벡터DB 위치 ---
    notes_path: str = "../my-second-brain"   # 헤르메스가 clone한 노트 레포 경로
    chroma_path: str = "./chroma_db"          # Chroma 벡터DB 저장 폴더(파일 기반)
    collection_name: str = "second_brain"     # 실제 컬렉션은 모델별로 자동 분리됨(index.py)
    ignore_dirs: list[str] = ["templates"]    # 인덱싱 제외 폴더

    # --- 임베딩 백엔드 (교체형) ---
    # provider: ollama | lmstudio | llamacpp | tei | openai | voyage | gemini
    embedding_provider: str = "ollama"
    embed_model: str = ""        # 비우면 provider 프리셋 기본 모델
    embed_base_url: str = ""     # 비우면 provider 프리셋 기본 주소(로컬 포트만 다르면 여기만 지정)
    embed_api_key: str = ""      # 클라우드 provider(openai/voyage/gemini) API 키

    # --- 검색 동작 ---
    auto_sync_on_search: bool = True          # 검색 직전 노트 변경분 자동 재인덱싱

    # --- API 보안 (옵션, 임베딩 키와 무관) ---
    api_key: str = ""                         # 비우면 인증 없음. 설정 시 X-API-Key 헤더 필수

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SB_",
        extra="ignore",
    )
```

- [ ] **Step 4: `app/embeddings.py` 전체 교체**

```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine/tests/test_embeddings.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git -C "D:/project/second-brain-engine" add app/config.py app/embeddings.py tests/test_embeddings.py
git -C "D:/project/second-brain-engine" commit -m "feat: 임베딩 프리셋 팩토리 — provider 이름만으로 7종 백엔드 교체"
```

---

## Task 2: 모델별 컬렉션 자동 분리

**Files:**
- Modify: `app/index.py` (헬퍼 2개 추가 + `BrainIndex.__init__`)
- Modify: `tests/test_index.py` (테스트 추가, 기존 그대로)

- [ ] **Step 1: 컬렉션 이름 테스트를 먼저 작성 (`tests/test_index.py` 맨 아래에 추가)**

기존 import 줄(`from app.index import (...)`)에 `_collection_name`, `_collection_slug`를 추가하고, 파일 끝에 아래 테스트를 붙인다.

import 줄을 다음으로 교체:
```python
from app.index import (
    BrainIndex,
    _collection_name,
    _collection_slug,
    _safe_rel,
    _slugify,
    chunk_markdown,
    extract_links,
    parse_frontmatter,
)
```

파일 끝에 추가:
```python
# ---------- 모델별 컬렉션 분리 ----------


def test_컬렉션이름_모델별로_분리된다():
    assert _collection_name("second_brain", "ollama", "bge-m3") == "second_brain__ollama_bge_m3"
    assert (
        _collection_name("second_brain", "gemini", "gemini-embedding-001")
        == "second_brain__gemini_gemini_embedding_001"
    )


def test_컬렉션이름_provider없으면_base유지():
    # 가짜 임베더처럼 provider 속성이 없을 때는 기존 base 컬렉션을 그대로 쓴다(하위호환)
    assert _collection_name("test", "", "") == "test"


def test_컬렉션슬러그_특수문자_치환():
    assert _collection_slug("ollama", "nomic-embed-text:latest") == "ollama_nomic_embed_text_latest"
    assert _collection_slug("lmstudio", "") == "lmstudio"   # 모델 비면 provider만


def test_BrainIndex_컬렉션이_모델별로_분리된다(tmp_path):
    settings = SimpleNamespace(
        notes_path=str(tmp_path / "notes"),
        chroma_path=str(tmp_path / "chroma"),
        collection_name="second_brain",
        ignore_dirs=["templates"],
    )
    os.makedirs(settings.notes_path, exist_ok=True)
    emb = _FakeEmbedder()
    emb.provider = "ollama"
    emb.model = "bge-m3"
    brain = BrainIndex(settings, emb)
    assert brain.collection_name == "second_brain__ollama_bge_m3"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine/tests/test_index.py -q`
Expected: FAIL — `ImportError: cannot import name '_collection_name'`.

- [ ] **Step 3: `app/index.py`에 헬퍼 추가**

기존 정규식 상수 블록(`_HEADING`/`_UNSAFE`/`_LINK`) 바로 아래에 추가:
```python
_COLL_UNSAFE = re.compile(r"[^a-zA-Z0-9]+")   # Chroma 컬렉션 이름은 영숫자/_/- 만 안전


def _collection_slug(provider: str, model: str) -> str:
    """provider+model을 Chroma 컬렉션 이름 조각으로. 영숫자 외(`:`/`/`/`.`/`-`)는 _로, 양끝 _ 제거."""
    raw = f"{provider}__{model}" if model else provider
    return _COLL_UNSAFE.sub("_", raw).strip("_")


def _collection_name(base: str, provider: str, model: str) -> str:
    """모델별로 컬렉션을 분리. provider가 없으면(테스트 등) base를 그대로 쓴다(하위호환)."""
    if not provider:
        return base
    return f"{base}__{_collection_slug(provider, model)}"
```

- [ ] **Step 4: `BrainIndex.__init__` 교체**

기존:
```python
    def __init__(self, settings, embedder: EmbeddingProvider):
        self.notes_path = settings.notes_path
        self.ignore_dirs = set(settings.ignore_dirs)
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection(settings.collection_name)
```
교체 후:
```python
    def __init__(self, settings, embedder: EmbeddingProvider):
        self.notes_path = settings.notes_path
        self.ignore_dirs = set(settings.ignore_dirs)
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        # 모델별로 컬렉션을 분리 → 모델을 바꾸면 빈 컬렉션을 보게 되고 sync()가 자동 full 빌드.
        provider = getattr(embedder, "provider", "")
        model = getattr(embedder, "model", "")
        self.collection_name = _collection_name(settings.collection_name, provider, model)
        self.collection = self.client.get_or_create_collection(self.collection_name)
```

- [ ] **Step 5: 테스트 통과 확인 (신규 + 기존 회귀)**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine/tests/test_index.py -q`
Expected: PASS — 기존 BrainIndex 테스트(`collection_name="test"`, provider 속성 없음 → `_collection_name`이 base "test" 반환)도 그대로 통과.

- [ ] **Step 6: 커밋**

```bash
git -C "D:/project/second-brain-engine" add app/index.py tests/test_index.py
git -C "D:/project/second-brain-engine" commit -m "feat: 모델별 컬렉션 자동 분리 — 모델 바꾸면 sync()가 새 인덱스 자동 빌드"
```

---

## Task 3: /health 에 백엔드 노출

**Files:**
- Modify: `app/main.py` (`health` 함수만)

- [ ] **Step 1: `health()` 함수 교체**

기존:
```python
@app.get("/health")
def health() -> dict:
    # 임베딩 백엔드(ollama 등)가 실제로 응답하는지까지 확인
    try:
        embedder.embed(["health"])
        embedding_ok = True
    except Exception:
        embedding_ok = False
    return {
        "status": "ok" if embedding_ok else "degraded",
        "embedding_ok": embedding_ok,
        "provider": settings.embedding_provider,
        "notes_path": settings.notes_path,
        "documents": brain.collection.count(),
    }
```
교체 후:
```python
@app.get("/health")
def health() -> dict:
    # 임베딩 백엔드(ollama 등)가 실제로 응답하는지까지 확인
    try:
        embedder.embed(["health"])
        embedding_ok = True
    except Exception:
        embedding_ok = False
    return {
        "status": "ok" if embedding_ok else "degraded",
        "embedding_ok": embedding_ok,
        "provider": settings.embedding_provider,
        "model": getattr(embedder, "model", ""),
        "collection": brain.collection_name,
        "notes_path": settings.notes_path,
        "documents": brain.collection.count(),
    }
```

- [ ] **Step 2: import이 깨지지 않았는지 빠른 점검**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -c "import app.main"`
Expected: 출력 없음(에러 없이 import 성공). ollama가 떠 있지 않아도 import 자체는 성공해야 한다. 만약 `lifespan`/모듈 로드 단계에서 ollama 호출로 막히면 그건 정상(런타임 동작), import만 통과하면 OK.

- [ ] **Step 3: 커밋**

```bash
git -C "D:/project/second-brain-engine" add app/main.py
git -C "D:/project/second-brain-engine" commit -m "feat: /health에 현재 임베딩 model·collection 노출"
```

---

## Task 4: 설정·문서 갱신

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example` (권한 막히면 사용자에게 요청)
- Modify: `README.md`
- Modify: `progress.md`

- [ ] **Step 1: `docker-compose.yml`의 환경변수 교체**

기존 3줄:
```yaml
      SB_EMBEDDING_PROVIDER: ollama
      # 컨테이너에서 호스트의 Ollama 접근 (호스트는 OLLAMA_HOST=0.0.0.0 필요)
      SB_OLLAMA_BASE_URL: http://host.docker.internal:11434
      SB_OLLAMA_EMBED_MODEL: bge-m3
```
교체 후:
```yaml
      SB_EMBEDDING_PROVIDER: ollama
      # 컨테이너에서 호스트의 Ollama 접근 (호스트는 OLLAMA_HOST=0.0.0.0 필요)
      SB_EMBED_BASE_URL: http://host.docker.internal:11434
      SB_EMBED_MODEL: bge-m3
```

- [ ] **Step 2: `.env.example` 존재 확인 후 갱신**

존재 확인: `git -C "D:/project/second-brain-engine" ls-files .env.example`
- 추적되면: 임베딩 관련 줄을 아래 블록으로 교체(권한으로 Read/Write가 막히면 이 블록을 사용자에게 보여주고 직접 붙여넣기 요청).
- 없으면: 이 Step은 건너뛴다.

```dotenv
# --- 임베딩 백엔드 (교체형) ---
# provider: ollama | lmstudio | llamacpp | tei | openai | voyage | gemini
SB_EMBEDDING_PROVIDER=ollama
SB_EMBED_MODEL=          # 비우면 provider 기본 모델
SB_EMBED_BASE_URL=       # 비우면 provider 기본 주소(로컬 서버 포트만 다르면 여기만)
SB_EMBED_API_KEY=        # 클라우드(openai/voyage/gemini) API 키

# 전환 예시:
#   Gemini    : SB_EMBEDDING_PROVIDER=gemini  + SB_EMBED_API_KEY=AIza...
#   OpenAI    : SB_EMBEDDING_PROVIDER=openai  + SB_EMBED_API_KEY=sk-...
#   Voyage    : SB_EMBEDDING_PROVIDER=voyage  + SB_EMBED_API_KEY=pa-...
#   LM Studio : SB_EMBEDDING_PROVIDER=lmstudio + SB_EMBED_MODEL=<로드한 모델명>
#   llama.cpp : SB_EMBEDDING_PROVIDER=llamacpp + SB_EMBED_MODEL=<서버 모델>
```

- [ ] **Step 3: `README.md`의 임베딩 설정 안내 갱신**

`README.md`에서 `SB_OLLAMA`/`SB_OPENAI`/임베딩 provider를 설명하는 부분을 찾는다:
`/d/project/second-brain-engine/.venv/Scripts/python.exe - <<'PY'`은 쓰지 말고, Grep 도구로 `SB_OLLAMA|SB_OPENAI|embedding_provider|EMBEDDING_PROVIDER`를 `README.md`에서 찾아, 해당 표/코드블록을 아래 표로 갱신한다(영문/한글 양쪽 모두 있으면 둘 다).

갱신할 표 (한글 버전 예):
```markdown
### 임베딩 백엔드 교체

`SB_EMBEDDING_PROVIDER` 한 줄(클라우드면 `SB_EMBED_API_KEY` 추가)만 바꾸고 재시작하면 교체됩니다.
모델이 바뀌면 인덱스가 모델별로 자동 분리·재빌드됩니다.

| provider | 종류 | 기본 모델 | 키 |
|---|---|---|---|
| `ollama` (기본) | 로컬 | `bge-m3` | — |
| `lmstudio` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `llamacpp` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `tei` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `openai` | 클라우드 | `text-embedding-3-small` | ✅ |
| `voyage` | 클라우드 | `voyage-3.5` | ✅ |
| `gemini` | 클라우드 | `gemini-embedding-001` | ✅ |

예) Gemini로 전환: `SB_EMBEDDING_PROVIDER=gemini`, `SB_EMBED_API_KEY=AIza...`
```

영문 버전이 있으면 같은 내용을 영문으로도 갱신한다.

- [ ] **Step 4: `progress.md` 갱신**

- 56행 `Python FastAPI + Chroma + ollama bge-m3 임베딩.` →
  `Python FastAPI + Chroma + 교체형 임베딩(기본 ollama bge-m3; lmstudio/llamacpp/tei/openai/voyage/gemini 프리셋).`
- 69행 `임베딩: 교체형(프로바이더 인터페이스). 기본 로컬 ollama bge-m3, config로 OpenAI 등 교체 가능.` →
  `임베딩: 교체형 — provider 이름 한 줄로 7종(ollama/lmstudio/llamacpp/tei/openai/voyage/gemini) 교체. 모델별 컬렉션 자동 분리·재빌드.`
- "진행 기록" 맨 위에 한 줄 추가:
  `- **2026-06-07 교체형 임베딩 백엔드**: provider 이름 한 줄로 로컬(ollama/lmstudio/llamacpp/tei)·클라우드(openai/voyage/gemini) 임베딩 교체. OpenAI 호환 1클래스 + 프리셋, 모델별 컬렉션 자동 분리로 차원 충돌 없이 자동 재빌드. (Claude는 임베딩 API 없어 Voyage로 대체)`

- [ ] **Step 5: 커밋**

```bash
git -C "D:/project/second-brain-engine" add docker-compose.yml README.md progress.md
git -C "D:/project/second-brain-engine" commit -m "docs: 임베딩 백엔드 교체 설정/문서 갱신 (SB_OLLAMA_* → SB_EMBED_*)

Progress: skip"
```
(`.env.example`이 추적·편집됐다면 add 목록에 추가. 막혀서 사용자 직접 수정이면 제외.)

---

## Task 5: 전체 회귀 + 수동 E2E

**Files:** 없음 (검증만)

- [ ] **Step 1: ruff 통과**

Run: `/d/project/second-brain-engine/.venv/Scripts/ruff.exe check /d/project/second-brain-engine`
Expected: `All checks passed!`

- [ ] **Step 2: pytest 전체 통과**

Run: `/d/project/second-brain-engine/.venv/Scripts/python.exe -m pytest /d/project/second-brain-engine -q`
Expected: 기존 11 + 신규(embeddings 6 + index 4) = 21 passed (정확한 수는 환경에 따라 ±, 모두 PASS면 OK).

- [ ] **Step 3: 기본값(ollama) 수동 E2E — 회귀 없음 확인**

ollama가 떠 있고 `bge-m3`가 받아진 상태에서, 엔진을 띄워 `/health`를 확인한다.

띄우기(별도 터미널, 사용자 실행 권장):
`! /d/project/second-brain-engine/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`

확인:
`/d/project/second-brain-engine/.venv/Scripts/python.exe -c "import httpx,json; print(json.dumps(httpx.get('http://localhost:8000/health').json(), ensure_ascii=False, indent=2))"`

Expected: `provider: "ollama"`, `model: "bge-m3"`, `collection: "second_brain__ollama_bge_m3"`, `embedding_ok: true`, `documents`는 노트 수만큼.
※ 기존 `second_brain` 컬렉션은 새 이름으로 1회 자동 재빌드된다(노트는 파일로 보존되므로 데이터 손실 없음).

- [ ] **Step 4: (선택) 전환 스모크 — 키가 있으면**

Gemini/OpenAI 키가 있으면 `.env`에 `SB_EMBEDDING_PROVIDER=gemini` + `SB_EMBED_API_KEY=...`를 넣고 엔진을 재시작해 `/health`가 `embedding_ok: true`, `collection: second_brain__gemini_...`로 바뀌는지, `/search`가 결과를 반환하는지 확인한다.
키가 없으면 이 Step은 건너뛴다(Task 1의 팩토리 단위 테스트로 구성 정확성은 이미 검증됨).

---

## 비상 계획 (Gemini OpenAI 호환이 실패할 경우)

Task 5 Step 4에서 Gemini의 OpenAI 호환 엔드포인트(`/v1beta/openai/embeddings`)가 형식 오류를 내면:
- `gemini` 프리셋의 `kind`를 `"gemini"`로 바꾸고, `embeddings.py`에 네이티브 `GeminiEmbedder`를 추가한다.
  네이티브 API: `POST {base_url}/models/{model}:batchEmbedContents?key={api_key}`,
  body `{"requests":[{"model":"models/{model}","content":{"parts":[{"text": t}]}} ...]}`,
  응답 `{"embeddings":[{"values":[...]}, ...]}`. base_url은 `.../v1beta`로 조정.
- 이 경로는 다른 6종 백엔드에 영향이 없다(분기 한 줄 추가).

---

## Self-Review 결과

- **Spec 커버리지**: 프리셋(Task1)·설정통합(Task1)·컬렉션분리(Task2)·자동재빌드(Task2, sync 재사용)·/health 노출(Task3)·문서(Task4)·테스트/회귀(Task1,2,5). 설계 12절 마이그레이션은 Task5 Step3 노트로 커버. 누락 없음.
- **Placeholder**: 모든 코드 step에 완성형 코드 포함. "적절한 처리" 류 없음.
- **타입/이름 일관성**: `_collection_name(base, provider, model)`·`_collection_slug(provider, model)`·`emb.provider`·`brain.collection_name`이 Task 전반에서 동일하게 사용됨. `get_embedder`가 세팅하는 `provider` 속성을 Task2가 `getattr`로 읽고 Task3이 `brain.collection_name`을 노출 — 흐름 일치.
