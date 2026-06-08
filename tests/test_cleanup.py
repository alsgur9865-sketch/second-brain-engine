# File: tests/test_cleanup.py
# 자동정리 '탐지'(find_duplicate_candidates)를 가짜 임베더(네트워크 0)로 검증.

import os
from types import SimpleNamespace

from app.cleanup import find_duplicate_candidates
from app.index import BrainIndex


class _FakeEmbedder:
    """길이 기반 결정적 벡터 — 길이가 비슷한 노트끼리 코사인 유사도가 높아진다."""

    def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


def _make_brain(tmp_path):
    settings = SimpleNamespace(
        notes_path=str(tmp_path / "notes"),
        chroma_path=str(tmp_path / "chroma"),
        collection_name="test",
        ignore_dirs=["templates"],
    )
    os.makedirs(settings.notes_path, exist_ok=True)
    return BrainIndex(settings, _FakeEmbedder())


def test_노트_2개_미만이면_후보없음(tmp_path):
    brain = _make_brain(tmp_path)
    assert find_duplicate_candidates(brain) == []
    brain.add_note("하나뿐", "내용", [], "inbox")
    assert find_duplicate_candidates(brain) == []


def test_유사한_노트가_후보로_잡힌다(tmp_path):
    brain = _make_brain(tmp_path)
    # 길이가 같은 두 노트 → 가짜 임베더에서 코사인 유사도 ~1.0
    p1 = brain.add_note("환불 정책 A", "환불은 14일 이내 가능하다", [], "inbox")
    p2 = brain.add_note("환불 정책 B", "환불은 14일 안에 가능하다", [], "inbox")
    cands = find_duplicate_candidates(brain, threshold=0.5)
    assert len(cands) >= 1
    assert {cands[0]["a"]["path"], cands[0]["b"]["path"]} == {p1, p2}
    assert "snippet" in cands[0]["a"] and "title" in cands[0]["a"]


def test_threshold_초과_요구하면_후보없음(tmp_path):
    brain = _make_brain(tmp_path)
    brain.add_note("노트1", "어떤 내용", [], "inbox")
    brain.add_note("노트2", "다른 내용", [], "inbox")
    # 코사인 유사도는 최대 1.0 → 1.01 이상을 요구하면 무조건 0개
    assert find_duplicate_candidates(brain, threshold=1.01) == []


def test_max_pairs로_개수를_제한한다(tmp_path):
    brain = _make_brain(tmp_path)
    for i in range(4):
        brain.add_note(f"노트{i}", "비슷한 길이의 내용입니다", [], "inbox")
    cands = find_duplicate_candidates(brain, threshold=0.0, max_pairs=2)
    assert len(cands) == 2


def _read(brain, rel):
    with open(os.path.join(brain.notes_path, rel), encoding="utf-8") as f:
        return f.read()


def test_relink_병합후_옛링크가_새제목으로_치환된다(tmp_path):
    brain = _make_brain(tmp_path)
    # A가 '포트 바꾸기'를 일반 링크와 별칭 링크 둘 다로 가리킨다
    body = "[[포트 바꾸기]] 와 [[포트 바꾸기|포트]]"
    a = brain.add_note("노트 A", body, [], "inbox")
    b = brain.add_note("포트 바꾸기", "포트 변경 내용", [], "inbox")

    old_names = brain.collect_link_names([b])   # 삭제 '전'에 옛 이름 수집
    brain.delete_note(b)
    new = brain.add_note("엔진 포트 변경 방법", "통합 내용", [], "inbox")
    changed = brain.relink(old_names, "엔진 포트 변경 방법", skip={new})

    assert a in changed and new not in changed   # A만 바뀌고 새 노트는 건드리지 않음
    text = _read(brain, a)
    assert "[[엔진 포트 변경 방법]]" in text       # 일반·별칭 링크 모두 단순 치환
    assert "포트 바꾸기" not in text


def test_relink_관련없는_링크는_그대로다(tmp_path):
    brain = _make_brain(tmp_path)
    a = brain.add_note("노트 A", "이건 [[다른 노트]] 링크", [], "inbox")
    changed = brain.relink({"포트 바꾸기"}, "엔진 포트 변경 방법", skip=set())
    assert changed == []
    assert "[[다른 노트]]" in _read(brain, a)
