# File: tests/test_index.py
# 순수 함수(청킹·슬러그·프론트매터·경로안전)는 네트워크 없이, BrainIndex는 가짜 임베더로 검증.

import os
from types import SimpleNamespace

from app.index import (
    BrainIndex,
    _collection_name,
    _collection_slug,
    _safe_rel,
    _slugify,
    chunk_markdown,
    extract_links,
    parse_frontmatter,
)


def test_헤딩_단위로_분할된다():
    text = "# 제목\n서문\n\n## 섹션A\n내용A\n\n## 섹션B\n내용B"
    chunks = chunk_markdown(text)
    assert len(chunks) == 3
    assert chunks[1].startswith("## 섹션A")
    assert "내용A" in chunks[1]


def test_헤딩_없으면_한_청크():
    text = "헤딩 없는 그냥 메모\n둘째 줄"
    assert len(chunk_markdown(text)) == 1


def test_빈_문서는_빈_리스트():
    assert chunk_markdown("   \n  \n") == []


def test_코드블록_안의_헤딩은_무시된다():
    text = "# 진짜 제목\n\n```\n# 코드 안 주석\n## 가짜 헤딩\n```\n본문 끝"
    # 코드블록 안 #로 분할되면 안 됨 → 진짜 헤딩은 '# 진짜 제목' 하나뿐이라 1청크
    assert len(chunk_markdown(text)) == 1


def test_slugify_금지문자와_공백_처리():
    assert _slugify('a/b:c?"') == "abc"
    assert _slugify("내 노트 제목") == "내-노트-제목"
    assert _slugify("   ") == "note"


def test_프론트매터_태그_날짜_추출():
    text = "---\ntitle: x\ncreated: 2026-06-07\ntags: [a, b, c]\n---\n\n# x\n본문"
    meta = parse_frontmatter(text)
    assert meta["tags"] == "a,b,c"
    assert meta["created"] == "2026-06-07"


def test_프론트매터_없으면_빈값():
    assert parse_frontmatter("# 제목\n본문") == {"title": "", "tags": "", "created": ""}


def test_위키링크_추출():
    text = "본문 [[노트 하나]] 그리고 [[둘|별칭]] 또 [[노트 하나]]"
    assert extract_links(text) == ["노트 하나", "둘"]   # 별칭 제거 + 중복 제거


def test_safe_rel_경로탈출_차단():
    assert _safe_rel("../../etc", "inbox") == "inbox"   # 상위(..) 탈출 → 기본값
    assert _safe_rel("/abs/path", "inbox") == "inbox"   # 절대경로 → 기본값
    assert _safe_rel("notes/sub") == "notes/sub"        # 정상 경로는 그대로
    assert _safe_rel("") == ""                          # 빈 입력 → 빈 값


# ---------- BrainIndex 통합 (가짜 임베더, 네트워크 0) ----------


class _FakeEmbedder:
    """길이 기반의 결정적 벡터 — ollama 없이 인덱싱/검색 경로를 통과시킨다."""

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


def test_capture_저장후_검색에_잡힌다(tmp_path):
    brain = _make_brain(tmp_path)
    path = brain.add_note("회의 결정", "## 결정\n환불 정책 변경", ["회의"], "inbox")
    assert path.startswith("inbox/")
    hits = brain.search("환불", k=5)
    assert any(h["path"] == path for h in hits)


def test_add_note_경로탈출은_inbox로_강제(tmp_path):
    brain = _make_brain(tmp_path)
    path = brain.add_note("x", "y", [], "../../escape")
    assert path.startswith("inbox/")   # 탈출 시도 → inbox로 강제


def test_delete_note_파일과_인덱스_제거(tmp_path):
    brain = _make_brain(tmp_path)
    path = brain.add_note("삭제대상", "내용", [], "inbox")
    res = brain.delete_note(path)
    assert res["file_existed"] is True
    assert not os.path.exists(os.path.join(brain.notes_path, path))


def test_그래프검색_링크된_이웃이_딸려온다(tmp_path):
    brain = _make_brain(tmp_path)
    p_ref = brain.add_note("환불 정책", "## 결정\n14일 환불.\n관련 [[온보딩]]", ["정책"], "notes")
    p_onb = brain.add_note("온보딩", "## 핵심\n첫 경험 5분", ["온보딩"], "notes")
    hits = brain.search("환불", k=3, include_links=True)
    ref = next(h for h in hits if h["path"] == p_ref)
    assert any(link["path"] == p_onb for link in ref["linked"])
    assert "_links" not in ref   # 내부 필드는 응답에서 빠진다


# ---------- 모델별 컬렉션 분리 ----------


def test_컬렉션이름_모델별로_분리된다():
    assert _collection_name("second_brain", "ollama", "bge-m3") == "second_brain__ollama_bge_m3"
    assert (
        _collection_name("second_brain", "gemini", "gemini-embedding-001")
        == "second_brain__gemini_gemini_embedding_001"
    )


def test_컬렉션이름_provider없으면_base유지():
    # 가짜 임베더처럼 provider 속성이 없을 때는 기존 base 컬렉션을 그대로 쓴다(하위호환)
    assert _collection_name("test", "", "") == "test"


def test_컬렉션슬러그_특수문자_치환():
    assert _collection_slug("ollama", "nomic-embed-text:latest") == "ollama_nomic_embed_text_latest"
    assert _collection_slug("lmstudio", "") == "lmstudio"   # 모델 비면 provider만


def test_BrainIndex_컬렉션이_모델별로_분리된다(tmp_path):
    settings = SimpleNamespace(
        notes_path=str(tmp_path / "notes"),
        chroma_path=str(tmp_path / "chroma"),
        collection_name="second_brain",
        ignore_dirs=["templates"],
    )
    os.makedirs(settings.notes_path, exist_ok=True)
    emb = _FakeEmbedder()
    emb.provider = "ollama"
    emb.model = "bge-m3"
    brain = BrainIndex(settings, emb)
    assert brain.collection_name == "second_brain__ollama_bge_m3"
