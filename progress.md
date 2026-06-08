<!-- progress-sync: ae9517b6535e9f6138178f2fdc54039a9cb9e28d -->
# Progress — 세컨드 브레인 엔진 (범용)

> 최종 업데이트: 2026-06-08

## 한 줄 요약

**에이전트가 쓰고(MCP) 사람이 그래프로 보는** 범용 세컨드 브레인 엔진.
엔진은 HTTP API만 노출하는 **범용 코어** — 폴더만 바꾸면 새 뇌(노트폴더+인덱스 한 쌍).
**이번 세션(06-08 후반): ①에이전트 자동 쌓기(능동 규칙 + Stop hook) ②자동정리 풀스택(중복 탐지 + gemma 병합)을 구현하고 dogfooding·E2E로 실검증 완료.**

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

- 이번 세션 코드 커밋 완료(자동 쌓기 / 자동정리 2커밋).
- **엔진 기동 중**: `localhost:8000`, `agent-memory` 뇌(노트 4개). MCP recall/remember 실작동 확인.

## 진행 기록

- **2026-06-08 (5) 노드 유형 분류 (안 B 첫 조각)**: frontmatter에 type 없는 노트만 로컬 gemma로 의미/통찰/절차로 분류해 frontmatter에 써넣고(이미 있으면 skip=캐싱) 그래프 노드를 유형별 색으로 칠한다 — `llm.py classify_note`+`index.py classify_unclassified`+`POST /classify`+`graph.py/html`(folder색→type색·범례). **프롬프트 함정**: 첫 시도엔 전체 text+약한 프롬프트로 gemma가 5개 다 '절차'로 쏠림 → 본문만(`_strip_frontmatter`)+유형 정의 또렷한 프롬프트로 통찰/절차/의미 정확 구분(qwen도 동일 → 모델 아닌 프롬프트 문제). ruff / pytest **32 passed**(classify 3) + 실엔진 E2E(통찰3/절차2, 재호출 skip 5). (커밋 ae9517b, 로컬)
- **2026-06-08 (4) 병합 시 위키링크 보정 + 재시작 후 검증**: ①재시작 후 cleanup MCP 도구·Stop hook(3분기)·`cleanup_merge` E2E 모두 실작동 확인(남은작업 1 해소). ②`cleanup_merge`가 원본을 삭제할 때 끊기던 `[[링크]]`를 새 노트 제목으로 자동 치환 — `index.py`에 `collect_link_names()`(삭제 전 stem+title 수집)+`relink()`(전체 스캔·단순 치환·재인덱싱), merge가 add→collect→delete→relink로 호출하고 응답에 `relinked` 추가. 별칭 버림·항상 자동. ruff / pytest **29 passed**(relink 2) + 실엔진 E2E(B·C 병합 시 A의 `[[..]]` 치환) 확인. (커밋 b0316fb, 로컬)
- **2026-06-08 (3) 자동정리 풀스택 + 에이전트 자동 쌓기**:
  - **자동 쌓기(능동+리마인더)**: 프로젝트 `CLAUDE.md` 능동 규칙(확정 시 `remember`/작업 시작 시 `recall`, folder=decisions/bugs/todos, 저장 전 중복확인) + `.claude/hooks/remind_memory.py` **Stop hook**(한 세션에 remember 0회+사용자 메시지 3개↑면 1회 환기, `stop_hook_active`로 무한루프 방지). hook 등록은 git 제외되는 `settings.local.json`.
  - **자동정리(탐지+병합)**: `app/cleanup.py`(임베딩 중복 탐지, **LLM 0**) + `app/llm.py`(로컬 ollama gemma 병합·요약) + `GET /cleanup/candidates`·`POST /cleanup/merge` + MCP `cleanup_candidates`/`cleanup_merge` + 그래프 **빨간 후보선**. merge는 content 유무로 **에이전트 작성 / gemma 자동요약** 분기.
  - **검증**: ruff / pytest **27 passed**(신규 cleanup 4). **dogfooding 실검증**: recall(0.55/0.33)·remember·`[[위키링크]]`·그래프 실작동. **cleanup E2E**: 중복 2개→탐지(0.939)→gemma 병합("엔진 실행 및 설정 방법")→5노드 줄어 4노드 확인.
  - **재시작 후 활성**: cleanup MCP 도구 + Stop hook(이 세션의 MCP 서버·설정은 구버전이라 다음 재시작부터).
- **2026-06-08 (2) 에이전트 메모리 + 그래프 뷰 MVP (안 A)**:
  - `app/graph.py`: 노드(노트)/엣지 추출 — ①`[[위키링크]]`(방향) ②임베딩 의미유사(노트 평균벡터 코사인 top-k). LLM 불필요.
  - `app/static/graph.html` + `GET /` + `GET /graph`: force-graph 단일 페이지(CDN). `mcp_server.py`: `remember`/`recall` MCP 툴(엔진 HTTP 프록시, stdio).
  - **dogfooding 뇌**: `D:/project/brains/agent-memory`(+`-db`). 개인 옵시디언 vault와 분리.
- **2026-06-07 교체형 임베딩 백엔드**: provider 한 줄로 7종(ollama/lmstudio/llamacpp/tei/openai/voyage/gemini) 교체. 모델별 컬렉션 자동 분리·재빌드. 설정 `SB_EMBED_*`.
- **2026-06-07 그래프 검색(연결 회상)**: 검색 결과에 `[[위키링크]]` 1-hop 이웃을 `linked`로 첨부.
- **2026-06-07 온보딩 팩 / 보안·기능 강화 / 범용 재포지셔닝**: 샘플 vault·Quickstart, 경로탈출 차단·옵션 API키·`/health`·태그/날짜 필터·`/delete`, MIT·영한 README.

## 아키텍처

```
[ 클라이언트 (교체·확장 가능) ]
  · 에이전트 메모리 (MCP: remember/recall, cleanup_candidates/merge)  ← 현 주력, dogfooding
  · 사람 (그래프 뷰, 브라우저 — 위키링크/의미유사/중복후보)            ← 같은 뇌를 "본다"
  · (가능) 헤르메스 봇 / CLI / 다른 에이전트(HTTP 직접)
            |  MCP(stdio) → HTTP  /  HTTP(JSON)
            v
[ 엔진 코어: second-brain-engine (범용) ]
  /health · /search · /capture · /reindex · /delete · /graph · /(그래프뷰)
  /cleanup/candidates(중복 탐지) · /cleanup/merge(병합)
            |
   +--------+--------------------+----------------------+
   |                             |                      |
notes 폴더(.md)             Chroma 벡터DB         로컬 LLM(ollama gemma)
저장/읽기                   임베딩 인덱스+그래프    병합·요약(cleanup 전용)
```

- **엔진**: Python FastAPI + Chroma + 교체형 임베딩(기본 ollama `bge-m3`).
- **그래프**: `/graph`가 노드/엣지(위키링크+의미유사)를, `/cleanup/candidates`가 중복 후보(빨간선)를 준다.
- **정리**: 탐지는 임베딩(LLM 0), 병합문은 에이전트(Claude)가 작성하거나 엔진이 로컬 gemma로 자동요약.
- **MCP**: `mcp_server.py`(별도 프로세스, stdio) → 엔진 HTTP 프록시. 엔진이 떠 있어야 작동.
- **뇌 = 노트폴더 + 인덱스 한 쌍.** `SB_NOTES_PATH`/`SB_CHROMA_PATH`로 교체 → 여러 뇌.

## 주요 설계 결정

- **자동 쌓기(06-08)**: '강제 자동요약'(Stop hook이 LLM으로 무조건 capture)은 노이즈·비용으로 탈락 → **능동 규칙 + 조건부 리마인더**. 범위는 프로젝트 작업 기억을 second-brain으로 일원화(Claude Code 자체 메모리와 구분).
- **자동정리(06-08)**: 무인 자동 실행은 오삭제 위험으로 제외 → **에이전트 주도**. 탐지(임베딩)·병합(LLM)을 분리하고, merge 한 엔드포인트에서 content 유무로 두 LLM 경로(에이전트/gemma)를 모두 커버. 위키링크 보정·관계 라벨은 다음 단계.
- **방향(06-08 office-hours)**: 엔진 범용 유지 + 첫 클라이언트=에이전트 메모리(MCP) + 사람용 그래프 뷰. **Graphiti 안 씀**(운영 부담, Chroma 단순함 유지).
- 임베딩: 교체형 7종. 벡터DB: Chroma(임베디드). 레포 분리: 엔진(공개)+노트(비공개). 보안: 경로탈출 차단 + 옵션 API 키.

## 해결한 문제 (디버깅 기록)

- **bge-m3 500 NaN**: ollama `0.21.0`+bge-m3가 일부 청크 NaN → `0.30.6`로 해결.
- **코드블록 청킹 오인**: ``` 안 `#`를 헤딩 분할 → `in_code` 토글.
- **경로 안전 함정**: `_safe_rel`이 leading `/` strip 전 절대경로 검사하도록.
- **Bash 도구 cwd 함정**: 실제 cwd가 `/d`인데 "reset to ...second-brain-engine" 메시지는 거짓 → 상대경로가 `D:\` 루트의 엉뚱한 파일을 조용히 반환(예: `D:\.claude` 게임 템플릿 오인). **절대경로 필수**. (메모리 `shell-and-verify-commands` 참고)
- **curl 한글 body 깨짐**: git-bash에서 `curl -d '{한글}'`은 파싱 실패 → E2E는 python httpx로.

## 검증 상태

- ruff: All passed / pytest: **27 passed**(순수함수 + 가짜임베더 BrainIndex/cleanup + 임베딩 프리셋). graph.py·llm.py·mcp_server.py·hook은 통합/E2E로 확인.
- `/health` E2E: ollama `bge-m3` 실호출 OK. `/graph`·`recall`/`remember`·`/cleanup/*`(gemma 병합)·브라우저 렌더 실측 OK.

## 남은 작업 (다음 세션)

1. **Claude Code 재시작 후 검증**: ① cleanup MCP 도구(`cleanup_candidates`/`cleanup_merge`) ② Stop hook 환기 ③ "정리해줘"로 에이전트 주도 정리 플로우. (recall/remember는 이미 작동)
2. **자동정리 다음 단계**: 병합 시 `[[위키링크]]` 보정(병합된 노트 가리키던 링크), (선택) 무인 자동 실행(임계값/주기).
3. **안 B(데모급 그래프)**: 노드 유형 분류(의미/통찰/절차, LLM) · 의미 관계 엣지(지지/반박/확장, LLM) · 질문→답(RAG).
4. 헤르메스 실연동 — 또 다른 클라이언트로 여전히 가능.

## 로컬 환경 메모

- 작업 루트: `D:\project\` (git 미추적). **주의**: Bash 도구 cwd가 `/d`라 상대경로는 `D:\` 기준 — 항상 `/d/project/second-brain-engine/...` 절대경로.
- **에이전트 뇌**: `D:\project\brains\agent-memory`(노트) + `agent-memory-db`(인덱스). git 미추적.
- venv: `D:\project\second-brain-engine\.venv` (ruff/pytest/uvicorn/mcp/httpx).
- 엔진 실행: `SB_NOTES_PATH=<뇌> [SB_CHROMA_PATH=<db>] uvicorn app.main:app --port 8000` (cwd=엔진폴더 또는 `--app-dir`).
- 임베딩 모델: `ollama pull bge-m3`(기본). **정리용 LLM**: `gemma4:e4b`(기본, `SB_LLM_*`로 교체). 헤르메스 LLM도 gemma 계열.
- 검증용 임시파일(`_e2e*.py` 등)은 실행 후 삭제, `_`·`.gitignore`로 배포 제외.
