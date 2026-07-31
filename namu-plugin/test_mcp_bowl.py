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
        "mcp_server.namu_record(bowl='learnings', task='t1', outcome='success',"
        " reason='r1', summary='요약1', body='생략')\n"
        "mcp_server.namu_record(bowl='learnings', task='t2', outcome='failure',"
        " reason='r2', summary='요약2', body='생략')\n"
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
        " text='구현 진행중', reason='생략', body='생략', tag='결정')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    log_text = (fake_home / ".namu" / "tasks" / "proj-x" / "namu-57" / "log.md").read_text(encoding="utf-8")
    lines = log_text.splitlines()
    assert lines[-1].startswith("[결정] ")
    assert lines[-1].endswith(" hp · 구현 진행중")

    printed = result.stdout.strip().split("RESULT ", 1)[1]
    returned_line = ast.literal_eval(printed)
    # 옛 이름으로 부르면 반환문 뒤에 '어디로 옮겼는지' 안내가 붙는다(namu-65).
    assert returned_line.splitlines()[0] == lines[-1]


def test_namu_record_bowl_tasks_stdio_default_project(tmp_path, fake_home):
    _make_pool_task(fake_home, "my-proj", "namu-57", "# log\n")
    cwd = tmp_path / "my-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', task='namu-57', text='cwd 기본값', reason='생략', body='생략')\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='nope-999', text='x', reason='생략', body='생략')\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='ghost-task', text='x', reason='생략', body='생략')\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='x', reason='생략', body='생략')\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='   ', reason='생략', body='생략')\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', text='x', reason='생략', body='생략', tag='bad]tag')\n"
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
        "    mcp_server.namu_record(bowl='tasks', task='namu-57', text='x', reason='생략', body='생략', ctx=_WEB_CTX)\n"
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
        "    mcp_server.namu_record(bowl='tasks', project='*', task='namu-57', text='x', reason='생략', body='생략')\n"
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
        " text='웹에서 기록', reason='생략', body='생략', ctx=_WEB_CTX)\n"
        "print('LINE', repr(line))\n"
        "r = mcp_server.namu_search(bowl='tasks', project='proj-x', via='claude')\n"
        "print('SEARCH', r['count'], r['results'][0]['text'], r['results'][0]['via'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "(via claude)" in result.stdout
    assert "SEARCH 1 웹에서 기록 claude" in result.stdout


# ---------------------------------------------------------------------------
# ⑧ namu_recall — 기존 2키 불변 + 신규 'tasks' 키(namu-57 2단계 보완)
# ---------------------------------------------------------------------------


def test_namu_recall_existing_two_keys_unchanged(fake_home):
    """profile/learnings 키의 형태·내용이 project 인자 추가 전과 동일해야 한다(하위 호환).

    키 집합 자체는 그릇이 늘면 함께 는다 — namu-56에서 'memo'가 추가됐다. 여기서
    지키는 것은 "기존 키가 사라지거나 모양이 바뀌지 않는다"이지 "키가 영원히 3개"가
    아니다.
    """
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='learnings', task='t1', outcome='success',"
        " reason='r1', summary='요약1', body='생략')\n"
        "r = mcp_server.namu_recall(query='t1')\n"
        "print('RESULT', sorted(r.keys()), r['learnings'][0]['task'], isinstance(r['profile'], list))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['learnings', 'memo', 'profile', 'tasks'] t1 True" in result.stdout


def test_namu_recall_lists_open_tasks_with_full_next(fake_home):
    _make_pool_task(
        fake_home, "proj-x", "namu-57",
        "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n"
        "[다음] 2026-07-25 10:00:00 hp · 여기부터 이어서 하기 아주 길게 설명하는 재진입 지점\n",
    )
    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', len(r['tasks']), r['tasks'][0]['project'], r['tasks'][0]['slug'],"
        " repr(r['tasks'][0]['next']))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert (
        "RESULT 1 proj-x namu-57 '여기부터 이어서 하기 아주 길게 설명하는 재진입 지점'"
        in result.stdout
    )


def test_namu_recall_next_is_none_when_no_next_tag(fake_home):
    _make_pool_task(
        fake_home, "proj-x", "namu-57",
        "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n",
    )
    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', r['tasks'][0]['next'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT None" in result.stdout


def test_namu_recall_stdio_default_project_is_cwd(tmp_path, fake_home):
    _make_pool_task(fake_home, "my-proj", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · in my-proj\n")
    _make_pool_task(fake_home, "other-proj", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · in other-proj\n")
    cwd = tmp_path / "my-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_recall()\n"
        "print('RESULT', [t['project'] for t in r['tasks']])\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['my-proj']" in result.stdout


def test_namu_recall_web_default_project_merges_all(fake_home):
    _make_pool_task(fake_home, "proj-a", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · a\n")
    _make_pool_task(fake_home, "proj-b", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · b\n")

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_recall(ctx=_WEB_CTX)\n"
        "print('RESULT', sorted(t['project'] for t in r['tasks']))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['proj-a', 'proj-b']" in result.stdout


def test_namu_recall_project_star_merges_all_even_on_stdio(tmp_path, fake_home):
    _make_pool_task(fake_home, "proj-a", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · a\n")
    _make_pool_task(fake_home, "proj-b", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · b\n")
    cwd = tmp_path / "unrelated-proj"
    cwd.mkdir()

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_recall(project='*')\n"
        "print('RESULT', sorted(t['project'] for t in r['tasks']))\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['proj-a', 'proj-b']" in result.stdout


# ---------------------------------------------------------------------------
# ⑨ namu_record(bowl='tasks', create=True) — 새 task 생성(namu-57 2단계 보완)
# ---------------------------------------------------------------------------


def test_namu_record_create_writes_task_and_log_and_start_line(fake_home):
    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, body='생략', title='새 설계 작업', purpose='웹에서 새 task를 만들 수 있어야 한다',"
        " done_when=['조건1', '조건2'])\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    task_dir = fake_home / ".namu" / "tasks" / "proj-new" / "namu-99"
    task_md = (task_dir / "task.md").read_text(encoding="utf-8")
    log_md = (task_dir / "log.md").read_text(encoding="utf-8")

    assert "# namu-99 — 새 설계 작업" in task_md
    assert "웹에서 새 task를 만들 수 있어야 한다" in task_md
    assert "- [ ] 조건1" in task_md
    assert "- [ ] 조건2" in task_md
    assert not (task_dir / "context.hp.md").exists()  # context.<machine>.md는 만들지 않는다
    assert any(f.name.startswith("context.") for f in task_dir.iterdir()) is False

    lines = log_md.splitlines()
    assert lines[-1].startswith("[시작] ")
    assert lines[-1].endswith(" · 작업 생성, 목적·완료조건 확정")

    assert str(task_dir) in result.stdout
    assert "[시작]" in result.stdout


def test_namu_record_create_without_purpose_raises(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99', create=True, body='생략')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert not (fake_home / ".namu" / "tasks" / "proj-new").exists()


def test_namu_record_create_existing_slug_raises(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', create=True, body='생략',"
        " purpose='덮어쓰기 시도')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    # 기존 log.md가 덮어써지지 않았는지 확인
    log_text = (fake_home / ".namu" / "tasks" / "proj-x" / "namu-57" / "log.md").read_text(encoding="utf-8")
    assert log_text == "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n"


def test_namu_record_missing_slug_without_create_still_raises(fake_home):
    """create 없이 없는 슬러그면 기존과 동일하게 거절(안내 문구 포함)."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='ghost', text='x', reason='생략', body='생략')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "create=True" in result.stdout


def test_namu_record_create_path_traversal_slug_rejected(fake_home):
    result = _run_probe(
        fake_home,
        "for bad in ('../evil', 'a/b', 'a\\\\b', '..'):\n"
        "    try:\n"
        "        mcp_server.namu_record(bowl='tasks', project='proj-x', task=bad, create=True, body='생략',"
        " purpose='p')\n"
        "        print('NO_ERROR', bad)\n"
        "    except ValueError as e:\n"
        "        print('VALUEERROR', bad)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "NO_ERROR" not in result.stdout
    assert result.stdout.count("VALUEERROR") == 4
    # 실제로 부모 경로 밖으로 폴더가 새지 않았는지 확인
    assert not (fake_home / ".namu" / "evil").exists()
    assert not (fake_home / ".namu" / "tasks" / "evil").exists()


def test_namu_record_create_with_text_appends_next_line(fake_home):
    """namu-62 ③: create=True에 넘긴 tag/text가 버려지지 않고 두 번째 줄로 들어간다.
    예전에는 조용히 사라져 `[다음]`이 빈 task가 남았다(실측 2건).
    """
    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, purpose='한 번에 다음 지점까지', tag='다음',"
        " text='①user_repo.py 읽기\\n②범위 합의')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    log_md = (fake_home / ".namu" / "tasks" / "proj-new" / "namu-99" / "log.md").read_text(
        encoding="utf-8"
    )
    lines = [ln for ln in log_md.splitlines() if ln.startswith("[")]
    assert lines[-2].startswith("[시작] ")
    assert lines[-1].startswith("[다음] ")
    # 개행은 한 줄로 접힌다(log.md는 줄 단위 파일)
    assert lines[-1].endswith(" · ①user_repo.py 읽기 ②범위 합의")
    # 반환문에도 두 줄이 다 보이고, 경고는 붙지 않는다
    assert "[다음]" in result.stdout
    assert "이어갈 지점" not in result.stdout


def test_namu_record_create_without_text_warns_about_missing_next(fake_home):
    """text 없이 만들면 생성은 되지만 반환문이 [다음] 누락을 경고한다(namu-62 ③)."""
    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-98',"
        " create=True, body='생략', purpose='경고 확인용')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    log_md = (fake_home / ".namu" / "tasks" / "proj-new" / "namu-98" / "log.md").read_text(
        encoding="utf-8"
    )
    log_lines = [ln for ln in log_md.splitlines() if ln.startswith("[")]
    assert len(log_lines) == 1 and log_lines[0].startswith("[시작] ")
    assert "이어갈 지점" in result.stdout
    # 반환문에 "한 번 더 호출" 안내가 들어 있어야 한다(repr 출력이라 따옴표는 escape됨)
    assert "namu_record" in result.stdout and "한 번 더" in result.stdout


def test_namu_record_create_tag_without_text_raises_before_folder(fake_home):
    """tag만 주고 text가 비면 거절하고, 껍데기 폴더도 남기지 않는다(namu-62 ③)."""
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-97',"
        " create=True, body='생략', purpose='p', tag='다음')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert not (fake_home / ".namu" / "tasks" / "proj-new" / "namu-97").exists()


def test_namu_record_create_with_text_shows_next_in_recall(fake_home):
    """생성 한 번으로 브리핑의 '다음'까지 채워진다 — 이 결함의 실제 피해 지점."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-101', create=True,"
        " purpose='왕복 확인용', tag='다음', text='③ 결함 수정부터')\n"
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', r['tasks'][0]['next'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "③ 결함 수정부터" in result.stdout


def test_namu_record_create_then_recall_roundtrip(fake_home):
    """create=True로 만든 task가 곧바로 namu_recall의 열린 task 목록에 나온다."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-100', create=True, body='생략',"
        " purpose='왕복 확인용')\n"
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', [t['slug'] for t in r['tasks']], r['tasks'][0]['title'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['namu-100'] namu-100" in result.stdout


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
