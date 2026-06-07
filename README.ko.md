# second-brain-engine

[English](README.md) | **한국어**

![second-brain-engine](assets/hero.png)

대화를 자동 기억하고 의미검색으로 회상하는 **범용 세컨드 브레인 엔진**.
마크다운 노트 폴더를 인덱싱해 작은 HTTP API로 제공한다 — 디스코드 봇, CLI,
웹 대시보드 등 **어떤 클라이언트든** 이 위에서 지식을 저장·검색할 수 있다.

- **스택**: Python · FastAPI · Chroma(임베디드 벡터DB)
- **임베딩 교체형**: 기본 로컬 Ollama, 설정 한 줄로 OpenAI 등으로 전환
- **증분 인덱싱**: 변경된 노트만 다시 임베딩 — 클라이언트는 파일만 쓰면 된다
- **자동 수집**: `POST /capture`로 정리된 노트를 저장 + 즉시 인덱싱 (대화→자동기억)
- **연결 회상**: 검색 결과에 `[[위키링크]]`로 이어진 이웃 노트가 따라와, 한 노트가 아니라 *연결된 덩어리*로 회상 (Obsidian식 그래프)

## 빠른 시작 (5분)

**번들 샘플 vault**로 본인 노트 없이 바로 시험해 본다:

```bash
git clone https://github.com/alsgur9865-sketch/second-brain-engine
cd second-brain-engine
python -m venv .venv && .venv\Scripts\activate    # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull bge-m3                                  # 임베딩 모델 1회 다운로드 (~2 GB)
```

엔진을 샘플 vault로 가리켜 띄운다:

```bash
# bash / macOS / Linux
SB_NOTES_PATH=examples/vault uvicorn app.main:app --port 8000
# Windows PowerShell
$env:SB_NOTES_PATH="examples/vault"; uvicorn app.main:app --port 8000
```

다른 터미널에서 *의미로* 검색한다 (키워드 아님):

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "환불 며칠 안에 되나요?", "k": 3}'
```

키워드가 거의 안 맞아도 환불 정책 노트가 잡힌다.
Ollama가 없다면 [임베딩 프로바이더 교체](#임베딩-프로바이더-교체)로 OpenAI를 써도 된다.

## 동작 방식

```
[ 클라이언트 (교체·확장 가능) ]
  · 헤르메스 스킬 (첫 통합) — 대화를 LLM으로 정리
  · (향후) CLI / 웹 대시보드 / 다른 봇
            │  HTTP (JSON)
            ▼
[ 엔진 코어: second-brain-engine ]
  /health · /search · /capture · /reindex · /delete
            │
   ┌────────┴───────────────┐
노트 폴더 (.md)          Chroma 벡터DB
읽기 / 쓰기              임베딩 인덱스
```

엔진은 클라이언트 비의존 — HTTP/JSON만 쓴다. 헤르메스(디스코드 봇)가 현재
첫 번째·주력 클라이언트지만, 엔진 코드는 헤르메스에 전혀 의존하지 않는다.

## 구조

```
second-brain-engine/
├── app/
│   ├── config.py       # 설정(SB_ 환경변수) — 임베딩 프로바이더, 옵션 API 키
│   ├── embeddings.py   # 프로바이더 프리셋 (Ollama + OpenAI 호환)
│   ├── index.py        # Chroma 인덱싱 + 증분 동기화 + 검색 + capture/delete
│   └── main.py         # FastAPI 라우트 (/health, /search, /capture, /reindex, /delete)
├── tests/              # 청킹 / 프론트매터 / 경로안전 + BrainIndex 테스트
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 사전 준비 (로컬 Ollama 임베딩)

```bash
ollama pull bge-m3        # 기본 모델 — 다국어·한국어 강력
```

## 실행 — 방법 A: 로컬 Python (가장 빠른 확인)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux는: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # 선택 — 기본값으로 바로 실행됨 (macOS/Linux는 cp)
uvicorn app.main:app --port 8000
```

모든 설정은 기본값이 있어(`app/config.py`) 바로 실행된다. 값을 바꾸려면
`.env.example`을 `.env`로 복사해 수정하거나, `SB_` 접두사 환경변수를 설정하면 된다.

## 실행 — 방법 B: Docker

```bash
docker compose up -d
```

> ⚠️ Docker 컨테이너에서 호스트의 Ollama에 접근하려면 호스트에서 Ollama가
> 외부 바인딩돼야 한다: `OLLAMA_HOST=0.0.0.0`로 띄울 것. (안 그러면 컨테이너가
> `host.docker.internal:11434`에 못 붙음)

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 상태 + 임베딩 백엔드 정상 여부 + 인덱싱된 문서 수 |
| POST | `/search` | 의미검색 (아래 본문 참고) |
| POST | `/capture` | 정리된 노트 저장 + 즉시 인덱싱 (대화→자동기억) |
| POST | `/reindex` | 노트 변경분 강제 재동기화 |
| POST | `/delete` | `{"path": "inbox/note.md"}` → 노트 파일 + 인덱스 제거 |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "온보딩 관련 노트", "k": 5, "tag": "회의", "folder": "notes", "max_distance": 1.0}'
```

`tag`·`folder`·`max_distance`는 선택 필터다. `include_links: true`(기본)면 각 결과에
`linked`가 함께 온다 — 그 노트가 `[[위키링크]]`로 가리키는 이웃 노트들이라, 단편이 아니라
연결된 덩어리로 회상된다. 인터랙티브 API 문서(Swagger UI)는 `http://localhost:8000/docs`에서 볼 수 있다.

### 인증 (선택)

`SB_API_KEY`는 기본값이 비어 있다(인증 없음). 값을 설정하면 `/health`를 제외한
모든 라우트에 `X-API-Key` 헤더를 보내야 한다.

## 임베딩 프로바이더 교체

`.env`에서 `SB_EMBEDDING_PROVIDER` 한 줄(클라우드면 `SB_EMBED_API_KEY` 추가)만 바꾸고
재시작하면 된다. OpenAI 호환 서버(LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini)는
한 클라이언트를 공유하고, provider 이름은 base_url 프리셋만 고른다.

| provider | 종류 | 기본 모델 | 키 |
|---|---|---|---|
| `ollama` (기본) | 로컬 | `bge-m3` | — |
| `lmstudio` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `llamacpp` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `tei` | 로컬(OpenAI 호환) | 직접 지정 | — |
| `openai` | 클라우드 | `text-embedding-3-small` | ✅ |
| `voyage` | 클라우드 | `voyage-3.5` | ✅ |
| `gemini` | 클라우드 | `gemini-embedding-001` | ✅ |

```bash
# Gemini로 전환
SB_EMBEDDING_PROVIDER=gemini
SB_EMBED_API_KEY=AIza...

# 또는 로컬 LM Studio 서버
SB_EMBEDDING_PROVIDER=lmstudio
SB_EMBED_MODEL=text-embedding-bge-m3   # 로드한 모델명
```

필요하면 프리셋을 덮어쓴다: `SB_EMBED_BASE_URL`(예: 커스텀 포트), `SB_EMBED_MODEL`.
모델을 바꾸면 벡터 차원이 달라지지만, 인덱스는 **모델별로 따로 보관**되며
(`second_brain__<provider>_<model>`) 다음 검색에서 엔진이 새 인덱스를 자동 재빌드한다.
이전 인덱스는 남아 있어 되돌리면 즉시 복귀된다.

> 참고: Anthropic은 임베딩 API가 없으므로 Claude 대신 `voyage`(권장 파트너)를 쓴다.

## 개발

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## 클라이언트 & 연동

엔진은 범용 — HTTP만 쓰면 어떤 클라이언트든 사용할 수 있다. 첫 통합은
**헤르메스**(디스코드 봇)다: 별도 노트 레포(`my-second-brain`)를 로컬에 clone해
직접 읽고/쓰며, 의미검색이 필요할 때만 `/search`를 호출한다. 연동 스킬은
`hermes-skill/second-brain/SKILL.md` 참고.

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
