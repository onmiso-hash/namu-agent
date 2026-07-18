"""mcp_server._resolve_via 단위 테스트 (namu-50 출처 꼬리표).

mcp_server는 import 시점에 실제 ~/.namu를 건드리므로(_ensure_db 등),
test_http_server.py와 동일하게 서브프로세스 격리(HOME을 tmp_path로 돌림)로
in-process import를 피한다 — 파일 상단 원칙은 그 파일의 주석을 따른다.
"""
import os
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).parent

_VIA_PROBE_TEMPLATE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import mcp_server

class _FakeRequest:
    def __init__(self, query_params):
        self.query_params = query_params

class _FakeRequestContext:
    def __init__(self, request):
        self.request = request

class _FakeCtx:
    def __init__(self, request_context):
        self.request_context = request_context

{case_code}
"""


def _run_probe(tmp_path, case_code: str) -> subprocess.CompletedProcess:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("NAMU_HOME", None)

    script = _VIA_PROBE_TEMPLATE.format(plugin_dir=str(_NAMU_PLUGIN_DIR), case_code=case_code)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


def test_resolve_via_ctx_none_returns_none(tmp_path):
    result = _run_probe(
        tmp_path,
        "print('RESULT', mcp_server._resolve_via(None))",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT None" in result.stdout


def test_resolve_via_request_none_returns_none(tmp_path):
    """stdio 경로: request_context.request가 None이면 검증 면제, None 반환."""
    result = _run_probe(
        tmp_path,
        "ctx = _FakeCtx(_FakeRequestContext(None))\n"
        "print('RESULT', mcp_server._resolve_via(ctx))",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT None" in result.stdout


def test_resolve_via_valid_client_returns_it(tmp_path):
    result = _run_probe(
        tmp_path,
        "ctx = _FakeCtx(_FakeRequestContext(_FakeRequest({'client': 'claude'})))\n"
        "print('RESULT', mcp_server._resolve_via(ctx))",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT claude" in result.stdout


def test_resolve_via_missing_client_raises_valueerror(tmp_path):
    result = _run_probe(
        tmp_path,
        "ctx = _FakeCtx(_FakeRequestContext(_FakeRequest({})))\n"
        "try:\n"
        "    mcp_server._resolve_via(ctx)\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e)[:20])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


def test_resolve_via_invalid_format_raises_valueerror(tmp_path):
    result = _run_probe(
        tmp_path,
        "ctx = _FakeCtx(_FakeRequestContext(_FakeRequest({'client': 'bad name!'})))\n"
        "try:\n"
        "    mcp_server._resolve_via(ctx)\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e)[:20])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
