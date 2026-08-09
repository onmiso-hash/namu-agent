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
import new_project_gate
import task_resolve

# 새 프로젝트 게이트는 "질문을 보여준 적 없는 프로젝트 이름"을 create 단계에서
# 거절한다(new_project=True를 붙여도 첫 호출은 거절 — new_project_gate 참고).
# 아래 이름들은 이 파일 대부분의 시험이 쓰는 붙박이 시험용 프로젝트로, 게이트가
# 관심사가 아닌 시험까지 매번 "거절→대기→재호출" 두 걸음을 흉내내지 않도록
# "이미 묻고 답을 받아 왔다"로 심어 둔다. 게이트 자체를 보는 시험은 이 목록에 없는
# 이름('brand-new-proj')을 써서 진짜 문을 통과한다.
for _primed in {primed!r}:
    new_project_gate._prime_for_tests(_primed)

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


def _run_probe(
    home: Path,
    case_code: str,
    cwd: Path | None = None,
    primed: tuple[str, ...] = ("proj-new", "proj-x"),
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("NAMU_HOME", None)

    script = _PROBE_TEMPLATE.format(
        plugin_dir=str(_NAMU_PLUGIN_DIR), case_code=case_code, primed=primed
    )
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
    # 작업일지 그릇에는 log.md 줄과 task.md 한 장이 함께 담기므로(2026-08-08),
    # 일지 줄만 골라 본다 — 이 시험이 확인하려는 것은 journal 결과의 반환이다.
    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks', project='proj-x')\n"
        "logs = [e for e in r['results'] if e['tag'] != task_resolve.TASK_DOC_TAG]\n"
        "print('RESULT', r['bowl'], len(logs), logs[0]['text'])\n",
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
        "print('RESULT', sorted(set(e['project'] for e in r['results'])))\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    # 확인 대상은 "어느 방이 걸렸나"다 — 방마다 일지 줄과 설명서가 함께 나오므로
    # 건수가 아니라 방 이름으로 본다(2026-08-08 설명서 색인 이후).
    assert "RESULT ['my-proj']" in result.stdout


def test_namu_search_web_default_project_merges_all(fake_home):
    _make_pool_task(fake_home, "proj-a", "namu-1", "# log\n[결정] 2026-07-25 10:00:00 hp · a\n")
    _make_pool_task(fake_home, "proj-b", "namu-2", "# log\n[결정] 2026-07-25 10:00:00 hp · b\n")

    result = _run_probe(
        fake_home,
        "r = mcp_server.namu_search(bowl='tasks', ctx=_WEB_CTX)\n"
        "print('RESULT', sorted(set(e['project'] for e in r['results'])))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['proj-a', 'proj-b']" in result.stdout


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
        "print('RESULT', sorted(set(e['project'] for e in r['results'])))\n",
        cwd=cwd,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['proj-a', 'proj-b']" in result.stdout


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
# ⑧-2 닫기 규율(namu-66) — 닫는 말 강제 + 완료조건 미충족 경고
# ---------------------------------------------------------------------------


def _make_pool_task_with_done_when(home: Path, project: str, slug: str, done_when: list[str]):
    task_dir = home / ".namu" / "tasks" / project / slug
    task_dir.mkdir(parents=True)
    body = "\n".join(f"- [ ] {d}" for d in done_when)
    (task_dir / "task.md").write_text(
        f"# {slug} — 테스트\n\n## 목적\n테스트\n\n## 완료조건\n{body}\n", encoding="utf-8"
    )
    (task_dir / "log.md").write_text("# log\n[시작] 2026-07-30 09:00:00 hp · 시작\n", encoding="utf-8")
    return task_dir


@pytest.mark.parametrize("bad_tag", ["종료", "마무리", "끝", "Done", "close"])
def test_namu_record_rejects_closing_synonym_tags(fake_home, bad_tag):
    """'종료'·'마무리' 등은 닫는 뜻으로 쓰이지만 판정은 '완료'/'중단'만 본다 —
    저장은 성공하고 작업은 안 닫히는 조용한 어긋남이라 그 자리에서 거절한다(namu-66).

    실물: 로그 전체에 '종료' 1건·'마무리' 1건이 있었고 namu-37은 기록상 미종결로 남았다.
    """
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-30 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        f"    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', tag={bad_tag!r},"
        " summary='다 했다', reason='생략', body='생략')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "완료" in result.stdout and "중단" in result.stdout  # 쓸 수 있는 말을 알려준다

    log = (fake_home / ".namu" / "tasks" / "proj-x" / "namu-57" / "log.md").read_text(encoding="utf-8")
    assert bad_tag not in log  # 거절했으면 줄도 남지 않아야 한다


def test_namu_record_allows_normal_and_closing_tags(fake_home):
    """'완료'·'중단'·일반 태그는 그대로 통과한다(과잉 거절 방지)."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-30 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "for t in ['기록', '결정', '중단', '완료']:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-57', tag=t,"
        " summary='한 줄', reason='생략', body='생략')\n"
        "print('OK')\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK" in result.stdout


def test_namu_record_warns_when_closing_with_unmet_done_when(fake_home):
    """안 채운 완료조건이 남은 채로 닫으면 경고가 붙는다 — 다만 기록은 그대로 남는다."""
    _make_pool_task_with_done_when(fake_home, "proj-x", "namu-70", ["조건1", "조건2"])

    result = _run_probe(
        fake_home,
        "out = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-70', tag='완료',"
        " summary='끝냈다', reason='생략', body='생략')\n"
        "print('RESULT', out)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "안 채운 완료조건 2개" in result.stdout
    assert "조건1" in result.stdout and "조건2" in result.stdout

    log = (fake_home / ".namu" / "tasks" / "proj-x" / "namu-70" / "log.md").read_text(encoding="utf-8")
    assert "[완료]" in log  # 경고가 기록을 취소하지 않는다(append-only)
    assert "⚠" not in log  # 경고는 반환문에만 — 로그를 오염시키지 않는다


def test_namu_record_no_warning_when_done_when_all_checked(fake_home):
    """완료조건을 다 채우고 닫으면 경고가 없다."""
    task_dir = _make_pool_task_with_done_when(fake_home, "proj-x", "namu-70", ["조건1"])
    (task_dir / "task.md").write_text(
        "# namu-70 — 테스트\n\n## 완료조건\n- [x] 조건1\n", encoding="utf-8"
    )

    result = _run_probe(
        fake_home,
        "out = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-70', tag='완료',"
        " summary='끝냈다', reason='생략', body='생략')\n"
        "print('RESULT', out)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "안 채운 완료조건" not in result.stdout


def test_namu_record_no_warning_for_non_closing_tag(fake_home):
    """닫지 않는 줄(기록 등)에는 완료조건이 남아 있어도 경고하지 않는다 — 진행 중엔 당연하다."""
    _make_pool_task_with_done_when(fake_home, "proj-x", "namu-70", ["조건1", "조건2"])

    result = _run_probe(
        fake_home,
        "out = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-70', tag='기록',"
        " summary='진행 중', reason='생략', body='생략')\n"
        "print('RESULT', out)\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "안 채운 완료조건" not in result.stdout


# ---------------------------------------------------------------------------
# ⑨ namu_record(bowl='tasks', create=True) — 새 task 생성(namu-57 2단계 보완)
# ---------------------------------------------------------------------------


def test_namu_record_create_writes_task_and_log_and_start_line(fake_home):
    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, new_project=True, body='생략', title='새 설계 작업',"
        " purpose='웹에서 새 task를 만들 수 있어야 한다',"
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


def test_namu_record_create_strips_slug_prefix_from_title(fake_home):
    """title에 slug가 이미 들어와도 머리줄에 이름이 두 번 박히지 않는다(namu-64 결함A 원천 차단).

    실물 namu-63·64가 `# <slug> — <slug> — 설명`으로 만들어졌고 task.md는 불변이라
    사후 수정이 불가능했다 — 그래서 생성 시점에 막는다.
    """
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, new_project=True, body='생략', title='namu-99 — 이름이 이미 들어간 제목',"
        " purpose='제목 중복 차단')\n"
        "print('OK')\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    task_md = (
        fake_home / ".namu" / "tasks" / "proj-new" / "namu-99" / "task.md"
    ).read_text(encoding="utf-8")
    head = task_md.splitlines()[0]
    assert head == "# namu-99 — 이름이 이미 들어간 제목"
    assert head.count("namu-99") == 1


def test_namu_record_create_rejects_overlong_title(fake_home):
    """제목 칸에 문제 설명을 통째로 넣으면 거절한다(namu-72).

    실물: namu-70·71이 60·70자짜리 문장을 제목으로 받아 statusLine 한 줄을 뒤덮었다.
    읽는 쪽에 자르는 안전망을 뒀지만, 잘린 제목은 원문을 되찾을 수 없으므로 들어올
    때 막는다 — 조용히 잘라 저장하면 호출자가 잘못 넣은 줄 모른다(namu-66과 같은
    판단).
    """
    long_title = (
        "그릇마다 시각 표기 시간대가 다르다 — 쪽지는 한국시(+09:00), "
        "교훈은 세계시(+00:00)로 저장돼 9시간 어긋난다"
    )
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        f" create=True, new_project=True, body='생략', title={long_title!r}, purpose='설명은 여기로')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "제목이 너무 깁니다" in result.stdout
    # 거절했으면 반쯤 만들어진 task가 남아서도 안 된다.
    assert not (fake_home / ".namu" / "tasks" / "proj-new" / "namu-99").exists()


def test_namu_record_create_accepts_normal_title(fake_home):
    """상한 이하의 평범한 제목은 그대로 통과한다 — 거절 규칙이 모든 생성을 막고
    있는 것은 아닌지 확인하는 대조군."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, new_project=True, body='생략', title='작업 닫기 규율', purpose='짧은 제목은 통과')\n"
        "print('OK')\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    head = (
        fake_home / ".namu" / "tasks" / "proj-new" / "namu-99" / "task.md"
    ).read_text(encoding="utf-8").splitlines()[0]
    assert head == "# namu-99 — 작업 닫기 규율"


def test_namu_record_create_without_purpose_raises(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='proj-new', task='namu-99',"
        " create=True, new_project=True, body='생략')\n"
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
        "        mcp_server.namu_record(bowl='tasks', project='proj-x', task=bad,"
        " create=True, new_project=True, body='생략', purpose='p')\n"
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
        " create=True, new_project=True, purpose='한 번에 다음 지점까지', tag='다음',"
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
        " create=True, new_project=True, body='생략', purpose='경고 확인용')\n"
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
        " create=True, new_project=True, body='생략', purpose='p', tag='다음')\n"
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
        " new_project=True, purpose='왕복 확인용', tag='다음', text='③ 결함 수정부터')\n"
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', r['tasks'][0]['next'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "③ 결함 수정부터" in result.stdout


def test_namu_record_create_then_recall_roundtrip(fake_home):
    """create=True로 만든 task가 곧바로 namu_recall의 열린 task 목록에 나온다."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-100', create=True,"
        " new_project=True, body='생략', purpose='왕복 확인용')\n"
        "r = mcp_server.namu_recall(project='proj-x')\n"
        "print('RESULT', [t['slug'] for t in r['tasks']], r['tasks'][0]['title'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT ['namu-100'] namu-100" in result.stdout


# ---------------------------------------------------------------------------
# ⑨-보완 새 프로젝트 게이트 — 없는 project 이름은 new_project=True 없이 못 만든다
#
# 실사고: 웹채팅이 project를 매번 자유 텍스트로 받다 보니(cwd가 없어서다) AI가
# 사용자에게 묻지 않고 "onnamu-security" 같은 프로젝트 이름을 그 자리에서 지어냈다.
# CLI도 project를 명시로 넘기면 같은 문이 열리므로 플랫폼을 가리지 않고 막는다
# (namu-66이 닫는 말을 거절하는 것과 같은 패턴).
# ---------------------------------------------------------------------------


def test_namu_record_create_unknown_project_without_flag_rejected(fake_home):
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, body='생략', purpose='새 프로젝트 게이트 확인')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "proj-x" in result.stdout  # 기존 프로젝트 목록이 함께 돌아온다
    # 거절했으면 폴더가 하나도 안 생겨야 한다(반쯤 만들어진 프로젝트가 남으면 안 됨).
    assert not (fake_home / ".namu" / "tasks" / "brand-new-proj").exists()


def test_namu_record_create_rejection_carries_a_question_to_show_the_user(fake_home):
    """거절문은 "물어봐라"는 설명이 아니라 **사용자에게 그대로 보여줄 질문**이어야 한다.

    1차 판은 설명만 돌려줬고, 웹의 AI는 묻는 대신 스스로 확인 칸을 켜서 재시도했다.
    물어보는 비용(선택지를 손수 지어내는 일)이 0이어야 실제로 묻는다.
    """
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")
    _make_pool_task(fake_home, "proj-y", "namu-58", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, body='생략', purpose='질문 문안 확인')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e).replace(chr(10), '⏎'))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    # 번호 매긴 선택지 — 사용자가 고르기만 하면 되는 형태
    assert "1. proj-x" in result.stdout
    assert "2. proj-y" in result.stdout
    assert "0. 새 프로젝트로 만들기 — 'brand-new-proj'" in result.stdout
    # 우회 방법(칸 이름)을 거절문이 그 자리에서 알려주면 AI가 그걸 집어 든다.
    assert "new_project=True" not in result.stdout


def test_namu_record_create_immediate_retry_with_flag_is_rejected(fake_home):
    """거절 직후 곧바로 new_project=True로 다시 부르는 것은 막는다 — 사람이 답할
    시간이 없었으므로 AI가 스스로 정한 것이다(실사고 2회: blog-summary-bot,
    blog-auto-bot)."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "for attempt, flag in ((1, False), (2, True)):\n"
        "    try:\n"
        "        mcp_server.namu_record(bowl='tasks', project='brand-new-proj',"
        " task='namu-1', create=True, body='생략', purpose='즉시 재시도 확인',"
        " new_project=flag)\n"
        "        print('ATTEMPT', attempt, 'NO_ERROR')\n"
        "    except ValueError as e:\n"
        "        print('ATTEMPT', attempt, 'VALUEERROR', str(e).replace(chr(10), '⏎'))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "ATTEMPT 1 VALUEERROR" in result.stdout
    assert "ATTEMPT 2 VALUEERROR" in result.stdout
    assert "답할" in result.stdout  # "읽고 답할 시간이 없었습니다"
    assert not (fake_home / ".namu" / "tasks" / "brand-new-proj").exists()


def test_namu_record_create_retry_after_the_wait_succeeds(fake_home):
    """사람이 답할 만한 시간이 지난 뒤의 재시도는 통과한다 — 문턱은 지연이지 금지가
    아니다(문턱이 영구 차단이면 새 프로젝트를 영영 못 만든다)."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "import new_project_gate\n"
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, body='생략', purpose='기다린 뒤 재시도')\n"
        "except ValueError:\n"
        "    pass\n"
        "new_project_gate.COOLDOWN_SECONDS = 0  # 사람이 답하고 온 상황을 흉내낸다\n"
        "line = mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, body='생략', purpose='기다린 뒤 재시도', new_project=True)\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert (fake_home / ".namu" / "tasks" / "brand-new-proj" / "namu-1" / "task.md").exists()


def test_namu_record_create_unknown_project_with_flag_alone_is_rejected(fake_home):
    """확인 칸만 켜서 **첫 호출에** 새 프로젝트를 만드는 길은 없다.

    처음 만들 때 이 경우를 통과시켰다가 검수에서 잡혔다 — 그러면 AI는 거절문을
    읽을 것도 없이 칸만 켜면 됐고, 사용자는 질문을 한 번도 못 봤다.
    """
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, new_project=True, body='생략', purpose='새 프로젝트 게이트 확인')\n"
        "    print('NO_ERROR')\n"
        "except ValueError as e:\n"
        "    print('VALUEERROR', str(e).replace(chr(10), '⏎'))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "VALUEERROR" in result.stdout
    assert "질문을 보여준 적이 없" in result.stdout
    assert not (fake_home / ".namu" / "tasks" / "brand-new-proj").exists()


def test_namu_record_create_unknown_project_after_asking_succeeds(fake_home):
    """물어보고 답을 받아 온 흐름은 실제로 새 프로젝트를 만든다 — 게이트가 새
    프로젝트를 영영 못 만들게 하는 것은 아니라는 대조군."""
    result = _run_probe(
        fake_home,
        "new_project_gate._prime_for_tests('brand-new-proj')  # 묻고 답을 받아 온 상태\n"
        "line = mcp_server.namu_record(bowl='tasks', project='brand-new-proj', task='namu-1',"
        " create=True, new_project=True, body='생략', purpose='새 프로젝트 게이트 확인')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert (fake_home / ".namu" / "tasks" / "brand-new-proj" / "namu-1" / "task.md").exists()


def test_namu_record_create_known_project_needs_no_flag(fake_home):
    """이미 다른 task가 있는 프로젝트에 새 task를 더할 때는 new_project 없이도 통과한다
    — 게이트는 '처음 보는 프로젝트 이름'에만 걸리지, 매번 걸리면 기존 사용이 깨진다."""
    _make_pool_task(fake_home, "proj-x", "namu-57", "# log\n[시작] 2026-07-24 09:00:00 hp · 시작\n")

    result = _run_probe(
        fake_home,
        "line = mcp_server.namu_record(bowl='tasks', project='proj-x', task='namu-58',"
        " create=True, body='생략', purpose='기존 프로젝트에 추가')\n"
        "print('RESULT', repr(line))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert (fake_home / ".namu" / "tasks" / "proj-x" / "namu-58" / "task.md").exists()


# ---------------------------------------------------------------------------
# ⑨ bowl='attachments' — 첨부 기록(namu-file-upload-download 4단계)
# ---------------------------------------------------------------------------


def test_namu_record_bowl_attachments_writes_the_entry(fake_home):
    """도구 계층까지 붙어 있는지 — 저장 계층 시험(test_attachments.py)만으로는
    namu_record가 그 그릇으로 갈라지는지 알 수 없다."""
    result = _run_probe(
        fake_home,
        "mcp_server.namu_record(bowl='attachments',"
        " path='attach_file/설계.pdf', bytes=284915, status='올림',"
        " summary='설계 문서', reason='파일째 남긴다', body='원문',"
        " topic='namu-70', project='proj-x')\n"
        "r = mcp_server.namu_search(bowl='attachments')\n"
        "e = r['results'][0]\n"
        "print('RESULT', r['bowl'], r['count'], e['path'], e['bytes'], e['status'], e['task'])\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT attachments 1 attach_file/설계.pdf 284915 올림 namu-70" in result.stdout


def test_namu_record_attachments_rejects_missing_size(fake_home):
    """크기 칸이 비면 거절한다 — 비어 있으면 목록 도구가 크기를 저장소에 묻는 쪽으로
    되돌아갈 수밖에 없고, 그 순간 첨부가 통째로 내려와 격리가 뚫린다."""
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='attachments', path='attach_file/a.pdf',"
        " status='올림', summary='s', reason='r', body='b')\n"
        "    print('RESULT 거절안됨')\n"
        "except ValueError as e:\n"
        "    print('RESULT', 'bytes' in str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT True" in result.stdout


def test_namu_record_attachments_rejects_unknown_status(fake_home):
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='attachments', path='attach_file/a.pdf',"
        " bytes=10, status='삭제', summary='s', reason='r', body='b')\n"
        "    print('RESULT 거절안됨')\n"
        "except ValueError as e:\n"
        "    print('RESULT', '올림' in str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT True" in result.stdout


def test_namu_record_other_bowls_still_reject_the_attachment_fields(fake_home):
    """path·bytes는 첨부 기록 전용이다 — 다른 그릇이 받으면 그릇을 새로 만든
    이유(파일 이력이 지식베이스에 섞이지 않게)가 사라진다."""
    result = _run_probe(
        fake_home,
        "try:\n"
        "    mcp_server.namu_record(bowl='learnings', topic='t', path='attach_file/a.pdf',"
        " summary='s', reason='r', body='b')\n"
        "    print('RESULT 거절안됨')\n"
        "except ValueError as e:\n"
        "    print('RESULT', '첨부 기록' in str(e))\n",
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "RESULT True" in result.stdout


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
