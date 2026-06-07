# second-brain-engine

![second-brain-engine](assets/hero.png)

헤르메스 에이전트용 **세컨드 브레인 의미검색 엔진**. 마크다운 노트 레포(`my-second-brain`)를 인덱싱해 의미 기반 검색 API를 제공한다.

- **스택**: Python · FastAPI · Chroma(임베디드 벡터DB)
- **임베딩**: 교체형 — 기본 로컬 Ollama, 설정 한 줄로 OpenAI 등으로 전환
- **증분 인덱싱**: 노트 변경분만 자동 재인덱싱. 헤르메스는 파일만 쓰면 된다.

## 구조

```
second-brain-engine/
├── app/
│   ├── config.py       # 설정(SB_ 환경변수) — 임베딩 프로바이더 선택
│   ├── embeddings.py   # 프로바이더 추상화 (Ollama / OpenAI)
│   ├── index.py        # Chroma 인덱싱 + 증분 동기화 + 의미검색
│   └── main.py         # FastAPI 라우트 (/search, /reindex, /health)
├── tests/              # 청킹 단위 테스트
├── docker-compose.yml  # 로컬 한 방 실행
└── requirements.txt
```

## 사전 준비 (로컬 Ollama 임베딩)

```bash
ollama pull nomic-embed-text
```

## 실행 — 방법 A: 로컬 Python (가장 빠른 확인)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 필요 시 값 수정
uvicorn app.main:app --port 8000
```

## 실행 — 방법 B: Docker

```bash
docker compose up -d
```

> ⚠️ Docker 컨테이너에서 호스트의 Ollama에 접근하려면 호스트에서 Ollama가 외부 바인딩돼야 한다:
> `OLLAMA_HOST=0.0.0.0` 로 Ollama를 띄울 것. (안 그러면 컨테이너가 `host.docker.internal:11434`에 못 붙음)

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 상태 + 인덱싱된 문서 수 |
| POST | `/search` | `{"query": "...", "k": 5}` → 의미검색 결과 |
| POST | `/reindex` | 노트 변경분 강제 재동기화 |
| POST | `/capture` | 정리된 노트 저장 + 즉시 인덱싱 (대화→자동기억) |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"온보딩 관련 노트\", \"k\": 5}"
```

## 임베딩 프로바이더 교체

`.env`에서 프로바이더만 바꾸면 된다. 새 프로바이더는 `app/embeddings.py`에 클래스 하나 추가 + `get_embedder`에 분기 한 줄.

```bash
# OpenAI로 전환
SB_EMBEDDING_PROVIDER=openai
SB_OPENAI_API_KEY=sk-...
```

> ⚠️ 프로바이더를 바꾸면 벡터 차원이 달라진다. `chroma_db/` 폴더를 지우고 다시 인덱싱할 것:
> `POST /reindex` (또는 폴더 삭제 후 서버 재시작).

## 개발

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## 헤르메스 연동

별도 노트 레포 `my-second-brain`을 헤르메스가 로컬 clone해서 직접 읽고/쓴다. 의미검색이 필요할 때만 이 엔진의 `/search`를 호출한다. 연동 스킬은 `my-second-brain` 레포 및 헤르메스 스킬 문서를 참고.
