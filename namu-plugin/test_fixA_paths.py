"""경로 탈출 막기 — 방 이름·작업 이름(항목 1)과 웹의 파일 경로 칸(항목 2).

2026-09-25 검토에서 재현된 사고 둘을 그대로 다시 돌린다.

  ① `namu_task_move(task='memory', to='web-project', project='..')` 한 번에 교훈 원본
     폴더(`~/.namu/memory`)가 남의 방 안으로 옮겨졌다. `project='/'`면 방 목록이 통째로
     "작업"으로 보여 방 하나가 다른 방 안으로 들어갔다.
  ② 웹 요청에서도 `namu_upload_file(file_path=…)`가 서버 PC의 아무 파일이나 읽어
     올렸고, `namu_download_file(save_to=…)`가 아무 자리에나 썼다. 덤으로 확장자 없는
     파일 이름(`.bashrc`)을 폴더로 읽어 그 이름의 폴더를 만들었다.

mcp_server는 import 시점에 `~/.namu`를 만지므로 가짜 홈에서 서브프로세스로 돈다
(test_mcp_memo.py와 같은 방식).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).parent
sys.path.insert(0, str(_PLUGIN))

import project_policy  # noqa: E402

_PROBE = """
import sys
sys.path.insert(0, {plugin!r})
import mcp_server, memory_sync
memory_sync.sync_push = lambda *a, **k: None
mcp_server.memory_sync.sync_push = lambda *a, **k: None

class _Req:
    query_params = {{'client': 'claude'}}
class _RC:
    request = _Req()
class _Ctx:
    request_context = _RC()
web = _Ctx()

def expect_reject(fn, *needles):
    try:
        fn()
    except ValueError as exc:
        msg = str(exc)
        for n in needles:
            assert n in msg, (n, msg)
        print('REJECTED')
        return
    raise AssertionError('통과해 버렸다')

{case}
"""


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    nm = h / ".namu"
    (nm / "memory").mkdir(parents=True)
    (nm / "memory" / "learnings.yaml").write_text("", encoding="utf-8")
    for room in ("proj-a", "web-project"):
        t = nm / "tasks" / room / "t1"
        t.mkdir(parents=True)
        (t / "task.md").write_text("# t1 — 제목\n", encoding="utf-8")
        (t / "log.md").write_text("[시작] 2026-09-01 10:00:00 hp · s\n", encoding="utf-8")
    return h


def _run(home: Path, case: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    env.pop("NAMU_HOME", None)
    return subprocess.run(
        [sys.executable, "-c", _PROBE.format(plugin=str(_PLUGIN), case=case)],
        cwd=str(cwd or home), env=env, capture_output=True, text=True, timeout=60,
    )


# ── 규칙 자체 (순수 함수) ──────────────────────────────────────────────


@pytest.mark.parametrize("bad", [
    "", "  ", ".", "..", "/", "a/b", "..\\x", "C:", "a:b", ".git", ".pin.hp",
    "a\nb", "a\x00b", "a\tb", None,
])
def test_validate_room_name_rejects_escapes(bad):
    with pytest.raises(ValueError):
        project_policy.validate_room_name(bad)


@pytest.mark.parametrize("good", [
    # 지금 개인 풀에 실제로 있는 방 이름들(2026-09-25 `ls ~/.namu/tasks/`)
    "naite", "namu-agent", "namu-cloud-routing", "onnamu-project", "project",
    "web-project",
    # 사람이 연 폴더 이름이라 한글·공백·가운데 점도 방이 될 수 있다
    "내 프로젝트", "v1.2", "a..b",
])
def test_validate_room_name_accepts_real_rooms(good):
    assert project_policy.validate_room_name(good) == good


def test_validate_room_name_accepts_everything_cloud_accepts():
    """클라우드 `_validate_project_name`을 통과하는 이름은 코어도 통과해야 한다 —
    클라우드가 코어 함수로 갈아타도 기존 회원 방이 막히지 않는다."""
    import re
    cloud = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    for name in ("a", "namu-agent", "x.y_z-1", "A" * 64):
        assert cloud.match(name) and ".." not in name
        assert project_policy.validate_room_name(name) == name


def test_create_project_rejects_dotdot_before_room_list():
    with pytest.raises(ValueError, match="쓸 수 없습니다"):
        project_policy.resolve_create_project(
            "..", is_web=True, existing=["proj-a"],
        )


# ── ① 도구 계층: 사고 재현 ─────────────────────────────────────────────


def test_move_with_dotdot_project_cannot_move_memory_folder(home):
    r = _run(home, """
expect_reject(lambda: mcp_server.namu_task_move(task='memory', to='web-project', project='..', ctx=web), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_move(task='memory', to='web-project', project='..'), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_move(task='proj-a', to='web-project', project='/', ctx=web), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_move(task='t1', to='..', project='proj-a', ctx=web), '쓸 수 없습니다')
""")
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("REJECTED") == 4
    nm = home / ".namu"
    assert (nm / "memory" / "learnings.yaml").exists()
    assert sorted(p.name for p in (nm / "tasks").iterdir()) == ["proj-a", "web-project"]
    assert sorted(p.name for p in (nm / "tasks" / "web-project").iterdir()) == ["t1"]


def test_record_pin_unpin_reject_dotdot_project(home):
    r = _run(home, """
expect_reject(lambda: mcp_server.namu_record(bowl='tasks', project='..', topic='memory', summary='x', reason='생략', body='생략', ctx=web), '쓸 수 없습니다')
expect_reject(lambda: mcp_server._record_task_entry('..', 'memory', 'x', None, None, None), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_pin(task='memory', project='..'), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_unpin(project='..'), '쓸 수 없습니다')
expect_reject(lambda: mcp_server.namu_task_unpin(project='a/b'), '쓸 수 없습니다')
""")
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("REJECTED") == 5
    assert not (home / ".namu" / "memory" / "log.md").exists()
    assert not (home / ".namu" / ".pin.hp").exists()


def test_task_slug_rejects_dot_names_and_separators(home):
    (home / ".namu" / "tasks" / "proj-a" / ".git").mkdir()
    r = _run(home, """
for bad in ('.', '..', '.git', 't1/../..', 'a\\\\b'):
    expect_reject(lambda: mcp_server._resolve_task_slug('proj-a', bad), 'topic')
print('OK', mcp_server._resolve_task_slug('proj-a', 't1'))
""")
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("REJECTED") == 5
    assert "OK t1" in r.stdout


def test_normal_record_still_works(home):
    r = _run(home, """
print(mcp_server.namu_record(bowl='tasks', project='proj-a', topic='t1', summary='정상 기록', reason='생략', body='생략', ctx=web).splitlines()[0])
""")
    assert r.returncode == 0, r.stderr
    log = (home / ".namu" / "tasks" / "proj-a" / "t1" / "log.md").read_text(encoding="utf-8")
    assert "정상 기록" in log


# ── ② 웹 요청의 파일 경로 칸 ──────────────────────────────────────────


def test_web_upload_refuses_file_path(home):
    secret = home / ".ssh" / "id_fake"
    secret.parent.mkdir()
    secret.write_text("PRIVATE-KEY", encoding="utf-8")
    r = _run(home, f"""
import attach_local
seen = []
attach_local.upload = lambda *a, **k: seen.append(a) or {{'path': 'x', 'bytes': 1, 'replaced': False}}
expect_reject(lambda: mcp_server.namu_upload_file(summary='s', reason='r', file_path={str(secret)!r}, ctx=web), '이 연결에는 파일 경로 칸이 없다', 'namu_create_upload_ticket')
assert seen == [], seen
""")
    assert r.returncode == 0, r.stderr
    assert "REJECTED" in r.stdout


def test_web_download_refuses_save_to(home):
    target = home / "evil" / "out.txt"
    r = _run(home, f"""
mcp_server.fetch_file = lambda c, u, n: b'echo pwned'
expect_reject(lambda: mcp_server.namu_download_file(name='x.txt', save_to={str(target)!r}, ctx=web), '이 연결에는 파일 경로 칸이 없다', 'namu_create_download_ticket')
out = mcp_server.namu_download_file(name='x.txt', ctx=web)
assert out['content_text'] == 'echo pwned' and out['saved_to'] is None
""")
    assert r.returncode == 0, r.stderr
    assert not target.exists()


def test_stdio_save_to_extensionless_file_is_a_file_not_a_folder(home):
    """`.bashrc`·`README`처럼 확장자 없는 이름은 파일 이름이다 — 예전에는 폴더로 읽혀
    그 이름의 폴더가 생기고 안에 파일이 떨어졌다."""
    out_dir = home / "out"
    out_dir.mkdir()
    r = _run(home, f"""
mcp_server.fetch_file = lambda c, u, n: b'hello'
a = mcp_server.namu_download_file(name='x.txt', save_to={str(out_dir / 'README')!r})
b = mcp_server.namu_download_file(name='x.txt', save_to={str(out_dir)!r})
c = mcp_server.namu_download_file(name='x.txt', save_to={str(out_dir / 'new-dir') + '/'!r})
print(a['saved_to']); print(b['saved_to']); print(c['saved_to'])
""")
    assert r.returncode == 0, r.stderr
    assert (out_dir / "README").is_file()
    assert (out_dir / "README").read_bytes() == b"hello"
    assert (out_dir / "x.txt").is_file()                 # 이미 있는 폴더 → 그 안에
    assert (out_dir / "new-dir" / "x.txt").is_file()     # 끝이 '/' → 폴더로


# ── 항목 7: 세션 측정 도구도 출처를 검사한다 ─────────────────────────


def test_record_session_checks_client_on_web(home):
    r = _run(home, """
class _NoClientReq:
    query_params = {}
class _RC2:
    request = _NoClientReq()
class _Ctx2:
    request_context = _RC2()
expect_reject(lambda: mcp_server.namu_record_session(session_id='s1', utterances=[{'at': '', 'text': '안녕'}], ctx=_Ctx2()), 'client')
""")
    assert r.returncode == 0, r.stderr
    assert "REJECTED" in r.stdout
