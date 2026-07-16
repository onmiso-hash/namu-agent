"""http_server.py 단위 테스트 (namu-44).

mcp_server를 import하는 테스트는 금지 — mcp_server는 import 시점에 실제 ~/.namu를
만지므로(_ensure_db 등), 여기서는 순수 로직(설정 검증·인증·디바운스 미들웨어·도구 제한)만
검증한다. 미들웨어는 더미 ASGI inner app으로, restrict_tools는 더미 FastMCP 유사
객체(list_tools/remove_tool만 흉내)로 검증하고, build_app()/main()(내부에서
`import mcp_server`)은 이 테스트 스코프에서 다루지 않는다(라이브 스모크로 별도 검증).
"""
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import http_server


async def _dummy_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


# ---------------------------------------------------------------------------
# config.http_settings
# ---------------------------------------------------------------------------

def _clear_http_env(monkeypatch):
    for name in (
        "NAMU_HTTP_TOKEN",
        "NAMU_HTTP_PATH_SECRET",
        "NAMU_HTTP_HOST",
        "NAMU_HTTP_PORT",
        "NAMU_HTTP_PULL_INTERVAL",
        "NAMU_HTTP_ALLOW_NOAUTH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_http_settings_defaults(monkeypatch):
    _clear_http_env(monkeypatch)
    s = cfg.http_settings()
    assert s == {
        "token": "",
        "path_secret": "",
        "host": "127.0.0.1",
        "port": 8765,
        "pull_interval": 60.0,
        "allow_noauth": False,
    }


def test_http_settings_reads_env(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_TOKEN", "  secrettoken  ")
    monkeypatch.setenv("NAMU_HTTP_PATH_SECRET", "  mysecret  ")
    monkeypatch.setenv("NAMU_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("NAMU_HTTP_PORT", "9999")
    monkeypatch.setenv("NAMU_HTTP_PULL_INTERVAL", "5.5")
    monkeypatch.setenv("NAMU_HTTP_ALLOW_NOAUTH", "1")
    s = cfg.http_settings()
    assert s["token"] == "secrettoken"
    assert s["path_secret"] == "mysecret"
    assert s["host"] == "0.0.0.0"
    assert s["port"] == 9999
    assert s["pull_interval"] == 5.5
    assert s["allow_noauth"] is True


def test_http_settings_bad_port_raises(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_PORT", "not-a-number")
    with pytest.raises(ValueError):
        cfg.http_settings()


def test_http_settings_path_secret_with_slash_raises(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_PATH_SECRET", "foo/bar")
    with pytest.raises(ValueError):
        cfg.http_settings()


# ---------------------------------------------------------------------------
# validate_settings
# ---------------------------------------------------------------------------

def _settings(**overrides) -> dict:
    base = {
        "token": "",
        "path_secret": "",
        "host": "127.0.0.1",
        "port": 8765,
        "pull_interval": 60.0,
        "allow_noauth": False,
    }
    base.update(overrides)
    return base


def test_validate_settings_rejects_noauth():
    with pytest.raises(SystemExit) as exc_info:
        http_server.validate_settings(_settings())
    assert exc_info.value.code == 2


def test_validate_settings_allows_explicit_noauth():
    http_server.validate_settings(_settings(allow_noauth=True))  # SystemExit 없이 통과


def test_validate_settings_allows_token_only():
    http_server.validate_settings(_settings(token="t"))


def test_validate_settings_allows_path_secret_only():
    http_server.validate_settings(_settings(path_secret="s"))


# ---------------------------------------------------------------------------
# AuthMiddleware
# ---------------------------------------------------------------------------

def test_auth_middleware_x_api_key_match():
    app = http_server.AuthMiddleware(_dummy_app, token="tok123")
    client = TestClient(app)
    r = client.get("/mcp", headers={"x-api-key": "tok123"})
    assert r.status_code == 200


def test_auth_middleware_x_api_key_mismatch():
    app = http_server.AuthMiddleware(_dummy_app, token="tok123")
    client = TestClient(app)
    r = client.get("/mcp", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_auth_middleware_bearer_match():
    app = http_server.AuthMiddleware(_dummy_app, token="tok123")
    client = TestClient(app)
    r = client.get("/mcp", headers={"Authorization": "Bearer tok123"})
    assert r.status_code == 200


def test_auth_middleware_no_header():
    app = http_server.AuthMiddleware(_dummy_app, token="tok123")
    client = TestClient(app)
    r = client.get("/mcp")
    assert r.status_code == 401


def test_auth_middleware_no_token_configured_passes_through():
    app = http_server.AuthMiddleware(_dummy_app, token="")
    client = TestClient(app)
    r = client.get("/mcp")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# PullDebounceMiddleware
# ---------------------------------------------------------------------------

def test_pull_debounce_first_call_then_skips(monkeypatch):
    calls = []
    monkeypatch.setattr(http_server.memory_sync, "sync_pull", lambda: calls.append(1) or True)
    monkeypatch.setattr(http_server, "_last_pull", 0.0)

    app = http_server.PullDebounceMiddleware(_dummy_app, pull_interval=60.0)
    client = TestClient(app)

    r1 = client.get("/mcp")
    assert r1.status_code == 200
    assert len(calls) == 1

    r2 = client.get("/mcp")
    assert r2.status_code == 200
    assert len(calls) == 1  # 60초 이내 재요청 — 디바운스로 스킵


def test_pull_debounce_recalls_after_interval_elapsed(monkeypatch):
    """시간 경과를 흉내: 모듈 상태 _last_pull을 과거로 되돌려 다음 요청에서
    재호출되는지 확인 (실제 time.sleep 없이 시간 경과를 시뮬레이션)."""
    calls = []
    monkeypatch.setattr(http_server.memory_sync, "sync_pull", lambda: calls.append(1) or True)
    monkeypatch.setattr(http_server, "_last_pull", 0.0)

    app = http_server.PullDebounceMiddleware(_dummy_app, pull_interval=60.0)
    client = TestClient(app)

    client.get("/mcp")
    assert len(calls) == 1
    client.get("/mcp")
    assert len(calls) == 1

    monkeypatch.setattr(http_server, "_last_pull", 0.0)  # 경과 시뮬레이션
    client.get("/mcp")
    assert len(calls) == 2


def test_pull_debounce_interval_zero_pulls_every_request(monkeypatch):
    calls = []
    monkeypatch.setattr(http_server.memory_sync, "sync_pull", lambda: calls.append(1) or True)
    monkeypatch.setattr(http_server, "_last_pull", 0.0)

    app = http_server.PullDebounceMiddleware(_dummy_app, pull_interval=0.0)
    client = TestClient(app)

    client.get("/mcp")
    client.get("/mcp")
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# restrict_tools (설계 §8 보완 — 원격 HTTP에는 recall/record/search 3종만 노출)
# ---------------------------------------------------------------------------

class _DummyTool:
    def __init__(self, name: str):
        self.name = name


class _DummyFastMCP:
    """FastMCP를 흉내내는 최소 더미 — restrict_tools가 쓰는 두 공개 메서드
    (list_tools async, remove_tool sync)만 구현한다. mcp_server import 없이
    도구 제한 로직만 격리 검증하기 위함."""

    def __init__(self, names):
        self._tools = {name: _DummyTool(name) for name in names}
        self.removed_calls: list[str] = []

    async def list_tools(self):
        return list(self._tools.values())

    def remove_tool(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        del self._tools[name]
        self.removed_calls.append(name)


def test_restrict_tools_removes_non_allowed():
    dummy = _DummyFastMCP(["namu_recall", "namu_record", "namu_search", "namu_sync_setup"])
    http_server.restrict_tools(dummy, frozenset({"namu_recall", "namu_record", "namu_search"}))
    assert set(dummy._tools.keys()) == {"namu_recall", "namu_record", "namu_search"}
    assert dummy.removed_calls == ["namu_sync_setup"]


def test_restrict_tools_noop_when_already_restricted():
    dummy = _DummyFastMCP(["namu_recall", "namu_record", "namu_search"])
    http_server.restrict_tools(dummy, frozenset({"namu_recall", "namu_record", "namu_search"}))
    assert set(dummy._tools.keys()) == {"namu_recall", "namu_record", "namu_search"}
    assert dummy.removed_calls == []


def test_http_exposed_tools_excludes_sync_setup():
    assert http_server.HTTP_EXPOSED_TOOLS == frozenset(
        {"namu_recall", "namu_record", "namu_search"}
    )
    assert "namu_sync_setup" not in http_server.HTTP_EXPOSED_TOOLS


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
