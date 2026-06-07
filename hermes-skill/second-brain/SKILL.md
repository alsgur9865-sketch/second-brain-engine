---
name: second-brain
description: 개인 세컨드 브레인(마크다운 노트)에서 의미검색·읽기·쓰기. "내 노트/세컨드브레인에서 찾아줘", "이거 기억해둬", "노트로 저장해줘" 같은 요청에 사용. Semantic search over a personal markdown knowledge base via a local engine.
---

# Second Brain

개인 지식베이스. 마크다운 노트 레포(`my-second-brain`)를 직접 읽고/쓰며, 의미검색은 로컬 엔진(`second-brain-engine`)이 담당한다.

**설정** (`~/.hermes/.env`):
- `SECOND_BRAIN_PATH` — 노트 레포 경로 (예: `/d/project/my-second-brain`)
- `SECOND_BRAIN_API` — 검색엔진 URL (기본 `http://localhost:8000`)

**언제 쓰나**: 사용자가 자기 노트/지식베이스에서 무언가 찾아달라거나, 새 지식을 기억·저장해달라고 할 때.

## 1. 의미검색 — 키워드가 정확히 안 맞아도 의미로 찾기

```bash
API="${SECOND_BRAIN_API:-http://localhost:8000}"
curl -s -X POST "$API/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "찾고 싶은 내용", "k": 5}'
```

응답의 각 결과: `path`(노트 경로), `heading`(섹션 제목), `snippet`(미리보기), `distance`(작을수록 관련 높음). 관련 노트를 찾으면 아래 cat으로 전문을 읽어 답한다.

## 2. 정확 검색 / 읽기 — 파일명·정확 키워드

```bash
BRAIN="${SECOND_BRAIN_PATH:?SECOND_BRAIN_PATH 미설정}"
grep -rli "키워드" "$BRAIN" --include="*.md"   # 내용으로 파일 찾기
cat "$BRAIN/notes/노트제목.md"                  # 전문 읽기
```

## 3. 노트 쓰기 — 새 지식 저장

`notes/`(정리됨) 또는 `inbox/`(미정리)에 프론트매터 형식으로 저장한다. 엔진이 다음 검색 때 자동 재인덱싱하므로 추가 작업은 필요 없다.

```bash
BRAIN="${SECOND_BRAIN_PATH:?}"
TODAY=$(date +%Y-%m-%d)
cat > "$BRAIN/inbox/노트제목.md" << EOF
---
title: 노트 제목
created: $TODAY
tags: [태그1, 태그2]
source:
---

# 노트 제목

## 핵심
요점...

## 메모
세부...
EOF
```

## 4. 대화 자동수집 — 노트를 안 써도 쌓인다 (차별화 기능)

채널의 최근 대화에서 **의미 있는 것만 네가 직접 정리**해 `/capture`로 저장한다. 잡담·인사·농담은 빼고 결정·아이디어·할 일·배운 것만. 사용자가 "이거 기억해둬", "정리해둬" 하거나, 대화가 한 매듭 지어졌을 때 능동적으로 수행한다.

```bash
API="${SECOND_BRAIN_API:-http://localhost:8000}"
curl -s -X POST "$API/capture" \
  -H "Content-Type: application/json" \
  -d '{"title":"오늘 정한 것","content":"## 결정\n- ...\n\n## 할 일\n- ...","tags":["회의"],"folder":"inbox"}'
```

- 정리(요약·구조화)는 **네(LLM)가**, 저장·인덱싱은 **엔진이** 한다.
- 저장 즉시 인덱싱되므로 이후 의미검색에 바로 잡힌다.
- 애매하면 `folder`를 `inbox`(미정리)로 두고, 확실하면 `notes`로.

**규칙**
- 본문은 `##` 헤딩으로 섹션을 나눈다 (엔진이 헤딩 단위로 청킹·검색).
- 노트끼리는 `[[다른 노트 제목]]` 위키링크로 연결.
- `git push`는 사용자 확인 후에만 (자동 금지). 헤르메스는 로컬 파일 쓰기까지.
