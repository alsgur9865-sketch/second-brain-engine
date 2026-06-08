# second-brain-engine

[English](README.md) | **한국어**

![second-brain-engine](assets/hero.png)

범용 **세컨드 브레인 엔진** — **에이전트가 (MCP로) 쓰고, 사람이 그래프로 읽는다.**
마크다운 노트 폴더를 인덱싱해 작은 HTTP API로 제공한다. 지식을 저장하고, 의미로
회상하고, 스스로 정리되게 하고, 브라우저에서 Obsidian식 그래프로 탐색한다.

- **에이전트 메모리 (MCP)** — `remember` / `recall` 도구로 Claude Code(또는 Cursor·
  Cline·Windsurf 등 어떤 MCP 클라이언트든)가 작업 기억을 저장·회상한다. 엔진이 노트+
  인덱스의 단일 소유자이고, MCP 서버는 얇은 프록시다.
- **그래프 뷰 (브라우저)** — 에이전트가 뭘 기억했고 뭐가 뭐랑 엮였나를 본다:
  `[[위키링크]]`, 의미 유사, 노드 유형(의미/통찰/절차), 그리고 **관계 엣지**(지지/반박/
  확장). 노드를 클릭하면 본문이 열린다.
- **의미검색** — 키워드가 아니라 의미로. 결과에 `[[위키링크]]` 이웃이 따라와, 한 단편이
  아니라 *연결된 덩어리*로 회상된다.
- **질문(RAG)** — `POST /ask`가 노트를 검색해 로컬 LLM이 **그 노트만 근거로** 답한다.
  엄격 모드는 환각 대신 "기억에 없습니다"라고 답한다.
- **자동정리** — 임베딩으로 중복 노트를 탐지하고 병합한다(직접 작성 또는 로컬 LLM 요약).
  병합 시 끊기는 `[[링크]]`는 자동 보정된다.
- **임베딩 교체형** — 7종(Ollama·LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini), 설정
  한 줄로 전환, 모델별 인덱스 자동 재빌드.
- **증분 인덱싱** — 변경된 노트만 다시 임베딩, 클라이언트는 파일만 쓰면 된다.

**스택**: Python · FastAPI · Chroma(임베디드 벡터DB) · 로컬 Ollama LLM(정리·분류·답변
— 추가 인프라 0).

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

이제 할 수 있는 것:

```bash
# 1) 의미로 검색 (키워드 아님)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "환불 며칠 안에 되나요?", "k": 3}'

# 2) 질문 — 엔진이 내 노트만 근거로 답한다
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "환불 기간이 며칠이야?"}'
```

…그리고 브라우저로 **http://localhost:8000** 을 열면 **그래프 뷰**가 보인다 — 유형별
색 노드, 위키링크/유사/관계 엣지, 노드 상세 패널과 질문 박스.

Ollama가 없다면 [임베딩 프로바이더 교체](#임베딩-프로바이더-교체)로 OpenAI를 써도 된다.

## 동작 방식

```
[ 클라이언트 (교체·확장 가능) ]
  · 에이전트 메모리 (MCP: remember/recall, cleanup_*)   ← 주력, Claude Code로 dogfooding
  · 사람 (브라우저 그래프 뷰)                            ← 같은 뇌, 다른 창
  · (선택) HTTP 직접 클라이언트 / 봇 / CLI
            │  MCP(stdio) → HTTP   /   HTTP(JSON)
            ▼
[ 엔진 코어: second-brain-engine ]
  /health · /search · /ask · /capture · /graph · / (그래프뷰) · /note
  /cleanup/candidates · /cleanup/merge · /classify · /classify-relations
            │
   ┌────────┼──────────────────────┬────────────────────────┐
노트 폴더 (.md)             Chroma 벡터DB              로컬 LLM (Ollama gemma)
읽기 / 쓰기                 임베딩 인덱스 + 그래프       병합 · 분류 · 답변
```

엔진은 클라이언트 비의존 — HTTP/JSON만 쓴다. 주력 클라이언트는 **MCP 기반 에이전트
메모리**(Claude Code로 dogfooding)이고, **사람은 같은 뇌를 브라우저에서 그래프로** 본다.
HTTP를 쓰는 무엇이든 클라이언트가 될 수 있다.

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET  | `/health` | 상태 + 임베딩 백엔드 정상 여부 + 인덱싱된 문서 수 |
| GET  | `/` | 그래프 뷰 (단일 페이지 브라우저 UI) |
| GET  | `/graph` | 노드 + 엣지 (위키링크 · 의미유사 · 관계) |
| GET  | `/note?path=` | 노트 한 개의 본문 + 메타 (상세 패널용) |
| POST | `/search` | 의미검색 (+ `linked` 위키링크 이웃) |
| POST | `/ask` | RAG: 노트 검색 → 로컬 LLM이 **그 노트만 근거로** 답변 (엄격) |
| POST | `/capture` | 정리된 노트 저장 + 즉시 인덱싱 |
| POST | `/delete` | `{"path": "inbox/note.md"}` → 노트 + 인덱스 제거 |
| POST | `/reindex` | 노트 변경분 강제 재동기화 |
| GET  | `/cleanup/candidates` | 중복 후보 쌍 (임베딩 유사도) |
| POST | `/cleanup/merge` | 중복 병합 (직접 작성 또는 로컬 LLM 요약) + `[[링크]]` 보정 |
| POST | `/classify` | 노트를 유형(의미/통찰/절차)으로 분류 (노드 색) |
| POST | `/classify-relations` | 유사 쌍을 관계(지지/반박/확장)로 분류 (관계 엣지) |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "온보딩 관련 노트", "k": 5, "tag": "회의", "folder": "notes", "max_distance": 1.0}'
```

`tag`·`folder`·`max_distance`는 선택 필터다. `include_links: true`(기본)면 각 결과에
`linked`(그 노트가 `[[위키링크]]`로 가리키는 이웃)가 함께 온다. 인터랙티브 API 문서
(Swagger UI)는 `http://localhost:8000/docs`.

### 인증 (선택)

`SB_API_KEY`는 기본값이 비어 있다(인증 없음). 설정하면 읽기 전용
(`/health`·`/graph`·`/note`·`/cleanup/candidates`)을 제외한 모든 라우트에 `X-API-Key`
헤더를 보내야 한다.

## 에이전트 메모리 (MCP)

첫 번째 클라이언트는 엔진 HTTP를 프록시하는 MCP 서버(`mcp_server.py`, stdio)다. Claude
Code 같은 에이전트가 자기 작업 기억을 직접 쌓고 꺼낸다:

| MCP 도구 | 엔진 호출 | 용도 |
|---|---|---|
| `remember` | `POST /capture` | 대화에서 알게 된 사실·결정·할 일 저장 |
| `recall` | `POST /search` | 의미로 회상 (+ 위키링크 이웃) |
| `cleanup_candidates` | `GET /cleanup/candidates` | 병합 전 중복 기억 찾기 |
| `cleanup_merge` | `POST /cleanup/merge` | 중복을 하나로 병합 |

`.mcp.json`(`.mcp.json.example` 참고) 또는 `claude mcp add`로 등록하고, 엔진을
`localhost:8000`에 띄워 둔다. 에이전트가 쓰면, 사람은 그 결과를 그래프에서 본다.

## 그래프 뷰

엔진이 떠 있는 동안 브라우저로 **http://localhost:8000** 을 연다:

- **노드** = 노트, 유형별 색(의미/통찰/절차, 회색 = 미분류)
- **엣지**: 초록 = `[[위키링크]]`, 회색 = 의미 유사, 빨강 = 정리 후보(중복), 그리고
  **라벨 관계 엣지** — 청록 *지지*, 주황 *반박*, 보라 *확장*(`POST /classify-relations`로 채움)
- **노드 클릭** → 상세 패널(제목·유형·태그·본문·연결 노트). 연결 칩이나 `/ask` 근거를
  클릭하면 그 노드로 점프
- **질문 박스**(좌하단)가 `/ask`를 내 뇌에 던진다

## Docker로 실행

```bash
docker compose up -d
```

> ⚠️ 컨테이너가 호스트의 Ollama에 접근하려면 호스트에서 Ollama를 외부 바인딩으로 띄울 것
> (`OLLAMA_HOST=0.0.0.0`). 안 그러면 `host.docker.internal:11434`에 못 붙는다.

## 임베딩 프로바이더 교체

`SB_EMBEDDING_PROVIDER` 한 줄(클라우드면 `SB_EMBED_API_KEY` 추가)만 바꾸고 재시작하면
된다. OpenAI 호환 서버(LM Studio·llama.cpp·TEI·OpenAI·Voyage·Gemini)는 한 클라이언트를
공유하고, provider 이름은 base_url 프리셋만 고른다.

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

모델을 바꾸면 벡터 차원이 달라지지만, 인덱스는 **모델별로 따로 보관**되며
(`second_brain__<provider>_<model>`) 다음 검색에서 엔진이 새 인덱스를 자동 재빌드한다.
이전 인덱스는 남아 있어 되돌리면 즉시 복귀된다.

> 참고: Anthropic은 임베딩 API가 없으므로 `voyage`(권장 파트너)를 쓴다. 생성형 LLM
> (정리·분류·답변)은 기본이 로컬 Ollama `gemma`이고 `SB_LLM_*`로 교체한다.

## 구조

```
second-brain-engine/
├── app/
│   ├── config.py        # 설정(SB_ 환경변수) — 임베딩/LLM 프로바이더, 옵션 API 키
│   ├── embeddings.py    # 임베딩 프로바이더 프리셋 (Ollama + OpenAI 호환)
│   ├── llm.py           # 생성형 LLM (정리 요약 · 노드 유형 · 관계 · 답변)
│   ├── cleanup.py       # 중복 탐지 (임베딩, LLM 0)
│   ├── index.py         # Chroma 인덱싱 + 증분 동기화 + 검색 + capture/delete + relink
│   ├── graph.py         # 노드/엣지 (위키링크 · 유사 · 관계)
│   ├── main.py          # FastAPI 라우트
│   └── static/graph.html# 브라우저 그래프 뷰 (force-graph, 단일 페이지)
├── mcp_server.py        # MCP 서버 (remember/recall/cleanup_*) → 엔진 HTTP 프록시
├── examples/vault/      # 빠른 시작용 번들 샘플 노트
├── tests/               # 순수 함수 + BrainIndex(가짜 임베더) + cleanup/relink/classify
├── Dockerfile · docker-compose.yml · requirements.txt
```

## 개발

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
