# File: app/main.py
# 검색엔진 HTTP API. 헤르메스가 의미검색(/search)·노트저장(/capture)을 호출한다.
# 실행: uvicorn app.main:app --host 0.0.0.0 --port 8000

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .config import Settings
from .embeddings import get_embedder
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


class SearchRequest(BaseModel):
    query: str
    k: int = 5


class CaptureRequest(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    folder: str = "inbox"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.embedding_provider,
        "notes_path": settings.notes_path,
        "documents": brain.collection.count(),
    }


@app.post("/search")
def search(req: SearchRequest) -> dict:
    if settings.auto_sync_on_search:
        brain.sync()
    return {"query": req.query, "results": brain.search(req.query, req.k)}


@app.post("/reindex")
def reindex() -> dict:
    return brain.sync()


@app.post("/capture")
def capture(req: CaptureRequest) -> dict:
    """정리된 노트(대화·인사이트)를 저장 + 즉시 인덱싱. ①대화→자동기억의 저장구.

    LLM 정리는 호출자(헤르메스)가 하고, 엔진은 받은 노트를 마크다운으로 영속화한다.
    """
    path = brain.add_note(req.title, req.content, req.tags, req.folder)
    return {"saved": path}
