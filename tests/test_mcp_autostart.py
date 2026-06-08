# File: tests/test_mcp_autostart.py
# 엔진 자동 기동(_ensure_engine/_spawn_engine) 로직을 httpx·subprocess 없이 검증.

import io

import pytest

import mcp_server


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    # 전역 플래그 초기화(테스트 간 상태 누적 방지) + 실제 대기 제거
    monkeypatch.setattr(mcp_server, "_engine_ready", False)
    monkeypatch.setattr(mcp_server.time, "sleep", lambda *_: None)


def test_엔진이_이미_떠있으면_기동하지_않는다(monkeypatch):
    spawned = []
    monkeypatch.setattr(mcp_server, "_health_ok", lambda *a, **k: True)
    monkeypatch.setattr(mcp_server, "_spawn_engine", lambda: spawned.append(1))

    mcp_server._ensure_engine()

    assert spawned == []                       # Popen 경로를 타지 않는다
    assert mcp_server._engine_ready is True


def test_엔진이_없으면_띄우고_준비를_기다린다(monkeypatch):
    spawned = []
    monkeypatch.setattr(mcp_server, "_spawn_engine", lambda: spawned.append(1))
    # 첫 체크 False(꺼짐) → 기동 → 폴링 두 번째에 True
    calls = iter([False, False, True])
    monkeypatch.setattr(mcp_server, "_health_ok", lambda *a, **k: next(calls))

    mcp_server._ensure_engine()

    assert spawned == [1]
    assert mcp_server._engine_ready is True


def test_준비_안되면_타임아웃_에러를_낸다(monkeypatch):
    monkeypatch.setattr(mcp_server, "_spawn_engine", lambda: None)
    monkeypatch.setattr(mcp_server, "_health_ok", lambda *a, **k: False)

    with pytest.raises(RuntimeError, match="자동 기동 실패"):
        mcp_server._ensure_engine(boot_timeout=0.01)

    assert mcp_server._engine_ready is False    # 실패 시 준비됨으로 표시하지 않는다


def test_엔진주소에서_host_port를_파싱해_기동한다(monkeypatch):
    captured = {}
    monkeypatch.setattr(mcp_server, "ENGINE", "http://127.0.0.1:9001")
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.StringIO())  # 로그파일 부작용 차단
    monkeypatch.setattr(
        mcp_server.subprocess, "Popen", lambda cmd, **kw: captured.update(cmd=cmd, kw=kw)
    )

    mcp_server._spawn_engine()

    cmd = captured["cmd"]
    assert "uvicorn" in cmd
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--port") + 1] == "9001"
