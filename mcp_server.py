# File: mcp_server.py
# Claude Code(에이전트)용 MCP 서버. remember/recall을 엔진 HTTP로 프록시한다(stdio transport).
# 엔진(app.main)이 Chroma·노트의 단일 소유자 → 이 서버는 상태를 갖지 않는 얇은 프록시일 뿐.
# 등록: .mcp.json 또는 `claude mcp add`. 단독 실행: python mcp_server.py
#
# 엔진은 떠 있지 않으면 첫 도구 호출 때 자동으로 띄운다(_ensure_engine) — 사용자가 직접
# uvicorn을 켤 필요가 없다. 한 번 뜬 엔진은 detached라 계속 떠 있어 다음 세션도 즉시 쓴다.
#
# 엔진 주소/키는 환경변수로:
#   SECOND_BRAIN_API  엔진 베이스 URL (기본 http://127.0.0.1:8000)
#   SB_API_KEY        엔진에 API 키가 걸려 있으면 그 값(비면 인증 없음)
#
# 엔진 설정(어느 뇌를 볼지 등)은 프로젝트 폴더의 .env에서 읽는다(app/config.py).

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

# 기본 주소는 127.0.0.1 — Windows에서 localhost는 IPv6(::1) 우선 해석이라, 엔진이
# IPv4만 들으면 연결이 실패한다(http=000). IPv4를 명시해 그 함정을 피한다.
ENGINE = os.environ.get("SECOND_BRAIN_API", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("SB_API_KEY", "")

_PROJECT_DIR = Path(__file__).resolve().parent
_ENGINE_LOG = _PROJECT_DIR / "engine.log"

mcp = FastMCP("second-brain")

_engine_ready = False  # 한 프로세스에서 엔진 준비 확인/기동은 한 번만(매 호출 폭주 방지)


def _health_ok(timeout: float = 1.5) -> bool:
    """엔진 /health가 HTTP 200이면 True. 연결 거부·타임아웃은 '엔진 꺼짐'으로 보고 False.

    /health는 임베딩 백엔드가 죽어 있어도(degraded) HTTP 200을 주므로, 이건 'uvicorn이
    응답하는가'(liveness)만 본다. ollama 자체 문제는 실제 도구 호출에서 드러난다.
    """
    try:
        return httpx.get(f"{ENGINE}/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def _spawn_engine() -> None:
    """uvicorn 엔진을 detached 백그라운드로 띄운다(콘솔창 없음, 부모 죽어도 생존).

    cwd를 프로젝트 폴더로 둬 .env가 자동 로드되고 app 패키지가 임포트된다. host/port는
    ENGINE에서 파싱한다. 같은 venv 파이썬(sys.executable)을 쓴다.
    """
    parsed = urlparse(ENGINE)
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 8000)
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port]
    log = open(_ENGINE_LOG, "a", encoding="utf-8")  # detached 엔진 수명만큼 열어둔다(with 안 씀)
    kwargs: dict = {"cwd": str(_PROJECT_DIR), "stdout": log, "stderr": log}
    if os.name == "nt":
        # DETACHED_PROCESS(0x08) | CREATE_NO_WINDOW(0x08000000):
        # 콘솔창 없이, 부모(MCP 서버) 종료와 무관하게 살아남는다.
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True  # POSIX: 부모 세션과 분리
    subprocess.Popen(cmd, **kwargs)


def _ensure_engine(boot_timeout: float = 60.0) -> None:
    """엔진이 떠 있는지 확인하고, 없으면 자동으로 띄워 준비될 때까지 기다린다.

    한 프로세스에서 기동은 한 번만 시도한다(전역 플래그). 매 도구 호출 직전에 부른다.
    엔진 startup은 노트 인덱싱(brain.sync)까지 끝나야 /health가 200을 주므로, 처음 쓰는
    큰 vault의 첫 전체 인덱싱을 고려해 폴링 타임아웃을 넉넉히 둔다(이후엔 증분이라 빠름).
    """
    global _engine_ready
    if _engine_ready:
        return
    if _health_ok():  # 이미 떠 있으면(다른 세션이 띄웠든) 재사용
        _engine_ready = True
        return
    _spawn_engine()
    deadline = time.monotonic() + boot_timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if _health_ok(timeout=3.0):  # 콜드 로딩 중 응답이 느릴 수 있어 길게
            _engine_ready = True
            return
    raise RuntimeError(
        f"엔진 자동 기동 실패({boot_timeout:.0f}s 초과). 로그: {_ENGINE_LOG} / "
        f"ollama가 떠 있는지 확인하세요. 노트가 많으면 첫 인덱싱이 오래 걸릴 수 있으니, "
        f"한 번 직접 `uvicorn app.main:app`을 띄워 인덱싱을 마친 뒤 다시 시도하세요."
    )


def _post(path: str, payload: dict) -> dict:
    """엔진의 POST 엔드포인트를 호출. API 키가 있으면 X-API-Key 헤더를 붙인다."""
    _ensure_engine()
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    r = httpx.post(f"{ENGINE}{path}", json=payload, headers=headers, timeout=180)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict) -> dict:
    """엔진의 GET 엔드포인트를 호출. API 키가 있으면 X-API-Key 헤더를 붙인다."""
    _ensure_engine()
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    r = httpx.get(f"{ENGINE}{path}", params=params, headers=headers, timeout=120)
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


@mcp.tool()
def cleanup_candidates(threshold: float = 0.85, max_pairs: int = 20) -> dict:
    """중복으로 의심되는 기억 쌍을 찾는다(임베딩 유사도). 기억을 정리하기 전 '뭐가 겹치나' 확인용.

    threshold: 이 유사도 이상만(기본 0.85, 높을수록 더 확실한 중복). 각 쌍에 두 노트의
    경로·제목·스니펫이 온다. 진짜 중복이라고 판단되면 cleanup_merge로 합친다.
    """
    return _get("/cleanup/candidates", {"threshold": threshold, "max_pairs": max_pairs})


@mcp.tool()
def cleanup_merge(
    sources: list[str],
    title: str = "",
    content: str = "",
    folder: str = "decisions",
    tags: list[str] | None = None,
) -> dict:
    """중복 노트 여러 개(sources, 2개 이상)를 하나로 병합한다. 원본은 삭제된다.

    content를 직접 주면 그 내용으로 합치고(권장: 통합문을 네가 작성), 비우면 엔진이
    로컬 LLM(gemma)으로 자동 요약한다. folder/tags로 합친 노트를 분류한다.
    """
    payload: dict = {"sources": sources, "folder": folder, "tags": tags or []}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content
    return _post("/cleanup/merge", payload)


if __name__ == "__main__":
    mcp.run()  # 인자 없으면 stdio transport (Claude Code 로컬 연결용)
