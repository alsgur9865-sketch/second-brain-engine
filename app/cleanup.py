# File: app/cleanup.py
# 자동정리의 '탐지' 단계. 인덱스에서 '거의 같은' 노트 쌍을 임베딩 유사도로 찾는다.
# LLM 불필요 — graph.py와 같은 노트 평균벡터 코사인 계산. 병합 판단·실행은 호출자(에이전트).

import numpy as np

from .index import BrainIndex


def find_duplicate_candidates(
    brain: BrainIndex,
    threshold: float = 0.85,
    max_pairs: int = 20,
) -> list[dict]:
    """유사도가 threshold 이상인 노트 쌍을 점수 내림차순으로 반환.

    각 쌍에 두 노트의 path/title/snippet을 담아, 에이전트가 바로 진짜 중복인지
    판단하고 cleanup_merge로 합칠 수 있게 한다. graph.py의 의미유사(0.55)보다
    높은 기본값(0.85)을 써서 '유사'가 아니라 '거의 중복'만 잡는다.
    """
    got = brain.collection.get(include=["metadatas", "embeddings", "documents"])
    metas = got["metadatas"]
    embs = got["embeddings"]
    docs = got["documents"]
    if not metas:
        return []

    # path별로 청크 묶기 (graph.py와 동일한 노트 단위 평균벡터)
    by_path: dict[str, dict] = {}
    vecs: dict[str, list] = {}
    for meta, emb, doc in zip(metas, embs, docs, strict=True):
        path = meta["path"]
        if path not in by_path:
            by_path[path] = {
                "title": meta.get("title", "") or path.rsplit("/", 1)[-1],
                "snippet": (doc or "")[:200],
            }
            vecs[path] = []
        vecs[path].append(emb)

    paths = list(by_path)
    if len(paths) < 2:
        return []

    mat = np.array([np.mean(vecs[p], axis=0) for p in paths], dtype=float)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = mat / norms

    # 전수 비교(N×N 행렬) 대신 각 노트의 평균벡터로 Chroma ANN 질의 → 가까운 후보만 받아,
    # 그 후보에 대해서만 정확한 코사인을 다시 잰다. O(N²) → O(N·후보수)로 확장성 확보.
    path_idx = {p: i for i, p in enumerate(paths)}
    fetch = min(max_pairs * 4 + 30, len(metas))  # 청크 단위 반환이라 후보를 넉넉히
    pairs: list[dict] = []
    pair_seen: set = set()
    for i, p in enumerate(paths):
        res = brain.collection.query(
            query_embeddings=[mat[i].tolist()],
            n_results=fetch,
            include=["metadatas"],
        )
        for m in res["metadatas"][0]:
            cp = m["path"]
            if cp == p:
                continue
            key = tuple(sorted((p, cp)))  # 무방향 → 정렬해 쌍 중복 제거
            if key in pair_seen:
                continue
            j = path_idx.get(cp)
            if j is None:
                continue
            score = float(unit[i] @ unit[j])  # 후보만 정확한 코사인 재계산(근사 아님)
            if score < threshold:
                continue
            pair_seen.add(key)
            a, b = key
            pairs.append(
                {
                    "score": round(score, 3),
                    "a": {"path": a, **by_path[a]},
                    "b": {"path": b, **by_path[b]},
                }
            )
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs[:max_pairs]
