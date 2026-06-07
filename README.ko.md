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
│   ├── embeddings.py   # 프로바이더 추상화 (Ollama / OpenAI)
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

`tag`·`folder`·`max_distance`는 선택 필터다. 인터랙티브 API 문서(Swagger UI)는
`http://localhost:8000/docs`에서 볼 수 있다.

### 인증 (선택)

`SB_API_KEY`는 기본값이 비어 있다(인증 없음). 값을 설정하면 `/health`를 제외한
모든 라우트에 `X-API-Key` 헤더를 보내야 한다.

## 임베딩 프로바이더 교체

`.env`(또는 환경변수)에서 프로바이더만 바꾸면 된다. 새 프로바이더는
`app/embeddings.py`에 클래스 하나 추가 + `get_embedder`에 분기 한 줄.

```bash
# OpenAI로 전환
SB_EMBEDDING_PROVIDER=openai
SB_OPENAI_API_KEY=sk-...
```

> ⚠️ 프로바이더를 바꾸면 벡터 차원이 달라진다. `chroma_db/` 폴더를 지우고 다시
> 인덱싱할 것: `POST /reindex` (또는 폴더 삭제 후 서버 재시작).

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
