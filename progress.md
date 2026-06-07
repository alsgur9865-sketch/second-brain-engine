<!-- progress-sync: d42f2476e435bbbceac5da487b0ac6688a9f0673 -->
# Progress — 세컨드 브레인 엔진 (범용)

> 최종 업데이트: 2026-06-07

## 한 줄 요약

대화를 듣고 **자동으로 기억**하고 **의미검색으로 회상**하는 **범용 세컨드 브레인 엔진**.
엔진(`second-brain-engine`)은 HTTP API만 노출하는 **범용 코어** — 누구든 클라이언트가 될 수 있다.
**현 주력 통합(첫 클라이언트)은 헤르메스(디스코드 봇)**. **배포 완료, 헤르메스 실연동만 남음.**

## 정체성: 범용 엔진 + 교체 가능한 클라이언트

- **엔진은 헤르메스 전용이 아니다.** `app/` 코드에 헤르메스·디스코드 의존성 0 (주석 설명에만 등장).
  받는 건 순수 JSON, 누가 호출하는지 신경 쓰지 않는 일반 HTTP API다.
- **헤르메스는 "이 엔진의 클라이언트 중 하나"** — 지금은 유일하게 구현된 통합.
  같은 API를 CLI·웹 대시보드·Obsidian 플러그인·다른 봇 누구나 `curl`로 호출 가능.

| 구분 | 정체성 |
|---|---|
| `second-brain-engine` (엔진 코어) | **범용** — HTTP만 때리면 누구든 클라이언트 |
| `hermes-skill/` (통합 레이어) | 현재 **유일·주력 클라이언트** (= 첫 통합) |

## 현재 상태: 배포 완료 ✅

| 레포 | 공개 | URL |
|---|---|---|
| second-brain-engine | 🌐 public (MIT) | https://github.com/alsgur9865-sketch/second-brain-engine |
| my-second-brain | 🔒 private | https://github.com/alsgur9865-sketch/my-second-brain |

## 진행 기록

- **2026-06-07 교체형 임베딩 백엔드**: provider 이름 한 줄로 로컬(ollama/lmstudio/llamacpp/tei)·클라우드(openai/voyage/gemini) 임베딩 교체. OpenAI 호환 1클래스 + 프리셋, 모델별 컬렉션 자동 분리로 차원 충돌 없이 자동 재빌드. 설정은 `SB_EMBED_*` 4필드로 통합. (Claude는 임베딩 API 없어 Voyage로 대체)
- **2026-06-07 그래프 검색(연결 회상)** (`01c541c`): 검색 결과에 `[[위키링크]]`로 이어진 1-hop 이웃 노트를 `linked`로 첨부 — 단편이 아니라 연결된 기억 덩어리로 회상. Karpathy식 교차링크의 첫 구현, LLM 불필요. (실측: "환불 며칠?" → 환불 노트 + linked "온보딩 체크리스트")
- **2026-06-07 온보딩 팩** (`5ad123e`): 처음 온 사람이 clone→5분 안에 의미검색 성공까지 가도록 번들 샘플 vault(노트 3개)·README Quickstart(영/한)·CONTRIBUTING 추가. 오픈소스 진입장벽 제거. (실측: "환불 며칠?" → 환불 노트 distance 0.55 1위)
- **2026-06-07 보안·기능 강화** (`d0a1f26`): 경로 탈출 차단(`_safe_rel`)·옵션형 API 키(`X-API-Key`)·`/health` 임베딩 백엔드 헬스체크로 보안을 단단히 하고, 프론트매터 태그/날짜 메타데이터 인덱싱·검색 필터(`tag`/`folder`/`max_distance`)·`/delete` 엔드포인트를 추가. docker 임베딩 모델을 `bge-m3`로 통일, MIT LICENSE·영/한 이중언어 README·테스트(5→11) 정비.
- **2026-06-07 범용 재포지셔닝** (`78ffed4`): "헤르메스 전용" 표현을 걷어내고 범용 엔진으로 정리 — GitHub About·topics·README(영/한 토글)를 범용 기준으로 재작성.

## 아키텍처

```
[ 클라이언트 레이어 (교체·확장 가능) ]
  · 헤르메스 스킬 (현 주력) ── 대화 정리(LLM)
  · (향후) CLI / 웹 대시보드 / Obsidian / 다른 봇
            |
            | HTTP (JSON)
            v
[ 엔진 코어: second-brain-engine (범용) ]
  /health · /search · /capture · /reindex · /delete
            |
   +--------+------------------+
   |                           |
my-second-brain(.md 노트)   Chroma 벡터DB(의미검색)
저장/읽기                    임베딩 인덱스
```

- **second-brain-engine** (공개, 범용 코어): Python FastAPI + Chroma + 교체형 임베딩(기본 ollama `bge-m3`; lmstudio/llamacpp/tei/openai/voyage/gemini 프리셋).
  API: `GET /health` · `POST /search` · `POST /capture` · `POST /reindex` · `POST /delete`.
  검색 필터(`tag`/`folder`/`max_distance`)·옵션형 API 키(`X-API-Key`). 클라이언트 비의존.
- **my-second-brain** (비공개): 마크다운 노트 폴더(`inbox`/`notes`/`daily`/`templates`). Obsidian으로도 열림.
- **헤르메스 스킬** (현 주력 클라이언트): `second-brain-engine/hermes-skill/second-brain/SKILL.md`
  (엔진 레포에 포함, 공개). 헤르메스가 이 API를 호출하는 *사용 설명서*이지 엔진의 일부는 아님.
  헤르메스 `config.yaml`의 `skills.external_dirs`로 연결됨.

## 주요 설계 결정

- **검색엔진형**(가벼운 마크다운 아님) + **하이브리드 연동**(파일 읽기 + 의미검색 API).
- **엔진/클라이언트 분리**: 엔진은 HTTP만 노출 → 헤르메스에 묶이지 않고 어떤 클라이언트든 붙음.
- 벡터DB: **Chroma**(임베디드, 파일 저장) — 1인 규모에 가벼움.
- 임베딩: **교체형** — provider 이름 한 줄로 7종(ollama/lmstudio/llamacpp/tei/openai/voyage/gemini) 교체. 모델별 컬렉션 자동 분리·재빌드.
- 실행: 로컬 `docker compose` 또는 `uvicorn`.
- 레포 분리: **엔진(공개) + 노트(비공개)** — 코드는 공개, 데이터/시크릿은 비공개.
- **차별화 ① 대화→자동기억**: `/capture` 엔드포인트 = 정리된 노트를 저장+즉시 인덱싱.
  정리(LLM)는 클라이언트(현재 헤르메스)가, 저장·검색은 엔진이. → 경쟁 OSS(수동 입력·1인 CLI)와 차별.
- **보안**: 경로 탈출 차단(`..`·절대경로 무력화) + 옵션형 API 키(비우면 인증 없음, 설정 시 강제).

## 해결한 문제 (디버깅 기록)

- **bge-m3 500 NaN 버그**: ollama `0.21.0` + bge-m3가 일부 한국어/코드블록 청크에서 NaN 임베딩 생성
  → ollama `0.30.6` 업데이트로 해결. (배치 가설은 틀렸음 — 청크별 NaN이 원인)
- **코드블록 청킹 오인**: 코드블록(```) 안의 `#`를 헤딩으로 분할하던 것 → `in_code` 토글로 무시.
- **한국어 검색 품질**: `nomic-embed-text`(변별력 약) → `bge-m3`로 교체해 distance 분포 개선.
- **경로 안전 함정**: `_safe_rel`이 leading `/`를 먼저 strip해 절대경로 판정이 무력화 → strip 전에 검사하도록 수정(테스트가 잡음).

## 검증 상태

- ruff: All checks passed / pytest: **23 passed** (순수함수 + 가짜 임베더 BrainIndex capture/search/delete + 임베딩 프리셋 팩토리 + 모델별 컬렉션 분리)
- `/health` E2E: ollama `bge-m3` 실호출 성공(`embedding_ok: true`), `provider`·`model`·`collection`(`second_brain__ollama_bge_m3`) 노출 확인
- 임베딩: **교체형 7종**(ollama/lmstudio/llamacpp/tei/openai/voyage/gemini), 기본 `bge-m3`(ollama 0.30.6), 헤르메스 LLM: `gemma4:e4b`

## 남은 작업 (다음 세션)

1. **헤르메스 실연동** (미완 — 첫 클라이언트 붙이기)
   - 엔진 띄우기: `uvicorn app.main:app --port 8000` (cwd=엔진폴더) 또는 `docker compose up -d`
   - 헤르메스 `~/.hermes/.env`에 `SECOND_BRAIN_PATH`(노트 경로)·`SECOND_BRAIN_API`(`http://localhost:8000`) 설정
   - 봇 재시작 (스킬 인식 — SOUL.md/스킬 캐시 때문에 `/reset` 또는 재시작 필요)
   - 디스코드에서 "기억해둬"/"찾아줘" 테스트
   - ⚠️ 확인 필요: 헤르메스가 쓰는 셸(WSL/git-bash) → SKILL.md의 경로 형식 맞추기
   - SKILL.md에 `/delete`·검색 필터·API 키 헤더 사용법 반영 여부 점검

2. **운영 보강** (진단됐으나 아직 미구현)
   - 에러 처리·로깅 (ollama 다운 시 raw 500 → 친화 메시지/로그)
   - Dockerfile `HEALTHCHECK`·non-root 유저
   - HTTP 레이어 테스트(FastAPI `TestClient`), CHANGELOG

## 추후 방향성

### 클라이언트 확장 (엔진은 범용이므로 통합을 늘릴 수 있음)
- CLI / 웹 대시보드 / Obsidian 플러그인 / 다른 봇 등 새 클라이언트 추가 여지.

### 차별화 축
- ① 대화→자동기억 ✅ 구현됨
- ⑤ 연결 회상(`[[위키링크]]` 그래프) ✅ 구현됨 — Karpathy식 교차링크. 검색에 이웃 노트 첨부 (`01c541c`)
- ② 능동적 회상 — ⏳ **추후 업데이트 예정**. 봇이 먼저 "저번에 적었잖아" 떠올림. 본체는 헤르메스 로직(매 대화 `/search`+임계값 끼어들기), 엔진은 `/search`로 거의 충분 → **헤르메스 실연동 후**
- ③ 기억의 자가진화 — ⏳ **추후 업데이트 예정**. 같은 주제 노트 자동 병합·요약. 엔진은 "병합 후보 클러스터 찾기"까지, 합칠지 판단·요약은 LLM=봇 + 사람 확인(오병합 위험) → **헤르메스 실연동 후**
- ④ 캐릭터 기억 / 팀 공유 두뇌 — 아이디어 단계
- (B 차용) khoj 의미검색 깊이

## 로컬 환경 메모

- 작업 루트: `D:\project\` (이 progress.md 위치, git 미추적)
- venv: `D:\project\second-brain-engine\.venv` (ruff/pytest/uvicorn)
- 검증용 임시파일: `_smoke.py`·`_diag.py`·`_e2e.py`·`_e2e.ps1` (`.gitignore`로 배포 제외, 로컬에만 있음)
- 임베딩 모델 다운로드됨: `ollama pull bge-m3`, `nomic-embed-text`
