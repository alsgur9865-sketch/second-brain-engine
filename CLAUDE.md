# second-brain-engine — 프로젝트 작업 규칙

> 글로벌 규칙(`~/.claude/CLAUDE.md`)에 더해 이 프로젝트에만 적용되는 규칙.

## 🧠 에이전트 메모리 (second-brain dogfooding)

이 프로젝트는 **자기 자신을 dogfooding**한다 — Claude가 second-brain MCP(`recall`/`remember`)로
이 프로젝트의 작업 기억을 직접 쓰고 읽는다. 사람은 같은 기억을 `/graph`로 본다.

- 대상 뇌·엔진 주소: 엔진 설정(`SB_NOTES_PATH`)을 따른다(현재 dogfooding 뇌는 `progress.md` 참고).
- 엔진이 `localhost:8000`에 떠 있어야 MCP 호출이 성공한다. 안 떠 있으면 회상/저장은 건너뛰고 진행한다.

### 읽기 — 작업 시작 시 `recall` 먼저
- 새 작업·주제에 들어가기 전에 `mcp__second-brain__recall`로 관련 과거 기억을 꺼낸다.
  (예: 그래프를 만지기 전 `recall("그래프 엣지 설계")`.)
- 회상 결과는 **참고 자료**일 뿐이다. 현재 코드와 어긋나면 코드를 신뢰하고, 틀린 기억은 갱신한다.

### 쓰기 — 확정되면 `remember`
아래가 **확정**되면 `mcp__second-brain__remember`로 저장한다:

- **결정**(`folder=decisions`): 설계·방향 선택과 그 이유. (예: "Graphiti 안 씀 — 운영 부담")
- **버그 원인**(`folder=bugs`): 비자명한 원인과 해결. (예: "bge-m3 NaN → ollama 0.30.6")
- **할 일**(`folder=todos`): 다음 세션으로 넘기는 미완 작업.
- **배운 점**(`folder=decisions`): 이 코드베이스의 비자명한 함정.

규칙:
- 저장 전 `recall`로 **중복 확인** — 이미 있으면 새로 만들지 말고 넘어간다.
- `title`은 한 줄 요약, `content`는 마크다운(관련 기억은 `[[제목]]`으로 링크해 그래프 엣지를 만든다).
- `tags`로 주제 분류(예: `graph`, `mcp`, `embedding`).

### 정리 — 중복이 쌓이면 cleanup
- 기억이 늘어 중복이 의심되거나 사용자가 "정리해줘" 하면 `mcp__second-brain__cleanup_candidates`로 후보 쌍을 확인한다.
- 진짜 같은 내용이면 `mcp__second-brain__cleanup_merge`로 합친다. **통합문을 직접 써서 `content`로 넘기는 걸 우선**하고(품질↑), 급하면 비워서 로컬 LLM 자동요약에 맡긴다.
- 애매하면(다른 관점·보완 관계) **합치지 말고 둔다** — 잘못된 병합은 기억 손실이다.

### 안 넣을 것 (노이즈 차단)
- 코드·git 로그를 보면 알 수 있는 것(파일 구조, 과거 diff).
- 일회성 잡담, 확정 안 된 추측.
- `CLAUDE.md`·`progress.md`에 이미 적힌 것.

### Claude Code 자체 메모리(`MEMORY.md`)와의 구분
- 이 프로젝트의 **작업 지식**(결정·버그·할 일)은 **second-brain으로 일원화**한다.
- Claude Code 자체 메모리는 도구 사용 함정 등 **Claude 작업 보조용**만 남긴다.

> 세션 끝에 기억을 안 남기면 Stop hook(`.claude/hooks/remind_memory.py`)이 한 번 환기한다.
> 이 hook 등록은 PC 종속이라 `.claude/settings.local.json`(git 제외)에 있다.
