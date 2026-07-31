"""mcp_server의 memo 그릇 도구 계층 테스트 (namu-56).

memo.py(코어)는 test_memo.py가 덮으므로, 여기서는 **도구 계층에서만 결정되는 것**을
본다: record의 bowl 라우팅, 떼기 전용 도구, recall 반환에 memo가 실리는지, 그리고
memo가 learnings 그릇을 건드리지 않는지.

mcp_server는 import 시점에 실제 `~/.namu`를 만지므로(_ensure_db 등) test_mcp_bowl.py와
동일하게 서브프로세스 격리(HOME을 tmp 아래 가짜 홈으로)를 쓴다.
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
# ① 붙이기 — namu_record(bowl='memo')
# ---------------------------------------------------------------------------


def test_record_bowl_memo_appends_and_returns_id(fake_home):
    result = _run_probe(
        fake_home,
        "mid = mcp_server.namu_record(bowl='memo', summary='영화 8시 20분', reason='생략', body='영화 8시 20분')\n"
        "import memo\n"
        "entries = memo.load_all()\n"
        "print('RESULT', len(entries), entries[0]['summary'], entries[0]['id'] == mid)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 1 영화 8시 20분 True" in result.stdout


def test_record_bowl_memo_requires_text(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='memo')\n"
        "    print('RESULT no-raise')\n"
        "except ValueError as e:\n"
        "    print('RESULT raised')\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT raised" in result.stdout


def test_record_bowl_memo_does_not_touch_learnings(fake_home):
    """이 그릇의 존재 이유 — 일회성 메모가 지식베이스에 섞이면 안 된다."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='memo', summary='일회성 메모', reason='생략', body='일회성 메모')\n"
        "import db, config as cfg\n"
        "from contextlib import closing\n"
        "with closing(mcp_server.get_conn()) as conn:\n"
        "    hits = db.search_bowl(conn, bowl='learnings', query='일회성')\n"
        "print('RESULT', hits['count'], cfg.LEARNINGS_YAML_PATH.exists())\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 0 False" in result.stdout


def test_record_bowl_memo_ignores_default_kind(fake_home):
    """kind 기본값('lesson')이 그대로 넘어와도 memo 경로는 모순으로 보지 않는다 —
    호출자가 memo에 kind를 줄 이유가 없다(tasks와 같은 취급)."""
    result = _run_probe(
        fake_home,
        "mid = mcp_server.namu_record(bowl='memo', summary='kind 무관', reason='생략', body='kind 무관', kind='lesson')\n"
        "print('RESULT', bool(mid))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT True" in result.stdout


# ---------------------------------------------------------------------------
# ② 떼기 — namu_memo_remove
# ---------------------------------------------------------------------------


def test_memo_remove_deletes_only_that_memo(fake_home):
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='memo', summary='남을 것', reason='생략', body='남을 것')\n"
        "target = mcp_server.namu_record(bowl='memo', summary='뗄 것', reason='생략', body='뗄 것')\n"
        "msg = mcp_server.namu_memo_remove(target)\n"
        "import memo\n"
        "left = [m['summary'] for m in memo.load_all()]\n"
        "print('RESULT', left, '뗐습니다' in msg)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['남을 것'] True" in result.stdout


def test_memo_remove_unknown_id_raises(fake_home):
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='memo', summary='하나', reason='생략', body='하나')\n"
        "try:\n"
        "    mcp_server.namu_memo_remove('ZZZZZZZZ')\n"
        "    print('RESULT no-raise')\n"
        "except ValueError:\n"
        "    import memo\n"
        "    print('RESULT raised', len(memo.load_all()))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT raised 1" in result.stdout


def test_memo_remove_is_exposed_as_its_own_tool(fake_home):
    """떼기는 record의 인자가 아니라 별도 도구다(2026-07-25 사용자 결정) —
    도구 목록에 실제로 등록됐는지 확인한다."""
    result = _run_probe(
        fake_home,
        "import anyio\n"
        "tools = anyio.run(mcp_server.mcp.list_tools)\n"
        "names = sorted(t.name for t in tools)\n"
        "print('RESULT', 'namu_memo_remove' in names, len(names))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT True 5" in result.stdout


# ---------------------------------------------------------------------------
# ③ 조회 — recall 반환 + search(bowl='memo')
# ---------------------------------------------------------------------------


def test_recall_returns_memo_key(fake_home):
    """웹에는 세션 훅이 없어 recall 반환이 메모의 유일한 노출 경로다."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='memo', summary='첫째', reason='생략', body='첫째')\n"
        "mcp_server.namu_record(bowl='memo', summary='둘째', reason='생략', body='둘째')\n"
        "r = mcp_server.namu_recall()\n"
        "print('RESULT', [m['summary'] for m in r['memo']], sorted(r.keys()))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['첫째', '둘째'] ['learnings', 'memo', 'profile', 'tasks']" in result.stdout


def test_search_bowl_memo_filters_by_query(fake_home):
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='memo', summary='영화 8시 20분', reason='생략', body='영화 8시 20분')\n"
        "mcp_server.namu_record(bowl='memo', summary='세탁소 전화', reason='생략', body='세탁소 전화')\n"
        "r = mcp_server.namu_search(bowl='memo', query='영화')\n"
        "print('RESULT', r['count'], r['results'][0]['summary'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 1 영화 8시 20분" in result.stdout
