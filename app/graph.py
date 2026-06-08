# File: app/graph.py
# 인덱스(Chroma)에서 그래프(노드/엣지)를 뽑는다. 사람이 보는 그래프 뷰(/graph)의 데이터원.
# 노드 = 노트(파일), 엣지 = ① [[위키링크]](방향) ② 임베딩 의미 유사도(top-k 이웃).
# LLM 불필요 — 이미 인덱싱된 메타데이터 + 임베딩 벡터만으로 계산한다.

import numpy as np

from .index import BrainIndex, _norm_name


def _note_folder(path: str) -> str:
    """노트 경로의 첫 폴더(raw/wiki/inbox…). 그래프 색상 그룹용. 없으면 빈 문자열."""
    return path.split("/", 1)[0] if "/" in path else ""


def build_graph(
    brain: BrainIndex,
    sim_top_k: int = 3,
    sim_min: float = 0.55,
) -> dict:
    """인덱스에서 노드/엣지를 만든다.

    노드: path별로 청크를 묶어 노트 1개 = 노드 1개(임베딩은 청크 평균).
    엣지: [[위키링크]](방향) + 의미 유사도(노트 평균벡터 코사인 top-k, sim_min 이상, 무방향).
    """
    got = brain.collection.get(include=["metadatas", "embeddings"])
    metas = got["metadatas"]
    embs = got["embeddings"]
    if not metas:
        return {"nodes": [], "edges": []}

    # ---- path별로 청크 묶기: 메타 대표값 + 임베딩 모으기 ----
    by_path: dict[str, dict] = {}
    vecs: dict[str, list] = {}
    for meta, emb in zip(metas, embs, strict=True):
        path = meta["path"]
        if path not in by_path:
            by_path[path] = {
                "title": meta.get("title", ""),
                "tags": meta.get("tags", ""),
                "type": meta.get("type", ""),
                "relations": meta.get("relations", ""),
                "links": meta.get("links", ""),
            }
            vecs[path] = []
        vecs[path].append(emb)

    paths = list(by_path)
    # 노트별 평균벡터 → 정규화(코사인 유사도용)
    mat = np.array([np.mean(vecs[p], axis=0) for p in paths], dtype=float)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = mat / norms

    # ---- 노드 ----
    nodes = []
    for p in paths:
        info = by_path[p]
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        nodes.append(
            {
                "id": p,
                "label": info["title"] or stem,
                "folder": _note_folder(p),
                "type": info["type"],
                "tags": [t for t in info["tags"].split(",") if t],
            }
        )

    edges: list[dict] = []
    seen_edge: set = set()

    # ---- 엣지 ①: 위키링크(방향) — 이름→경로는 인덱스가 이미 풀어준다 ----
    name_to_path = brain._name_index()
    for p in paths:
        for raw in (by_path[p]["links"] or "").split(","):
            target = raw.strip()
            if not target:
                continue
            tp = name_to_path.get(_norm_name(target))
            if tp and tp != p:
                key = ("link", p, tp)
                if key not in seen_edge:
                    seen_edge.add(key)
                    edges.append({"source": p, "target": tp, "type": "link"})

    # ---- 엣지 ②: 의미 관계(frontmatter relations, 무관 제외) ----
    # relations는 사전순 앞 노트에 'target_path::관계'로 저장. 무관은 엣지를 안 그리되,
    # 분류된 쌍(무관 포함)은 의미유사 회색 선도 억제한다(이미 판단된 쌍의 중복 표시 방지).
    rel_suppress: set = set()
    for p in paths:
        for item in (by_path[p]["relations"] or "").split(","):
            target, sep, label = item.partition("::")
            target, label = target.strip(), label.strip()
            if not sep or target not in by_path or target == p:
                continue
            rel_suppress.add(tuple(sorted((p, target))))
            if label == "무관":
                continue
            key = ("rel", *sorted((p, target)))
            if key not in seen_edge:
                seen_edge.add(key)
                edges.append(
                    {"source": p, "target": target, "type": "relation", "label": label}
                )

    # ---- 엣지 ③: 의미 유사도(무방향 top-k) ----
    # 전수 비교(N×N 행렬) 대신 각 노트의 평균벡터로 Chroma ANN 질의 → 가까운 후보만 받아,
    # 그 후보에 대해서만 정확한 코사인을 다시 잰다. O(N²) → O(N·후보수)로 확장성 확보.
    path_idx = {p: i for i, p in enumerate(paths)}
    fetch = min(sim_top_k * 10 + 20, len(metas))  # 청크 단위로 반환되므로 노트 후보를 넉넉히
    for i, p in enumerate(paths):
        res = brain.collection.query(
            query_embeddings=[mat[i].tolist()],
            n_results=fetch,
            include=["metadatas"],
        )
        scored: list[tuple[float, str]] = []
        seen_cand: set = set()
        for m in res["metadatas"][0]:
            cp = m["path"]
            if cp == p or cp in seen_cand:
                continue
            seen_cand.add(cp)
            j = path_idx.get(cp)
            if j is None:
                continue
            score = float(unit[i] @ unit[j])  # 후보만 정확한 코사인 재계산(근사 아님)
            if score >= sim_min:
                scored.append((score, cp))
        scored.sort(reverse=True)
        for score, cp in scored[:sim_top_k]:
            if tuple(sorted((p, cp))) in rel_suppress:
                continue  # 의미 관계가 분류된 쌍은 라벨 엣지로 대체(무관이면 생략)
            key = ("sim", *sorted((p, cp)))  # 무방향 → 정렬해 중복 제거
            if key in seen_edge:
                continue
            seen_edge.add(key)
            edges.append(
                {"source": p, "target": cp, "type": "similar", "weight": round(score, 3)}
            )

    return {"nodes": nodes, "edges": edges}
