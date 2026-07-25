"""mcp_server.namu_search/namu_record 그릇(bowl) 계층 테스트 (namu-57 2단계 2단위 —
도구 계층). db.py/task_resolve.py(코어)는 1단위에서 이미 검증됐다(test_db_bowl.py) —
여기서는 도구 계층의 정책(project 기본값 stdio/웹 분기, bowl='tasks' 기록 경로,
슬러그 해석, 하위 호환)만 다룬다.

mcp_server는 import 시점에 실제 ~/.namu를 만지므로(_ensure_db 등), test_mcp_via.py와
동일하게 서브프로세스 격리(HOME을 tmp_path 아래 가짜 홈으로 돌림)로 in-process import를
피한다. namu_record(bowl='tasks')는 실제 log.md에 파일 I/O를 하므로 이 격리가 특히
필수다(과거 테스트가 실 HOME에 가짜 프로젝트 폴더 22개를 흘린 사고 있음).
"""
import ast
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

class _FakeRequest:
    def __init__(self, query_params):
        self.query_params = query_params

class _FakeRequestContext:
    def __init__(self, request):
        self.request = request

class _FakeCtx:
    def __init__(self, request_context):
        self.request_context = request_context

# ctx.request_context.request가 not-None이면 웹(stateless HTTP) 경로로 취급된다
# (mcp_server._is_web_request와 동일 판정 기준).
_WEB_CTX = _FakeCtx(_FakeRequestContext(_FakeRequest({{'client': 'claude'}})))

{case_code}
"""


@pytest.fixture
def fake_home(tmp_path):
    """실제 ~/.namu를 건드리지 않도록 HOME을 tmp 아래 가짜 홈으로 격리(namu-33 교훈)."""
    home = tmp_path / "fake_home"
    home.mkdir()
    return home


def _make_pool_task(home: Path, project: str, slug: str, log_body: str) -> Path:
    task_dir = home / ".namu" / "tasks" / project / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    (task_dir / "log.md").write_text(log_body, encoding="utf-8")
    return task_dir


def _run_probe(home: Path, case_code: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("NAMU_HOME", None)

    script = _PROBE_TEMPLATE.format(plugin_dir=str(_NAMU_PLUGIN_DIR), case_code=case_code)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(cwd) if cwd else str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


# ---------------------------------------------------------------------------
# ① 기존 namu_search(query=...) 호출이 그대로 동작 — 하위 호환
# ---------------------------------------------------------------------------


def test_namu_search_query_only_call_unchanged(fake_home):
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(task='t1', outcome='success', reason='r1')\n"
        "mcp_server.namu_record(task='t2', outcome='failure', reason='r2')\n"
        "r = mcp_server.namu_search('t1')\n"  # 위치인자: query 그대로 첫 자리
        "print('RESULT', r['bowl'], r['count'], r['results'][0]['task'], 'summary' in r)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT learnings 1 t1 True" in result.stdout


# ---------------------------------------------------------------------------
# ② bowl='tasks'가 journal 결과를 반환
# ---------------------------------------------------------------------------


def test_namu_search_bowl_tasks_returns_journal(fake_home):
    _make_pool_task(
        fake_home, "proj-x", "namu-57",
        "# log\n[결정] 2026-07-25 10:00:00 hp · 코어 조회\n",
    )
    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks', project='proj-x')\n"
        "print('RESULT', r['bowl'], r['count'], r['results'][0]['text'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT tasks 1 코어 조회" in result.stdout


# ---------------------------------------------------------------------------
# ③ project 기본값 — stdio는 현재 프로젝트, 웹은 전체 합침
# ---------------------------------------------------------------------------


def test_namu_search_stdio_default_project_is_cwd(tmp_path, fake_home):
    _make_pool_task(fake_home, "my-proj", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · in my-proj\n")
    _make_pool_task(fake_home, "other-proj", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · in other-proj\n")
    cwd = tmp_path / "my-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks')\n"
        "print('RESULT', r['count'], [e['project'] for e in r['results']])\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 1 ['my-proj']" in result.stdout


def test_namu_search_web_default_project_merges_all(fake_home):
    _make_pool_task(fake_home, "proj-a", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · a\n")
    _make_pool_task(fake_home, "proj-b", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · b\n")

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks', ctx=_WEB_CTX)\n"
        "print('RESULT', r['count'], sorted(e['project'] for e in r['results']))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 2 ['proj-a', 'proj-b']" in result.stdout


# ---------------------------------------------------------------------------
# ④ project='*' — 양쪽 모두에서 명시적 전체 조회
# ---------------------------------------------------------------------------


def test_namu_search_project_star_merges_all_even_on_stdio(tmp_path, fake_home):
    _make_pool_task(fake_home, "proj-a", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · a\n")
    _make_pool_task(fake_home, "proj-b", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · b\n")
    cwd = tmp_path / "unrelated-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks', project='*')\n"
        "print('RESULT', r['count'], sorted(e['project'] for e in r['results']))\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT 2 ['proj-a', 'proj-b']" in result.stdout


# ---------------------------------------------------------------------------
# ⑤ namu_record(bowl='tasks')가 log.md에 정확한 형식으로 append하고 그 줄을 반환
# ---------------------------------------------------------------------------


def test_namu_record_bowl_tasks_appends_and_returns_line(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57',"
        " text='구현 진행중', tag='결정')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    log_text = (fake_home / ".namu" / "tasks" / "proj-x" / "namu-57" / "log.md").read_text(encoding="utf-8")
    lines = log_text.splitlines()
    assert lines[-1].startswith("[결정] ")
    assert lines[-1].endswith(" hp · 구현 진행중")

    printed = result.stdout.strip().split("RESULT ", 1)[1]
    returned_line = ast.literal_eval(printed)
    assert returned_line == lines[-1]


def test_namu_record_bowl_tasks_stdio_default_project(tmp_path, fake_home):
    _make_pool_task(fake_home, "my-proj", "namu-57", "# log\n")
    cwd = tmp_path / "my-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', task='namu-57', text='cwd 기본값')\n"
        "print('RESULT', repr(line))\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    log_text = (fake_home / ".namu" / "tasks" / "my-proj" / "namu-57" / "log.md").read_text(encoding="utf-8")
    assert "cwd 기본값" in log_text


# ---------------------------------------------------------------------------
# ⑥ 없는 슬러그·모호한 슬러그·빈 text·']' 포함 tag → ValueError
# ---------------------------------------------------------------------------


def test_namu_record_bowl_tasks_missing_slug_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='nope-999', text='x')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "namu-57" in result.stdout  # 열린 task 힌트로 곁들여짐


def test_namu_record_bowl_tasks_missing_slug_creates_no_folder(fake_home):
    """없는 슬러그로 폴더를 새로 만들지 않는다(task.md 없이 log만 생기면 유령 task)."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n")

    _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='ghost-task', text='x')\n"
        "except ValueError:\n"
        "    pass\n"
        "print('DONE')\n",
    )
    tasks_root = fake_home / ".namu" / "tasks" / "proj-x"
    assert sorted(p.name for p in tasks_root.iterdir()) == ["namu-57"]


def test_namu_record_bowl_tasks_ambiguous_slug_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57-core", "# log\n")
    _make_pool_task(fake_home, "proj-x", "namu-57-web", "# log\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='x')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "namu-57-core" in result.stdout and "namu-57-web" in result.stdout


def test_namu_record_bowl_tasks_empty_text_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='   ')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


def test_namu_record_bowl_tasks_tag_with_bracket_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='x', tag='bad]tag')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


def test_namu_record_bowl_tasks_web_without_project_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', task='namu-57', text='x', ctx=_WEB_CTX)\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


def test_namu_record_bowl_tasks_project_star_raises(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='*', task='namu-57', text='x')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


def test_namu_record_bowl_kind_contradiction_raises(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='learnings', kind='fact', subject='s', statement='st', source='src')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout


# ---------------------------------------------------------------------------
# ⑦ via가 있으면 (via <라벨>) 꼬리표가 붙고, search(via=...)로 왕복된다
# ---------------------------------------------------------------------------


def test_namu_record_bowl_tasks_via_roundtrip(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57',"
        " text='웹에서 기록', ctx=_WEB_CTX)\n"
        "print('LINE', repr(line))\n"
        "r = mcp_server.namu_search(bowl='tasks', project='proj-x', via='claude')\n"
        "print('SEARCH', r['count'], r['results'][0]['text'], r['results'][0]['via'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "(via claude)" in result.stdout
    assert "SEARCH 1 웹에서 기록 claude" in result.stdout


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
