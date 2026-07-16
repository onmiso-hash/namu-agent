"""http_server.py 단위 테스트 (namu-44, 421 갭 수정으로 namu-44 연장).

mcp_server를 in-process import하는 테스트는 원칙적으로 금지 — mcp_server는 import
시점에 실제 ~/.namu를 만지므로(_ensure_db 등), 여기서는 순수 로직(설정 검증·인증·
디바운스 미들웨어·도구 제한·_build_transport_security)만 검증한다. 미들웨어는 더미
ASGI inner app으로, restrict_tools는 더미 FastMCP 유사 객체(list_tools/remove_tool만
흉내)로 검증한다.

예외 1건: build_app()의 실제 배선(streamable_http_app() 생성 후 Host 헤더 검증이
421→200으로 바뀌는지)은 mcp_server import 없이는 검증할 수 없다 — 이 구간만
서브프로세스로 격리해(HOME을 tmp_path로 돌려 실제 ~/.namu 무영향) 별도로 다룬다
(하단 `test_build_app_*` 참조). main()은 여전히 이 테스트 스코프에서 다루지 않는다
(라이브 스모크로 별도 검증).
"""
import os
import subprocess
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
        "NAMU_HTTP_ALLOWED_HOSTS",
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
        "allowed_hosts": [],
    }


def test_http_settings_reads_env(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_TOKEN", "  secrettoken  ")
    monkeypatch.setenv("NAMU_HTTP_PATH_SECRET", "  mysecret  ")
    monkeypatch.setenv("NAMU_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("NAMU_HTTP_PORT", "9999")
    monkeypatch.setenv("NAMU_HTTP_PULL_INTERVAL", "5.5")
    monkeypatch.setenv("NAMU_HTTP_ALLOW_NOAUTH", "1")
    monkeypatch.setenv("NAMU_HTTP_ALLOWED_HOSTS", "tunnel.example.com")
    s = cfg.http_settings()
    assert s["token"] == "secrettoken"
    assert s["path_secret"] == "mysecret"
    assert s["host"] == "0.0.0.0"
    assert s["port"] == 9999
    assert s["pull_interval"] == 5.5
    assert s["allow_noauth"] is True
    assert s["allowed_hosts"] == ["tunnel.example.com"]


# ---------------------------------------------------------------------------
# config.http_settings — NAMU_HTTP_ALLOWED_HOSTS 파싱 (421 갭 수정, namu-44 연장)
# ---------------------------------------------------------------------------

def test_http_settings_allowed_hosts_unset_is_empty_list(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.delenv("NAMU_HTTP_ALLOWED_HOSTS", raising=False)
    s = cfg.http_settings()
    assert s["allowed_hosts"] == []


def test_http_settings_allowed_hosts_blank_is_empty_list(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_ALLOWED_HOSTS", "   ")
    s = cfg.http_settings()
    assert s["allowed_hosts"] == []


def test_http_settings_allowed_hosts_single(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_ALLOWED_HOSTS", "tunnel.example.com")
    s = cfg.http_settings()
    assert s["allowed_hosts"] == ["tunnel.example.com"]


def test_http_settings_allowed_hosts_multiple_with_whitespace_and_blanks(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv(
        "NAMU_HTTP_ALLOWED_HOSTS", " tunnel.example.com , , other.example.org  "
    )
    s = cfg.http_settings()
    assert s["allowed_hosts"] == ["tunnel.example.com", "other.example.org"]


def test_http_settings_allowed_hosts_star(monkeypatch):
    _clear_http_env(monkeypatch)
    monkeypatch.setenv("NAMU_HTTP_ALLOWED_HOSTS", "*")
    s = cfg.http_settings()
    assert s["allowed_hosts"] == ["*"]


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


# ---------------------------------------------------------------------------
# _build_transport_security (터널 421 Misdirected Request 수정, namu-44 연장)
#
# mcp_server import 없이 순수 로직만 검증한다(파일 상단 docstring 원칙). 실제
# streamable_http_app()에 반영되는지(빌드 배선 + 421→200 회귀)는 아래
# test_build_app_allowed_hosts_* 에서 subprocess 격리로 별도 검증한다.
# ---------------------------------------------------------------------------

def test_build_transport_security_empty_returns_none():
    assert http_server._build_transport_security([]) is None


def test_build_transport_security_star_disables_protection():
    settings = http_server._build_transport_security(["*"])
    assert settings.enable_dns_rebinding_protection is False


def test_build_transport_security_adds_to_localhost_defaults_not_replaces():
    settings = http_server._build_transport_security(["tunnel.example.com"])
    assert settings.enable_dns_rebinding_protection is True
    assert settings.allowed_hosts == [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
        "tunnel.example.com",
    ]
    # allowed_origins는 FastMCP localhost 기본값 그대로 (지시서 스펙)
    assert settings.allowed_origins == [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]


def test_build_transport_security_multiple_hosts_all_added():
    settings = http_server._build_transport_security(["a.example.com", "b.example.com"])
    assert settings.allowed_hosts == [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
        "a.example.com",
        "b.example.com",
    ]


# ---------------------------------------------------------------------------
# build_app() 배선 + 421→200 회귀 (실측 확정 갭 수정)
#
# mcp_server를 실제로 import해야 하는 구간이라(streamable_http_app() 생성 등) 파일
# 상단 원칙(mcp_server import 금지)의 예외로 서브프로세스 격리를 쓴다 — HOME을
# tmp_path로 돌려 실제 ~/.namu를 건드리지 않는다(test_config_home_routing.py와
# 동일 패턴). 각 assert마다 새 서브프로세스를 쓰는 이유: FastMCP의
# StreamableHTTPSessionManager는 인스턴스당 run()을 한 번만 허용해 같은 프로세스에서
# build_app()을 두 번 부르면(session_manager가 mcp_server.mcp에 귀속된 싱글턴이라)
# "can only be called once per instance" RuntimeError로 실패한다(실측 확인).
# ---------------------------------------------------------------------------

_NAMU_PLUGIN_DIR = Path(__file__).parent

_BUILD_APP_PROBE = """
import os, sys
sys.path.insert(0, {plugin_dir!r})
import config as cfg
import http_server
from starlette.testclient import TestClient

settings = cfg.http_settings()
app = http_server.build_app(settings)
host_header = os.environ["PROBE_HOST_HEADER"]
req = dict(json={{
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {{
        "protocolVersion": "2024-11-05",
        "capabilities": {{}},
        "clientInfo": {{"name": "probe", "version": "0"}},
    }},
}})
with TestClient(app) as client:
    r = client.post(
        "/mcp",
        headers={{"Host": host_header, "Accept": "application/json, text/event-stream"}},
        **req,
    )
    print("PROBE_STATUS", r.status_code)
""".format(plugin_dir=str(_NAMU_PLUGIN_DIR))


def _run_build_app_probe(tmp_path, host_header: str, allowed_hosts_env: str | None) -> int:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("NAMU_HOME", None)
    env.pop("NAMU_HTTP_TOKEN", None)
    env.pop("NAMU_HTTP_PATH_SECRET", None)
    if allowed_hosts_env is None:
        env.pop("NAMU_HTTP_ALLOWED_HOSTS", None)
    else:
        env["NAMU_HTTP_ALLOWED_HOSTS"] = allowed_hosts_env
    env["PROBE_HOST_HEADER"] = host_header

    result = subprocess.run(
        [sys.executable, "-c", _BUILD_APP_PROBE],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    for line in result.stdout.splitlines():
        if line.startswith("PROBE_STATUS"):
            return int(line.split()[1])
    raise AssertionError(f"PROBE_STATUS not found in stdout: {result.stdout}")


def test_build_app_rejects_tunnel_host_without_allowed_hosts(tmp_path):
    """현행 동작 보존 확인: NAMU_HTTP_ALLOWED_HOSTS 미설정이면 터널 Host 헤더는
    여전히 421 Misdirected Request로 거부된다 (라이브 검증에서 발견된 갭 그 자체)."""
    status = _run_build_app_probe(tmp_path, "tunnel.example.com", allowed_hosts_env=None)
    assert status == 421


def test_build_app_allows_tunnel_host_when_added_to_allowed_hosts(tmp_path):
    """갭 수정 확인: NAMU_HTTP_ALLOWED_HOSTS에 터널 도메인을 추가하면 같은 Host
    헤더 요청이 421→200으로 바뀐다."""
    status = _run_build_app_probe(
        tmp_path, "tunnel.example.com", allowed_hosts_env="tunnel.example.com"
    )
    assert status == 200


def test_build_app_allowed_hosts_star_allows_any_host(tmp_path):
    status = _run_build_app_probe(
        tmp_path, "anything-goes.example.org", allowed_hosts_env="*"
    )
    assert status == 200


def test_build_app_localhost_still_works_after_allowed_hosts_added(tmp_path):
    """로컬 curl 스모크 회귀 방지: allowed_hosts에 터널 도메인을 추가해도 FastMCP
    localhost 기본값(127.0.0.1 등)은 계속 통과해야 한다(대체 금지, 합집합 스펙)."""
    status = _run_build_app_probe(
        tmp_path, "127.0.0.1:8765", allowed_hosts_env="tunnel.example.com"
    )
    assert status == 200


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
