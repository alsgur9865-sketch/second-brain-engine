# File: app/main.py
# 검색엔진 HTTP API. 클라이언트가 의미검색(/search)·노트저장(/capture)·삭제(/delete)를 호출한다.
# 실행: uvicorn app.main:app --host 0.0.0.0 --port 8000

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .cleanup import find_duplicate_candidates
from .config import Settings
from .embeddings import get_embedder
from .graph import build_graph
from .index import BrainIndex, _safe_rel, _strip_frontmatter, parse_frontmatter
from .llm import answer_question, get_llm, summarize_merge

settings = Settings()
embedder = get_embedder(settings)
brain = BrainIndex(settings, embedder)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 서버 시작 시 노트 변경분을 한 번 동기화
    brain.sync()
    yield


app = FastAPI(title="second-brain-engine", version="0.1.0", lifespan=lifespan)

_STATIC = Path(__file__).resolve().parent / "static"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """SB_API_KEY가 설정돼 있으면 X-API-Key 헤더를 강제. 비어있으면 인증 없음(기본)."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


class SearchRequest(BaseModel):
    query: str
    k: int = 5
    tag: str | None = None
    folder: str | None = None
    max_distance: float | None = None
    include_links: bool = True


class AskRequest(BaseModel):
    query: str
    k: int = 5


class CaptureRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    folder: str = "inbox"


class DeleteRequest(BaseModel):
    path: str


class MergeRequest(BaseModel):
    sources: list[str]            # 합칠 노트들(상대경로, 2개 이상)
    title: str | None = None
    content: str | None = None    # 비우면 엔진이 로컬 LLM으로 자동 요약
    folder: str = "decisions"
    tags: list[str] = []


@app.get("/health")
def health() -> dict:
    # 임베딩 백엔드(ollama 등)가 실제로 응답하는지까지 확인
    try:
        embedder.embed(["health"])
        embedding_ok = True
    except Exception:
        embedding_ok = False
    return {
        "status": "ok" if embedding_ok else "degraded",
        "embedding_ok": embedding_ok,
        "provider": settings.embedding_provider,
        "model": getattr(embedder, "model", ""),
        "collection": brain.collection_name,
        "notes_path": settings.notes_path,
        "documents": brain.collection.count(),
    }


@app.get("/")
def index_page() -> FileResponse:
    """사람이 보는 그래프 뷰(force-graph 단일 페이지)."""
    return FileResponse(_STATIC / "graph.html")


@app.get("/graph")
def graph() -> dict:
    """노트 그래프(노드 + [[위키링크]]·의미유사 엣지). 그래프 뷰의 데이터원.

    읽기 전용 시각화라 /health처럼 인증을 두지 않는다(로컬 도구).
    """
    if settings.auto_sync_on_search:
        brain.sync()
    return build_graph(brain)


@app.get("/note")
def note(path: str) -> dict:
    """노트 한 개의 본문 + 메타(제목/유형/태그/생성일)를 반환. 그래프 노드 클릭 시 상세 패널용.

    읽기 전용이라 /graph처럼 인증을 두지 않는다(로컬 도구). path는 노트 폴더 기준 상대경로.
    """
    safe = _safe_rel(path)
    if not safe:
        raise HTTPException(status_code=400, detail="안전하지 않은 경로")
    full = os.path.join(settings.notes_path, safe)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="노트를 찾을 수 없다")
    with open(full, encoding="utf-8") as f:
        text = f.read()
    fm = parse_frontmatter(text)
    return {
        "path": safe,
        "title": fm["title"],
        "type": fm["type"],
        "tags": [t for t in fm["tags"].split(",") if t],
        "created": fm["created"],
        "body": _strip_frontmatter(text),
    }


@app.post("/search", dependencies=[Depends(require_api_key)])
def search(req: SearchRequest) -> dict:
    if settings.auto_sync_on_search:
        brain.sync()
    results = brain.search(
        req.query, req.k, req.tag, req.folder, req.max_distance, req.include_links
    )
    return {"query": req.query, "results": results}


@app.post("/ask", dependencies=[Depends(require_api_key)])
def ask(req: AskRequest) -> dict:
    """질문을 노트에서 검색해 로컬 LLM이 근거 기반으로 답한다(1-shot RAG, 엄격 모드).

    ②기억→꺼내 쓰기. 관련 노트가 없으면 '기억에 없습니다'로 답하고 sources는 빈 리스트.
    답변 생성은 cleanup과 같은 로컬 LLM(get_llm)을 쓴다. 멀티홉 없이 top-k 본문만 근거로.
    """
    if settings.auto_sync_on_search:
        brain.sync()
    notes = brain.search(req.query, req.k, include_links=False)
    answer = answer_question(get_llm(settings), req.query, notes)
    sources = [
        {"path": n["path"], "heading": n["heading"], "distance": n["distance"]}
        for n in notes
    ]
    return {"query": req.query, "answer": answer, "sources": sources}


@app.post("/reindex", dependencies=[Depends(require_api_key)])
def reindex() -> dict:
    return brain.sync()


@app.post("/capture", dependencies=[Depends(require_api_key)])
def capture(req: CaptureRequest) -> dict:
    """정리된 노트(대화·인사이트)를 저장 + 즉시 인덱싱. ①대화→자동기억의 저장구.

    LLM 정리는 호출자(클라이언트)가 하고, 엔진은 받은 노트를 마크다운으로 영속화한다.
    """
    path = brain.add_note(req.title, req.content, req.tags, req.folder)
    return {"saved": path}


@app.post("/delete", dependencies=[Depends(require_api_key)])
def delete(req: DeleteRequest) -> dict:
    """노트 파일 삭제 + 인덱스에서 제거. path는 노트 폴더 기준 상대경로."""
    return brain.delete_note(req.path)


def _read_notes(sources: list[str]) -> list[dict]:
    """sources(상대경로)의 노트를 안전하게 읽어 [{title, content}]로. 경로탈출은 건너뛴다."""
    notes: list[dict] = []
    for rel in sources:
        safe = _safe_rel(rel)
        if not safe:
            continue
        full = os.path.join(settings.notes_path, safe)
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8") as f:
            text = f.read()
        fm = parse_frontmatter(text)
        notes.append({"title": fm["title"] or safe, "content": text})
    return notes


@app.get("/cleanup/candidates")
def cleanup_candidates(threshold: float = 0.85, max_pairs: int = 20) -> dict:
    """중복/유사 후보 쌍(임베딩 유사도 threshold 이상). 읽기 전용이라 인증 없음.

    threshold가 높을수록 '거의 같은' 것만 잡는다. 각 쌍에 두 노트의 path/title/snippet.
    """
    if settings.auto_sync_on_search:
        brain.sync()
    return {"candidates": find_duplicate_candidates(brain, threshold, max_pairs)}


@app.post("/cleanup/merge", dependencies=[Depends(require_api_key)])
def cleanup_merge(req: MergeRequest) -> dict:
    """중복 노트(sources, 2개 이상)를 하나로 병합. content 있으면 사용, 없으면 로컬 LLM 요약.

    새 노트를 저장하고 원본을 삭제한 뒤, 원본을 가리키던 [[위키링크]]를 새 제목으로 보정한다.
    """
    if len(req.sources) < 2:
        raise HTTPException(status_code=400, detail="sources는 2개 이상이어야 한다")

    title, content = req.title, req.content
    if not content:
        notes = _read_notes(req.sources)
        if not notes:
            raise HTTPException(status_code=404, detail="병합할 노트를 찾을 수 없다")
        gen_title, content = summarize_merge(get_llm(settings), notes)
        title = title or gen_title
    if not title:
        raise HTTPException(status_code=400, detail="title이 필요하다(content를 비우면 자동 생성)")

    new_path = brain.add_note(title, content, req.tags, req.folder)
    old_names = brain.collect_link_names(req.sources)   # 삭제 전에 옛 이름 수집
    removed: list[str] = []
    for src in req.sources:
        safe = _safe_rel(src)
        if not safe or safe == new_path:
            continue
        brain.delete_note(safe)
        removed.append(safe)
    relinked = brain.relink(old_names, title, skip={new_path})
    return {"merged": new_path, "removed": removed, "relinked": relinked}


@app.post("/classify", dependencies=[Depends(require_api_key)])
def classify() -> dict:
    """frontmatter에 type이 없는 노트를 LLM(의미/통찰/절차)으로 분류해 채운다(이미 있으면 skip)."""
    return brain.classify_unclassified(get_llm(settings))
