<!-- progress-sync: 9a81bb187dbe662520e28994d3f337ed020a2eeb -->
# Progress — 세컨드 브레인 엔진 (범용)

> 최종 업데이트: 2026-06-08

## 한 줄 요약

**에이전트가 쓰고(MCP) 사람이 그래프로 보는** 범용 세컨드 브레인 엔진.
엔진은 HTTP API만 노출하는 **범용 코어** — 폴더만 바꾸면 새 뇌(노트폴더+인덱스 한 쌍).
**이번 세션(06-08): 에이전트 메모리(MCP) + 의미 그래프 뷰 MVP 구현·검증 완료. MCP 실연결만 남음.**

## 정체성: 범용 엔진 + 교체 가능한 클라이언트

- **엔진은 누구 전용도 아니다.** 받는 건 순수 JSON, 누가 호출하든 신경 안 쓰는 HTTP API.
- **첫 주력 클라이언트 = 에이전트 메모리(MCP, `remember`/`recall`)** — Claude Code로 dogfooding.
  MCP는 표준이라 **클로드코드 전용이 아님**(Cursor·Cline·Windsurf 등도, MCP 안 쓰면 HTTP 직접도).
- **사람은 그래프 뷰**로 "에이전트가 뭘 기억했고 뭐가 뭐랑 엮였나"를 본다(같은 뇌, 다른 창).
- 헤르메스(디스코드 봇)는 "또 다른 가능 클라이언트"로 남음(우선순위 낮아짐).

## 현재 상태

| 레포 | 공개 | URL |
|---|---|---|
| second-brain-engine | 🌐 public (MIT) | https://github.com/alsgur9865-sketch/second-brain-engine |
| my-second-brain | 🔒 private | https://github.com/alsgur9865-sketch/my-second-brain |

- 이번 세션 신규 코드 **미커밋** (아래 "남은 작업" 참고).

## 진행 기록

- **2026-06-08 에이전트 메모리 + 그래프 뷰 MVP (안 A)**:
  - `app/graph.py`: 노드(노트)/엣지 추출 — ①`[[위키링크]]`(방향) ②임베딩 의미유사(노트 평균벡터 코사인 top-k). **LLM 불필요**, 인덱스의 메타+벡터만으로 계산.
  - `app/static/graph.html` + `GET /` + `GET /graph`: force-graph 단일 페이지(CDN, 빌드툴 0). 위키링크=초록 입자, 의미유사=회색.
  - `mcp_server.py`: `remember`/`recall` MCP 툴(엔진 HTTP 프록시, stdio transport). 엔진이 상태 단일소유, MCP는 얇은 껍데기.
  - `.mcp.json`(Claude Code 등록) · `requirements.txt`에 `mcp>=1.12`.
  - **검증**: ruff 통과 / pytest **23 passed**(기존 유지) / `/graph` 노드·엣지 확인 / MCP `recall` 엔진 호출 200 확인 / 브라우저 렌더 확인(사용자).
  - **dogfooding 뇌**: `D:/project/brains/agent-memory`(+`-db`). 빈 뇌→첫 기억 2개 저장, 의미유사 자동연결(0.605) 확인. **개인 옵시디언 vault(Karpathy 위키)와 분리** — 별개 뇌, 지금 스코프 아님.
- **2026-06-07 교체형 임베딩 백엔드**: provider 한 줄로 7종(ollama/lmstudio/llamacpp/tei/openai/voyage/gemini) 교체. 모델별 컬렉션 자동 분리·재빌드. 설정 `SB_EMBED_*`.
- **2026-06-07 그래프 검색(연결 회상)**: 검색 결과에 `[[위키링크]]` 1-hop 이웃을 `linked`로 첨부.
- **2026-06-07 온보딩 팩 / 보안·기능 강화 / 범용 재포지셔닝**: 샘플 vault·Quickstart, 경로탈출 차단·옵션 API키·`/health` 헬스체크·태그/날짜 필터·`/delete`, MIT·영한 README.

## 아키텍처

```
[ 클라이언트 (교체·확장 가능) ]
  · 에이전트 메모리 (MCP: remember/recall)  ← 현 주력, dogfooding
  · 사람 (그래프 뷰, 브라우저)               ← 같은 뇌를 "본다"
  · (가능) 헤르메스 봇 / CLI / 다른 에이전트(HTTP 직접)
            |  MCP(stdio) → HTTP  /  HTTP(JSON)
            v
[ 엔진 코어: second-brain-engine (범용) ]
  /health · /search · /capture · /reindex · /delete · /graph · /(그래프뷰)
            |
   +--------+--------------------+
   |                             |
notes 폴더(.md)              Chroma 벡터DB
저장/읽기                    임베딩 인덱스 + 그래프 계산
```

- **엔진**: Python FastAPI + Chroma + 교체형 임베딩(기본 ollama `bge-m3`).
- **그래프**: `/graph`가 노드/엣지(위키링크+의미유사)를 JSON으로, `/`가 force-graph 화면.
- **MCP**: `mcp_server.py`(별도 프로세스, stdio) → 엔진 HTTP 프록시. 엔진이 떠 있어야 작동.
- **뇌 = 노트폴더 + 인덱스 한 쌍.** `SB_NOTES_PATH`/`SB_CHROMA_PATH`로 교체 → 여러 뇌. 단 같은 인덱스를 두 프로세스가 직접 열면 SQLite 락(공유는 엔진 하나에 HTTP로 다 붙기).

## 주요 설계 결정

- **방향(06-08 office-hours)**: ①엔진 범용 유지 ②첫 클라이언트=에이전트 메모리(MCP) ③사람용 그래프 뷰 얹기. 통째 갈아타기(Reor/Khoj) 비추 — 엔진 살리고 **부품만**. **Graphiti 안 씀**(그래프DB 운영 부담, Chroma 단순함 유지).
- **Karpathy LLM Wiki 보완 관계**: 걔는 쓰기/유지(`/ingest`·`/process-inbox`·`/lint`), 우리는 **의미회상+의미그래프**를 얹음. 옵시디언 기본 그래프(링크만) 대비 차별 = 의미유사 엣지 + MCP 회상.
- 임베딩: 교체형 7종. 벡터DB: Chroma(임베디드). 레포 분리: 엔진(공개)+노트(비공개).
- 보안: 경로탈출 차단 + 옵션 API 키.

## 해결한 문제 (디버깅 기록)

- **bge-m3 500 NaN**: ollama `0.21.0`+bge-m3가 일부 청크 NaN → `0.30.6`로 해결.
- **코드블록 청킹 오인**: ``` 안 `#`를 헤딩 분할 → `in_code` 토글.
- **경로 안전 함정**: `_safe_rel`이 leading `/` strip 전 절대경로 검사하도록.
- **(이번) Bash 도구 함정**: cwd가 매 호출 `/d`로 reset → 절대경로 필수, `cd`를 command에 명시. (메모리 `shell-and-verify-commands` 참고)

## 검증 상태

- ruff: All passed / pytest: **23 passed**(순수함수 + 가짜임베더 BrainIndex + 임베딩 프리셋/컬렉션 분리). graph.py·mcp_server.py는 자동검증(린트/통합 호출)으로 확인, 전용 단위테스트는 미작성.
- `/health` E2E: ollama `bge-m3` 실호출 OK. `/graph`·MCP `recall`·브라우저 렌더 실측 OK.

## 남은 작업 (다음 세션)

1. **MCP 실연결** (사용자 액션 — 재시작 필요):
   - 엔진을 **본인 터미널**에서 띄움(Claude Code와 독립해야 재시작에도 살아있음):
     `SB_NOTES_PATH=D:\project\brains\agent-memory  SB_CHROMA_PATH=D:\project\brains\agent-memory-db  uvicorn app.main:app --port 8000`
   - Claude Code 재시작 → `.mcp.json` 신뢰 → `second-brain` MCP 등록 → `/mcp`로 확인
   - "기억해둬"/"찾아줘" 테스트
2. **쌓기 자동화** (선택): CLAUDE.md 규칙(느슨) 또는 Claude Code Hook(세션종료 시 강제).
3. **다음 단계 = 안 B(데모급 그래프)**: ①노드 유형 분류(의미/통찰/절차…, LLM) ②의미 관계 엣지(지지/반박/확장, LLM) ③자동 정리(병합/요약) ④질문→답(RAG).
4. **커밋**: 이번 변경 미커밋. `.mcp.json`은 PC 절대경로라 공개 레포엔 제외 권장(`.gitignore` 또는 `.example`).
5. (이전) 헤르메스 실연동 — 또 다른 클라이언트로 여전히 가능.

## 로컬 환경 메모

- 작업 루트: `D:\project\` (git 미추적).
- **에이전트 뇌**: `D:\project\brains\agent-memory`(노트) + `agent-memory-db`(인덱스). git 미추적.
- venv: `D:\project\second-brain-engine\.venv` (ruff/pytest/uvicorn/mcp).
- 엔진 실행: `SB_NOTES_PATH=<뇌> [SB_CHROMA_PATH=<db>] uvicorn app.main:app --port 8000` (cwd=엔진폴더 또는 `--app-dir`).
- 검증용 임시파일(`_seed.py` 등)은 실행 후 삭제, `_`·`.gitignore`로 배포 제외.
- 임베딩 모델: `ollama pull bge-m3`(기본), `nomic-embed-text`. 헤르메스 LLM: `gemma4:e4b`.
