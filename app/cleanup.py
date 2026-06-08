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
    sims = unit @ unit.T  # 정규화됐으므로 내적 = 코사인 유사도

    pairs: list[dict] = []
    n = len(paths)
    for i in range(n):
        for j in range(i + 1, n):  # 무방향 → 상삼각만
            score = float(sims[i][j])
            if score < threshold:
                continue
            a, b = paths[i], paths[j]
            pairs.append(
                {
                    "score": round(score, 3),
                    "a": {"path": a, **by_path[a]},
                    "b": {"path": b, **by_path[b]},
                }
            )
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs[:max_pairs]
