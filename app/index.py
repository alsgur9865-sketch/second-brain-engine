# File: app/index.py
# Chroma 벡터DB 인덱싱 + 의미검색 + 노트 저장(capture).
# 핵심 아이디어: 검색/재인덱싱 때마다 노트 폴더를 스캔해 "변경된 파일만" 다시 임베딩한다(증분).
# 헤르메스는 노트 파일을 쓰거나 /capture로 저장하면 되고, 재인덱싱은 엔진이 알아서 한다.

import datetime
import os
import re

import chromadb

from .embeddings import EmbeddingProvider

_HEADING = re.compile(r"^#{1,3}\s")
_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def chunk_markdown(text: str) -> list[str]:
    """마크다운을 헤딩(#, ##, ###) 단위로 분할. 헤딩이 없으면 통째로 한 청크.

    코드블록(```) 안의 #는 헤딩이 아니므로 분할 기준에서 제외한다.
    """
    chunks: list[str] = []
    current: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        is_heading = not in_code and bool(_HEADING.match(line))
        if is_heading and current:
            block = "\n".join(current).strip()
            if block:
                chunks.append(block)
            current = [line]
        else:
            current.append(line)
    block = "\n".join(current).strip()
    if block:
        chunks.append(block)
    return chunks


def _slugify(title: str) -> str:
    """제목을 안전한 파일명 조각으로. 파일시스템 금지문자 제거, 공백→-, 길이 제한."""
    s = _UNSAFE.sub("", title).strip()
    s = re.sub(r"\s+", "-", s)
    return s[:50] or "note"


class BrainIndex:
    def __init__(self, settings, embedder: EmbeddingProvider):
        self.notes_path = settings.notes_path
        self.ignore_dirs = set(settings.ignore_dirs)
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection(settings.collection_name)

    # ---------- 상태 비교 (디스크 vs 인덱스) ----------
    def _scan_disk(self) -> dict[str, int]:
        """노트 폴더의 모든 *.md → {상대경로: 수정시각(초)}. ignore_dirs는 건너뛴다."""
        state: dict[str, int] = {}
        if not os.path.isdir(self.notes_path):
            return state
        for root, dirs, files in os.walk(self.notes_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]  # 제외 폴더 가지치기
            for name in files:
                if name.lower().endswith(".md"):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, self.notes_path).replace("\\", "/")
                    state[rel] = int(os.path.getmtime(full))
        return state

    def _indexed_state(self) -> dict[str, int]:
        """이미 인덱싱된 청크들의 메타데이터 → {상대경로: 수정시각}."""
        got = self.collection.get(include=["metadatas"])
        state: dict[str, int] = {}
        for meta in got["metadatas"]:
            state[meta["path"]] = meta["mtime"]
        return state

    # ---------- 증분 동기화 ----------
    def sync(self) -> dict:
        disk = self._scan_disk()
        indexed = self._indexed_state()

        to_index = [p for p, m in disk.items() if indexed.get(p) != m]
        to_remove = [p for p in indexed if p not in disk]

        for path in to_remove:
            self.collection.delete(where={"path": path})
        for path in to_index:
            self._index_file(path, disk[path])

        return {
            "indexed": len(to_index),
            "removed": len(to_remove),
            "total_files": len(disk),
        }

    def _index_file(self, rel_path: str, mtime: int) -> None:
        full = os.path.join(self.notes_path, rel_path)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        chunks = chunk_markdown(text)
        # 변경 파일 대비: 기존 청크 먼저 제거 후 새로 삽입
        self.collection.delete(where={"path": rel_path})
        if not chunks:
            return
        embeddings = self.embedder.embed(chunks)
        ids, metadatas = [], []
        for i, chunk in enumerate(chunks):
            heading = chunk.splitlines()[0] if _HEADING.match(chunk) else ""
            ids.append(f"{rel_path}::{i}")
            metadatas.append({"path": rel_path, "mtime": mtime, "chunk": i, "heading": heading})
        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ---------- 노트 저장 (capture) ----------
    def add_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        folder: str = "inbox",
    ) -> str:
        """정리된 노트를 프론트매터 마크다운으로 저장 + 즉시 인덱싱. 저장된 상대경로 반환.

        ①대화→자동기억의 저장구. 파일명 충돌은 -2, -3 …으로 회피한다.
        """
        today = datetime.date.today().isoformat()
        rel_dir = folder.strip("/\\") or "inbox"
        base = f"{today}-{_slugify(title)}"
        rel_path = f"{rel_dir}/{base}.md"
        full = os.path.join(self.notes_path, rel_path)
        n = 2
        while os.path.exists(full):
            rel_path = f"{rel_dir}/{base}-{n}.md"
            full = os.path.join(self.notes_path, rel_path)
            n += 1

        os.makedirs(os.path.dirname(full), exist_ok=True)
        fm_tags = ", ".join(tags or [])
        md = (
            f"---\ntitle: {title}\ncreated: {today}\n"
            f"tags: [{fm_tags}]\nsource: capture\n---\n\n"
            f"# {title}\n\n{content}\n"
        )
        with open(full, "w", encoding="utf-8") as f:
            f.write(md)

        self._index_file(rel_path, int(os.path.getmtime(full)))
        return rel_path

    # ---------- 검색 ----------
    def search(self, query: str, k: int = 5) -> list[dict]:
        if self.collection.count() == 0:
            return []
        query_emb = self.embedder.embed([query])[0]
        res = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        results = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
        ):
            results.append(
                {
                    "path": meta["path"],
                    "heading": meta.get("heading", ""),
                    "snippet": doc[:500],
                    "distance": round(dist, 4),
                }
            )
        return results
