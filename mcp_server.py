# File: mcp_server.py
# Claude Code(에이전트)용 MCP 서버. remember/recall을 엔진 HTTP로 프록시한다(stdio transport).
# 엔진(app.main)이 Chroma·노트의 단일 소유자 → 이 서버는 상태를 갖지 않는 얇은 프록시일 뿐.
# 등록: .mcp.json 또는 `claude mcp add`. 단독 실행: python mcp_server.py
#
# 엔진 주소/키는 환경변수로:
#   SECOND_BRAIN_API  엔진 베이스 URL (기본 http://localhost:8000)
#   SB_API_KEY        엔진에 API 키가 걸려 있으면 그 값(비면 인증 없음)

import os

import httpx
from mcp.server.fastmcp import FastMCP

ENGINE = os.environ.get("SECOND_BRAIN_API", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("SB_API_KEY", "")

mcp = FastMCP("second-brain")


def _post(path: str, payload: dict) -> dict:
    """엔진의 POST 엔드포인트를 호출. API 키가 있으면 X-API-Key 헤더를 붙인다."""
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    r = httpx.post(f"{ENGINE}{path}", json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def remember(
    title: str,
    content: str,
    tags: list[str] | None = None,
    folder: str = "inbox",
) -> dict:
    """기억을 세컨드 브레인에 저장한다. 대화에서 알게 된 사실·결정·할 일을 정리해 넣을 때 사용.

    title: 한 줄 제목. content: 본문(마크다운, [[다른 노트]] 링크 가능).
    tags: 분류 태그. folder: 저장 폴더(기본 inbox). 저장 즉시 검색 대상이 된다.
    """
    return _post(
        "/capture",
        {"title": title, "content": content, "tags": tags or [], "folder": folder},
    )


@mcp.tool()
def recall(query: str, k: int = 5, tag: str = "", folder: str = "") -> dict:
    """세컨드 브레인에서 의미로 회상한다. '저번에 뭐라고 했더라' 싶을 때 키워드가 아닌 의미로 검색.

    query: 찾고 싶은 내용(자연어). k: 결과 수. tag/folder: 좁히기(선택, 비우면 전체).
    각 결과엔 [[위키링크]]로 이어진 이웃 노트가 linked로 함께 온다(연결된 기억 덩어리).
    """
    payload: dict = {"query": query, "k": k}
    if tag:
        payload["tag"] = tag
    if folder:
        payload["folder"] = folder
    return _post("/search", payload)


if __name__ == "__main__":
    mcp.run()  # 인자 없으면 stdio transport (Claude Code 로컬 연결용)
