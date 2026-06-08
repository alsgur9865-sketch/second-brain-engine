# File: app/llm.py
# 정리(cleanup)용 생성형 LLM 백엔드. 중복 기억을 하나로 병합·요약할 때만 쓴다.
# 임베딩과 달리 '글을 새로 쓰는' 작업이라 생성 모델이 필요 — 기본은 로컬 ollama gemma.
# 에이전트(Claude)가 병합문을 직접 주면 이 모듈은 안 불린다(엔진 무인 요약 경로 전용).

import httpx

# provider 이름 → (기본 base_url, 기본 모델). 필요 시 embeddings.py처럼 확장.
LLM_PRESETS: dict[str, dict[str, str]] = {
    "ollama": {"base_url": "http://localhost:11434", "model": "gemma4:e4b"},
}


class OllamaLLM:
    """로컬 Ollama 생성 모델. 추가 인프라 0 — 이미 깔린 Ollama 사용."""

    def __init__(self, base_url: str, model: str):
        self.url = f"{base_url.rstrip('/')}/api/generate"
        self.model = model

    def generate(self, prompt: str) -> str:
        r = httpx.post(
            self.url,
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=180,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()


def get_llm(settings):
    """설정값으로 LLM 생성. 지금은 ollama만(없는 provider면 명확히 실패)."""
    provider = settings.llm_provider.lower()
    preset = LLM_PRESETS.get(provider)
    if preset is None:
        raise ValueError(
            f"알 수 없는 llm_provider: {settings.llm_provider!r} "
            f"(지원: {', '.join(LLM_PRESETS)})"
        )
    base_url = settings.llm_base_url or preset["base_url"]
    model = settings.llm_model or preset["model"]
    return OllamaLLM(base_url, model)


def _split_title(text: str) -> tuple[str, str]:
    """LLM 출력에서 'TITLE: ...' 첫 줄과 본문을 분리. 형식이 안 맞으면 첫 줄을 제목으로."""
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("TITLE:"):
        title = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()
        return (title or "병합된 기억", body or text)
    first = lines[0].strip() if lines else "병합된 기억"
    return (first[:80] or "병합된 기억", text.strip())


def summarize_merge(llm, notes: list[dict]) -> tuple[str, str]:
    """중복 노트들을 하나로 통합한 (제목, 본문)을 생성. notes: [{title, content}, ...]."""
    joined = "\n\n---\n\n".join(f"## {n['title']}\n{n['content']}" for n in notes)
    prompt = (
        "다음은 거의 같은 내용의 기억 노트들이다. 중복을 제거하고 하나의 노트로 통합하라.\n"
        "사실은 모두 보존하되 군더더기는 줄인다. 한국어로 작성한다.\n"
        "첫 줄은 'TITLE: <한 줄 제목>', 그다음 줄부터 본문(마크다운)만 출력하라.\n\n"
        f"{joined}"
    )
    return _split_title(llm.generate(prompt))


NOTE_TYPES = ("의미", "통찰", "절차")


def classify_note(llm, title: str, content: str) -> str:
    """노트를 의미/통찰/절차 중 하나로 분류. 셋 중 아무것도 못 찾으면 '의미'로 폴백.
    content는 프론트매터를 뗀 본문을 넘기는 것이 분류 정확도가 높다."""
    prompt = (
        "노트를 정확히 한 단어로 분류하라. 반드시 의미/통찰/절차 중 하나만 출력(다른 말 금지).\n"
        "- 의미: 개념·정의·용어 설명\n"
        "- 통찰: 의견·판단·결정·방향성\n"
        "- 절차: 실행 방법·명령어·설정 단계\n\n"
        f"제목: {title}\n내용: {content}\n분류:"
    )
    out = llm.generate(prompt)
    for t in NOTE_TYPES:
        if t in out:
            return t
    return "의미"


NO_ANSWER = "기억에 없습니다."


def answer_question(llm, question: str, notes: list[dict]) -> str:
    """검색된 노트들만 근거로 질문에 답한다(1-shot RAG, 엄격 모드).

    notes: search() 결과 [{heading, snippet, ...}]. 근거가 없으면 추측하지 말고
    '기억에 없습니다'로 답하게 한다. notes가 비면 LLM을 부르지 않고 바로 그렇게 답한다.
    """
    if not notes:
        return NO_ANSWER
    context = "\n\n---\n\n".join(
        f"[{i + 1}] {n.get('heading') or n.get('path', '')}\n"
        f"{n.get('snippet') or n.get('content', '')}"
        for i, n in enumerate(notes)
    )
    prompt = (
        "다음은 사용자의 기억 노트에서 검색된 발췌다. 이 노트들만 근거로 질문에 답하라.\n"
        f"노트에 답의 근거가 없으면 추측하지 말고 정확히 '{NO_ANSWER}'라고만 답하라.\n"
        "한국어로 간결하게 답한다.\n\n"
        f"=== 노트 ===\n{context}\n\n"
        f"=== 질문 ===\n{question}\n\n답변:"
    )
    return llm.generate(prompt)
