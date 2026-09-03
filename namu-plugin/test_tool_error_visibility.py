"""도구가 던진 안내문이 AI에게 실제로 닿는지 (namu-tool-error-visibility).

SDK 2.x는 도구 호출 중 난 예외를 두 갈래로 나눈다 — `ToolError`는 문구가 그대로
전달되고("예상한 실패"), 그 밖의 예외(우리가 던지는 `ValueError` 포함)는
`UnexpectedToolError`에 감싸여 `Error executing tool <이름>` 한 줄만 남고 원문은
서버 로그에만 남는다(mcp/server/mcpserver/tools/base.py). 나무는 거절 사유를 전부
`ValueError`로 던지므로, 아무 조치가 없으면 우리가 정성껏 쓴 안내문이 AI에게 한
줄도 닿지 않는다 — 2026-09-03 실제 사고(제목 길이 초과·그릇에 없는 칸을 거절당한
원인을 AI가 알 수 없어 엉뚱한 원인으로 짚었다).

`mcp_server.tool()`이 그 자리를 감싼다: **도구 호출 경로**(`mcp.call_tool`)에서만
`ValueError`를 `ToolError`로 바꿔 다시 던지고, **파이썬에서 직접 부르는 경로**
(모듈 이름 `mcp_server.namu_record` 등, 기존 검사 다수가 이 경로로 `ValueError`를
잡는다)는 원본 함수 그대로 남겨 손대지 않는다. 이 파일은 그 두 경로가 각각 맞는
예외로 갈리는지, 그리고 진짜 고장(우리가 예상 못한 예외)은 여전히 감춰지는지를
검사한다.

mcp_server는 import 시점에 실제 `~/.namu`를 건드리므로(모듈 레벨 `_ensure_db()`)
test_mcp_bowl.py와 동일하게 서브프로세스 격리(HOME을 tmp 아래 가짜 홈으로)를 쓴다.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_NAMU_PLUGIN_DIR = Path(__file__).parent

_PROBE_TEMPLATE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import mcp_server

{case_code}
"""


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "fake_home"
    home.mkdir()
    return home


def _run_probe(home: Path, case_code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("NAMU_HOME", None)

    script = _PROBE_TEMPLATE.format(plugin_dir=str(_NAMU_PLUGIN_DIR), case_code=case_code)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# ① 도구 호출 경로 — ValueError가 ToolError로 바뀌어 문구가 그대로 닿는다
# ---------------------------------------------------------------------------


def test_toolcall_delivers_the_valueerror_text(fake_home):
    result = _run_probe(
        fake_home,
        "import asyncio\n"
        "from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError\n"
        "async def main():\n"
        "    try:\n"
        "        await mcp_server.mcp.call_tool('namu_record', {\n"
        "            'bowl': 'learnings', 'summary': '시', 'reason': '시', 'body': '시',\n"
        "            'project': 'namu-agent'})\n"
        "        print('RESULT no-raise')\n"
        "    except UnexpectedToolError as e:\n"
        "        print('RESULT hidden', e)\n"
        "    except ToolError as e:\n"
        "        print('RESULT delivered', e)\n"
        "asyncio.run(main())\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT delivered" in result.stdout
    assert "'project' 칸을 받지 않습니다" in result.stdout


# ---------------------------------------------------------------------------
# ② 직접 호출 경로 — 모듈 이름은 원본 그대로라 ValueError가 그대로 난다
#    (기존 검사 다수가 `except ValueError`로 이 경로를 쓴다 — 깨지면 안 된다)
# ---------------------------------------------------------------------------


def test_direct_python_call_still_raises_valueerror(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='learnings', summary='시', reason='시',\n"
        "                            body='시', project='namu-agent')\n"
        "    print('RESULT no-raise')\n"
        "except ValueError as e:\n"
        "    print('RESULT raised', e)\n"
        "except Exception as e:\n"
        "    print('RESULT wrong-type', type(e).__name__)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT raised" in result.stdout


# ---------------------------------------------------------------------------
# ③ 예상 못 한 고장은 도구 호출 경로에서도 여전히 감춰진다
# ---------------------------------------------------------------------------


def test_toolcall_still_hides_an_unexpected_crash(fake_home):
    result = _run_probe(
        fake_home,
        "import asyncio\n"
        "from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError\n"
        "mcp_server.memo.remove = lambda *a, **k: (_ for _ in ()).throw(KeyError('내부사정'))\n"
        "async def main():\n"
        "    try:\n"
        "        await mcp_server.mcp.call_tool('namu_memo_remove',\n"
        "            {'id': '01AAAAAAAAAAAAAAAAAAAAAAAA'})\n"
        "        print('RESULT no-raise')\n"
        "    except UnexpectedToolError as e:\n"
        "        print('RESULT hidden', e)\n"
        "    except ToolError as e:\n"
        "        print('RESULT leaked', e)\n"
        "asyncio.run(main())\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT hidden" in result.stdout
    assert "내부사정" not in result.stdout


# ---------------------------------------------------------------------------
# ④ 도구 스키마는 그대로다 — 껍데기가 인자 목록·설명을 바꾸지 않는다
# ---------------------------------------------------------------------------


def test_wrapped_tool_schema_is_unchanged(fake_home):
    result = _run_probe(
        fake_home,
        "import asyncio\n"
        "async def main():\n"
        "    tools = await mcp_server.mcp.list_tools()\n"
        "    print('RESULT', len(tools))\n"
        "    rec = [t for t in tools if t.name == 'namu_record'][0]\n"
        "    print('HAS_SUMMARY', 'summary' in rec.input_schema.get('properties', {}))\n"
        "    print('HAS_CTX_LEAK', 'ctx' in rec.input_schema.get('properties', {}))\n"
        "asyncio.run(main())\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 15" in result.stdout
    assert "HAS_SUMMARY True" in result.stdout
    assert "HAS_CTX_LEAK False" in result.stdout
