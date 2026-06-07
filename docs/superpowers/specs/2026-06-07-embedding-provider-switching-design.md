# 교체형 임베딩 백엔드 설계

> 작성일: 2026-06-07
> 상태: 설계 확정 대기 (사용자 리뷰 중)

## 1. 목표 (성공 기준)

`.env`에서 **`SB_EMBEDDING_PROVIDER` 값 한 줄 + (클라우드면) API 키 한 줄**만 바꾸고 재시작하면,
다른 임베딩 백엔드로 즉시 교체되고 검색이 정상 동작한다. 모델이 바뀌어 벡터 차원이 달라져도
사람이 재인덱싱을 신경 쓸 필요 없이 엔진이 알아서 새 인덱스를 빌드한다.

지원 백엔드: **로컬**(Ollama, LM Studio, llama.cpp, TEI) + **클라우드**(OpenAI, Voyage, Gemini).

## 2. 배경 / 현재 상태

- 엔진은 검색용 **임베딩 모델**만 사용한다(텍스트 → 벡터). 생성형 LLM(대화 정리)은
  클라이언트(헤르메스)가 담당하므로 이번 작업 범위 밖이다.
- 이미 `app/embeddings.py`에 `EmbeddingProvider`(ABC) + `OllamaEmbedder` + `OpenAIEmbedder`가 있고,
  `SB_EMBEDDING_PROVIDER`로 둘을 고를 수 있다. "교체형"의 토대는 이미 있다.
- 한계: (a) 프로바이더가 2종뿐, (b) 설정 필드가 `ollama_*`/`openai_*`로 흩어져 추가가 번거로움,
  (c) 모델을 바꾸면 벡터 차원이 달라져 기존 Chroma 인덱스와 충돌 → 수동 재인덱싱 필요.

## 3. 인터뷰로 확정한 결정

| # | 결정 | 선택 |
|---|---|---|
| 교체 대상 | 임베딩 모델만 (생성 LLM 아님) | 확정 |
| 지원 백엔드 | 로컬: Ollama·LM Studio·llama.cpp·TEI / 클라우드: OpenAI·Voyage·Gemini | 확정 |
| Claude 자리 | Anthropic은 임베딩 API 없음 → **Voyage AI**로 대체 | 결정1=A |
| 모델 변경 시 | **모델별 컬렉션 자동 분리 + 자동 빌드** | 결정2=A |
| 로컬 OpenAI호환 | lmstudio·llamacpp·tei **셋 다 프리셋** 제공 | 확정 |
| 무중단 전환 | 하지 않음 (재시작 기반, 1인 규모 오버스펙) | 확정 |

## 4. 핵심 통찰

1. **OpenAI 호환이 사실상 표준.** LM Studio·llama.cpp·TEI·OpenAI·Voyage는 전부
   `POST {base_url}/embeddings`, body `{model, input}`, `Authorization: Bearer` 형식을 따른다.
   → 기존 `OpenAIEmbedder` **클래스 하나로 5종 모두 처리**. provider 이름은 **base_url 프리셋만 결정**한다.
2. **`sync()`는 이미 증분 동기화다.** 컬렉션이 비어 있으면 노트 전체를 자동 인덱싱한다
   (`_indexed_state()`가 비면 모든 파일이 `to_index`에 들어감). 서버 시작 시 `lifespan`,
   검색 시 `auto_sync_on_search`가 `sync()`를 호출한다.
   → **컬렉션 이름만 모델별로 분리하면, 자동 재빌드는 기존 코드가 공짜로 해준다.** 새 재인덱싱 코드 불필요.
3. 따라서 실제로 새로 짜는 임베딩 클래스는 **Gemini 하나**뿐일 수 있다(아래 6절 참고).

## 5. 프로바이더 프리셋

`app/embeddings.py`에 프리셋 dict를 둔다. provider 이름 → (종류, 기본 base_url, 기본 모델).

| provider | kind | 기본 base_url | 기본 모델 | API 키 |
|---|---|---|---|---|
| `ollama` | ollama | `http://localhost:11434` | `bge-m3` | — |
| `lmstudio` | openai | `http://localhost:1234/v1` | (사용자 지정) | — |
| `llamacpp` | openai | `http://localhost:8080/v1` | (서버 로드 모델) | — |
| `tei` | openai | `http://localhost:8080/v1` | (서버 로드 모델) | — |
| `openai` | openai | `https://api.openai.com/v1` | `text-embedding-3-small` | ✅ |
| `voyage` | openai | `https://api.voyageai.com/v1` | `voyage-3.5` | ✅ |
| `gemini` | gemini\* | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-embedding-001` | ✅ |

\* Gemini는 OpenAI 호환 엔드포인트(`/v1beta/openai/embeddings`)를 제공하므로 `openai` kind로
처리될 가능성이 높다. 구현 단계에서 실제 검증 후 확정한다(6절).

해석 우선순위: **사용자 설정값(.env) > 프리셋 기본값**. 즉 `SB_EMBED_BASE_URL`/`SB_EMBED_MODEL`이
비어 있으면 프리셋 기본을 쓰고, 채워져 있으면 그 값으로 덮어쓴다.

## 6. 설정 통합 (config.py)

기존 `ollama_base_url`/`ollama_embed_model`/`openai_*` 흩어진 필드를 **공통 필드로 정리**한다.
아직 실연동 전이라 지금이 정리 적기다.

```
SB_EMBEDDING_PROVIDER=ollama   # 프리셋 키 (위 표)
SB_EMBED_MODEL=                # 비우면 provider 기본 모델
SB_EMBED_BASE_URL=             # 비우면 provider 기본 주소 (로컬 포트만 다르면 여기만)
SB_EMBED_API_KEY=              # 클라우드 provider 키 (로컬은 불필요)
```

- 기존 `SB_API_KEY`(엔진 HTTP 인증용)와 **혼동 금지** — 그건 그대로 두고, 임베딩 키는 `SB_EMBED_API_KEY`로 분리.
- **Breaking change**: `SB_OLLAMA_*`/`SB_OPENAI_*` 환경변수는 제거된다. 로컬 `.env`와 `docker-compose.yml`,
  `.env.example`, README의 설정 예시를 새 이름으로 갱신한다.

전환 예시:
- Gemini: `SB_EMBEDDING_PROVIDER=gemini` + `SB_EMBED_API_KEY=AIza...` (2줄)
- LM Studio: `SB_EMBEDDING_PROVIDER=lmstudio` + `SB_EMBED_MODEL=text-embedding-bge-m3` (1줄 추가)
- 기본(현행 유지): `SB_EMBEDDING_PROVIDER=ollama` (그대로)

## 7. 모델별 컬렉션 자동 분리 (index.py)

`BrainIndex.__init__`에서 컬렉션 이름을 **`{collection_name}__{provider}__{model슬러그}`** 로 자동 생성한다.

```
second_brain  →  second_brain__ollama__bge-m3
                 second_brain__gemini__gemini-embedding-001
                 second_brain__openai__text-embedding-3-small
```

- 모델을 바꾸면 다른 컬렉션을 보게 됨 → 비어 있음 → `sync()`가 노트 전체를 자동 빌드.
- 이전 모델 인덱스는 그대로 남아 있어, **되돌리면 재빌드 없이 즉시 복귀**된다.
- 차원이 다른 벡터가 한 컬렉션에 섞이는 사고가 원천 차단된다.

**Chroma 컬렉션 이름 제약 처리**: 영숫자/하이픈/언더스코어만 허용, 시작·끝은 영숫자.
모델명의 `:`·`/`·`.` 등은 슬러그 함수로 제거/치환한다(예: `nomic-embed-text:latest` → `nomic-embed-text_latest`).

## 8. 클래스 구조 (embeddings.py)

- `EmbeddingProvider` (ABC) — 변경 없음. `embed(texts) -> vectors`.
- `OllamaEmbedder` — 변경 없음.
- `OpenAIEmbedder` — 변경 없음(이름 유지). LM Studio·llama.cpp·TEI·OpenAI·Voyage가 공유.
- `GeminiEmbedder` — **신규**. 단, 구현 첫 단계에서 Gemini의 OpenAI 호환 엔드포인트
  (`/v1beta/openai/embeddings`)를 실제 호출해 본다.
  - 정상 동작하면 → `GeminiEmbedder`를 만들지 않고 `gemini` 프리셋의 kind를 `openai`로 둔다(코드 0줄).
  - 형식이 어긋나면 → 네이티브 임베딩 API(`models/{model}:embedContent`, 응답 `embedding.values`)로
    `GeminiEmbedder`를 구현한다.
- `get_embedder(settings)` — 프리셋 dict를 보고 kind에 따라 클래스를 고르며,
  base_url/model은 `settings 값 > 프리셋 기본` 순으로 결정하는 **팩토리**로 재작성.

## 9. API 노출 (main.py)

`/health` 응답에 현재 백엔드를 확인할 수 있도록 필드를 추가한다:
```json
{ "provider": "gemini", "model": "gemini-embedding-001",
  "collection": "second_brain__gemini__gemini-embedding-001", "documents": 42, ... }
```
다른 엔드포인트(`/search`·`/capture`·`/reindex`·`/delete`)는 변경 없음.

## 10. 변경 파일

- `app/embeddings.py` — 프리셋 dict, `get_embedder` 팩토리 재작성, (필요 시) `GeminiEmbedder`
- `app/config.py` — 공통 4필드로 정리 (`embed_model`/`embed_base_url`/`embed_api_key`)
- `app/index.py` — `__init__`에서 컬렉션 이름 자동 생성 + 모델명 슬러그 함수
- `app/main.py` — `/health`에 `model`·`collection` 노출
- `.env.example`·`docker-compose.yml`·`README` — 새 설정 이름 + 백엔드별 전환 예시
- `progress.md` — 임베딩 교체 관련 서술 갱신
- 테스트 — 프리셋 팩토리(각 provider → 올바른 클래스/base_url/model), 컬렉션 이름 슬러그

## 11. 안 하는 것 (YAGNI)

- 무중단 런타임 전환(API로 즉시 스위칭) — 재시작이면 충분.
- Cohere — API 형식이 또 달라 별도 코드 필요, 사용자 미요청.
- Claude 임베딩 — Anthropic이 제공하지 않음(Voyage로 대체).
- 사용자가 고르지 않은 백엔드.

## 12. 호환성 / 마이그레이션

- 기존 `second_brain` 컬렉션(bge-m3로 빌드됨)은 새 이름 규칙에서 버려지고
  `second_brain__ollama__bge-m3`로 **1회 자동 재빌드**된다. 노트는 파일로 보존되므로 데이터 손실 없음.
- `SB_OLLAMA_*`/`SB_OPENAI_*`를 쓰던 로컬 `.env`는 새 이름으로 한 번 갱신 필요(문서에 안내).

## 13. 테스트 계획

- 단위: `get_embedder`가 각 provider에 대해 올바른 클래스 + base_url + model을 만드는지
  (가짜 settings로, 네트워크 호출 없이).
- 단위: 컬렉션 이름 슬러그가 `:`/`/`/`.` 등을 안전 문자로 바꾸는지.
- 통합(기존 패턴): 가짜 임베더로 `BrainIndex`가 새 컬렉션 이름에서도 capture/search/delete 동작.
- 회귀: `ruff` 통과 + `pytest` 전체 통과(현행 11개 유지 또는 증가).

## 14. 성공 기준 (검증 방법)

1. `SB_EMBEDDING_PROVIDER=ollama` 기본값에서 기존과 동일하게 검색 동작(회귀 없음).
2. provider를 `lmstudio`/`gemini` 등으로 바꾸고 재시작 → `/health`가 새 provider·model·collection 표시,
   첫 `/search`에서 자동 재빌드 후 결과 반환.
3. `ruff` + `pytest` 전부 통과.
