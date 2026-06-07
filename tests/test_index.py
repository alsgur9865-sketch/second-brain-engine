# File: tests/test_index.py
# 순수 함수(청킹·슬러그)만 검증 — 네트워크/임베딩/DB 없이 빠르게 돈다.

from app.index import _slugify, chunk_markdown


def test_헤딩_단위로_분할된다():
    text = "# 제목\n서문\n\n## 섹션A\n내용A\n\n## 섹션B\n내용B"
    chunks = chunk_markdown(text)
    assert len(chunks) == 3
    assert chunks[1].startswith("## 섹션A")
    assert "내용A" in chunks[1]


def test_헤딩_없으면_한_청크():
    text = "헤딩 없는 그냥 메모\n둘째 줄"
    chunks = chunk_markdown(text)
    assert len(chunks) == 1


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
