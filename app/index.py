# File: app/index.py
# Chroma 벡터DB 인덱싱 + 의미검색 + 노트 저장(capture)/삭제 + [[위키링크]] 그래프 검색.
# 핵심 아이디어: 검색/재인덱싱 때마다 노트 폴더를 스캔해 "변경된 파일만" 다시 임베딩한다(증분).
# 클라이언트는 노트 파일을 쓰거나 /capture로 저장하면 되고, 재인덱싱은 엔진이 알아서 한다.

import datetime
import os
import re

import chromadb

from .embeddings import EmbeddingProvider

_HEADING = re.compile(r"^#{1,3}\s")
_UNSAFE = re.compile(r'[\\/:*?"<>|]')
_LINK = re.compile(r"\[\[([^\[\]]+)\]\]")   # [[노트 제목]] 또는 [[제목|별칭]]
_COLL_UNSAFE = re.compile(r"[^a-zA-Z0-9]+")   # Chroma 컬렉션 이름은 영숫자/_/- 만 안전


def _collection_slug(provider: str, model: str) -> str:
    """provider+model을 Chroma 컬렉션 이름 조각으로. 영숫자 외(`:`/`/`/`.`/`-`)는 _로, 양끝 _ 제거."""
    raw = f"{provider}__{model}" if model else provider
    return _COLL_UNSAFE.sub("_", raw).strip("_")


def _collection_name(base: str, provider: str, model: str) -> str:
    """모델별로 컬렉션을 분리. provider가 없으면(테스트 등) base를 그대로 쓴다(하위호환)."""
    if not provider:
        return base
    return f"{base}__{_collection_slug(provider, model)}"


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


def parse_frontmatter(text: str) -> dict[str, str]:
    """노트 맨 위 `--- ... ---` 프론트매터에서 title/tags/created를 얕게 추출.

    Chroma 메타데이터는 스칼라만 허용하므로 tags는 콤마 문자열로 평탄화한다.
    프론트매터가 없으면 빈 값.
    """
    meta = {"title": "", "tags": "", "created": ""}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end == -1:
        return meta
    for line in text[3:end].splitlines():
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        if key == "title":
            meta["title"] = val
        elif key == "tags":
            items = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
            meta["tags"] = ",".join(items)
        elif key == "created":
            meta["created"] = val
    return meta


def extract_links(text: str) -> list[str]:
    """본문의 `[[제목]]`/`[[제목|별칭]]`에서 대상 제목만 순서대로 추출(중복 제거)."""
    out: list[str] = []
    for raw in _LINK.findall(text):
        target = raw.split("|")[0].strip()
        if target and target not in out:
            out.append(target)
    return out


def _slugify(title: str) -> str:
    """제목을 안전한 파일명 조각으로. 파일시스템 금지문자 제거, 공백→-, 길이 제한."""
    s = _UNSAFE.sub("", title).strip()
    s = re.sub(r"\s+", "-", s)
    return s[:50] or "note"


def _safe_rel(path: str, default: str = "") -> str:
    """노트 폴더 기준 상대경로를 안전화. 절대경로·상위(..) 탈출은 default로 강제."""
    norm = path.replace("\\", "/")
    if norm.startswith("/") or os.path.isabs(norm):   # 절대경로는 strip 전에 거부
        return default
    rel = norm.strip("/")
    if not rel or ".." in rel.split("/"):
        return default
    return rel


def _norm_name(s: str) -> str:
    """링크 텍스트/제목 매칭용 정규화(앞뒤 공백 제거 + 소문자)."""
    return s.strip().lower()


class BrainIndex:
    def __init__(self, settings, embedder: EmbeddingProvider):
        self.notes_path = settings.notes_path
        self.ignore_dirs = set(settings.ignore_dirs)
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        # 모델별로 컬렉션을 분리 → 모델을 바꾸면 빈 컬렉션을 보게 되고 sync()가 자동 full 빌드.
        provider = getattr(embedder, "provider", "")
        model = getattr(embedder, "model", "")
        self.collection_name = _collection_name(settings.collection_name, provider, model)
        self.collection = self.client.get_or_create_collection(self.collection_name)

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
        fm = parse_frontmatter(text)
        links = ",".join(extract_links(text))   # 노트 단위 [[링크]] → 메타에 평탄화 저장
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
            metadatas.append(
                {
                    "path": rel_path,
                    "mtime": mtime,
                    "chunk": i,
                    "heading": heading,
                    "title": fm["title"],
                    "tags": fm["tags"],
                    "created": fm["created"],
                    "links": links,
                }
            )
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
        folder는 노트 폴더 밖으로 못 나가게 안전화한다(경로 탈출 방지).
        """
        today = datetime.date.today().isoformat()
        rel_dir = _safe_rel(folder, "inbox") or "inbox"
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

    # ---------- 노트 삭제 ----------
    def delete_note(self, path: str) -> dict:
        """노트 파일을 지우고 인덱스에서도 제거. path는 노트 폴더 기준 상대경로."""
        rel = _safe_rel(path)
        if not rel:
            raise ValueError(f"안전하지 않은 경로: {path!r}")
        full = os.path.join(self.notes_path, rel)
        file_existed = os.path.isfile(full)
        if file_existed:
            os.remove(full)
        self.collection.delete(where={"path": rel})
        return {"deleted": rel, "file_existed": file_existed}

    # ---------- 그래프(위키링크) ----------
    def _name_index(self) -> dict[str, str]:
        """노트를 가리킬 수 있는 이름(파일명 stem · frontmatter title) → 상대경로."""
        got = self.collection.get(include=["metadatas"])
        idx: dict[str, str] = {}
        for m in got["metadatas"]:
            path = m["path"]
            stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            idx[_norm_name(stem)] = path
            title = m.get("title")
            if title:
                idx[_norm_name(title)] = path
        return idx

    def _attach_linked(self, results: list[dict]) -> None:
        """각 결과의 `_links`(원시 [[링크]] 텍스트)를 실제 노트 경로로 풀어 `linked`에 첨부."""
        name_to_path = self._name_index()
        for r in results:
            linked: list[dict] = []
            seen: set[str] = set()
            for raw in (r.get("_links") or "").split(","):
                target = raw.strip()
                if not target:
                    continue
                path = name_to_path.get(_norm_name(target))
                if path and path != r["path"] and path not in seen:
                    seen.add(path)
                    linked.append({"name": target, "path": path})
            r["linked"] = linked

    # ---------- 검색 ----------
    def search(
        self,
        query: str,
        k: int = 5,
        tag: str | None = None,
        folder: str | None = None,
        max_distance: float | None = None,
        include_links: bool = True,
    ) -> list[dict]:
        """의미검색. tag/folder로 좁히고, max_distance보다 먼 결과는 버린다.

        include_links면 각 히트의 `[[링크]]`를 따라 1-hop 이웃 노트를 `linked`로 첨부한다.
        tag/folder는 Chroma where로 부분매칭이 안 되므로 후보를 넉넉히 뽑아 파이썬에서 거른다.
        """
        n = self.collection.count()
        if n == 0:
            return []
        query_emb = self.embedder.embed([query])[0]
        fetch = min(n, max(k * 5, k)) if (tag or folder) else min(k, n)
        res = self.collection.query(
            query_embeddings=[query_emb],
            n_results=fetch,
            include=["documents", "metadatas", "distances"],
        )
        folder_prefix = folder.strip("/\\") + "/" if folder else None
        results: list[dict] = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
        ):
            if max_distance is not None and dist > max_distance:
                break  # 거리 오름차순 정렬이라 이후도 전부 초과 → 중단
            if folder_prefix and not meta["path"].startswith(folder_prefix):
                continue
            if tag and tag not in meta.get("tags", "").split(","):
                continue
            results.append(
                {
                    "path": meta["path"],
                    "heading": meta.get("heading", ""),
                    "tags": meta.get("tags", ""),
                    "created": meta.get("created", ""),
                    "snippet": doc[:500],
                    "distance": round(dist, 4),
                    "_links": meta.get("links", ""),
                }
            )
            if len(results) >= k:
                break
        if include_links and results:
            self._attach_linked(results)
        for r in results:
            r.pop("_links", None)   # 내부 필드 제거(응답엔 linked만 노출)
        return results
