# File: app/main.py
# 검색엔진 HTTP API. 클라이언트가 의미검색(/search)·노트저장(/capture)·삭제(/delete)를 호출한다.
# 실행: uvicorn app.main:app --host 0.0.0.0 --port 8000

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import Settings
from .embeddings import get_embedder
from .graph import build_graph
from .index import BrainIndex

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


class CaptureRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    folder: str = "inbox"


class DeleteRequest(BaseModel):
    path: str


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


@app.post("/search", dependencies=[Depends(require_api_key)])
def search(req: SearchRequest) -> dict:
    if settings.auto_sync_on_search:
        brain.sync()
    results = brain.search(
        req.query, req.k, req.tag, req.folder, req.max_distance, req.include_links
    )
    return {"query": req.query, "results": results}


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
