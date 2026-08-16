"""기록 시각의 기준 시간대 테스트 (namu-57 5단계).

tasks 로그(log.md)의 시각은 시간대 표기가 없는 벽시계 문자열이라, 호스트마다 제
현지시각을 적으면 같은 파일 안에서 시각끼리 비교가 불가능해진다. 실제로 웹 커넥터
컨테이너(TZ=UTC)가 기록하자 그 줄만 9시간 이르게 적혀 브리핑의 "최근 활동" 정렬에서
최신 기록이 묻히고 task의 last_ts가 거꾸로 갔다.

그래서 이 파일의 핵심 케이스는 **"호스트 TZ가 UTC여도 서울 벽시계로 적힌다"**(④)다 —
서브프로세스에 TZ=UTC를 심어 웹 컨테이너 상황을 그대로 재현한다. 고치기 전 코드는
이 케이스에서 UTC 시각을 적으므로 반드시 실패한다(대조군 없이 통과하는 테스트가 되지
않도록 한 설계, namu-57 3단계 교훈).
"""
import ast
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import config
from task_resolve import _latest_log_ts, open_tasks_briefing

_NAMU_PLUGIN_DIR = Path(__file__).parent
_SEOUL = ZoneInfo("Asia/Seoul")
_STAMP_RE = re.compile(r"^\[.*?\]\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s")


# ---------------------------------------------------------------------------
# ① config.now() — 기준 시간대 해석
# ---------------------------------------------------------------------------


def test_now_is_seoul_aware_by_default():
    """기본값은 Asia/Seoul이고, naive가 아니라 aware여야 한다(비교 가능해야 하므로)."""
    assert config.NAMU_TZ == "Asia/Seoul"
    stamped = config.now()
    assert stamped.tzinfo is not None
    assert stamped.utcoffset() == timedelta(hours=9)


def test_now_honors_namu_tz_override(monkeypatch):
    """다른 기준 시간대를 쓰는 사용자를 위해 NAMU_TZ로 갈아끼울 수 있다."""
    monkeypatch.setattr(config, "NAMU_TZ", "UTC")
    assert config.now().utcoffset() == timedelta(0)


def test_now_falls_back_to_local_when_tz_data_missing(monkeypatch):
    """tz 데이터를 못 찾아도 예외로 기록을 막지 않고 현지시각으로 폴백한다 —
    시각이 어긋나는 것보다 기록이 유실되는 쪽이 훨씬 나쁘다."""
    monkeypatch.setattr(config, "NAMU_TZ", "Not/AZone")
    stamped = config.now()  # 예외가 나면 이 줄에서 실패
    assert stamped.tzinfo is None


# ---------------------------------------------------------------------------
# ② log.md에 실제로 찍히는 시각 — 웹 컨테이너(TZ=UTC) 재현
# ---------------------------------------------------------------------------


_PROBE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import mcp_server
print('LINE', mcp_server.namu_record(
    bowl='tasks', project='p1', task='t1', text='시간대 확인', reason='생략', body='생략'))
"""


def _make_pool_task(home: Path, project: str, slug: str) -> Path:
    task_dir = home / ".namu" / "tasks" / project / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    (task_dir / "log.md").write_text(f"# log — {slug}\n\n", encoding="utf-8")
    return task_dir


def _record_with_host_tz(home: Path, host_tz: str) -> str:
    """호스트 TZ를 지정해 서브프로세스에서 한 줄 기록하고 그 줄을 반환한다.

    mcp_server는 import 시점에 실제 ~/.namu를 만지므로 HOME 격리가 필수다
    (test_mcp_bowl.py와 같은 이유·같은 방식).
    """
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TZ"] = host_tz
    env.pop("NAMU_HOME", None)
    env.pop("NAMU_TZ", None)

    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(plugin_dir=str(_NAMU_PLUGIN_DIR))],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    line = next(l for l in result.stdout.splitlines() if l.startswith("LINE "))
    return line[len("LINE ") :]


def _parse_stamp(line: str) -> datetime:
    match = _STAMP_RE.match(line)
    assert match, f"시각을 파싱할 수 없는 줄: {line!r}"
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")


@pytest.mark.parametrize("host_tz", ["UTC", "America/New_York"])
def test_task_log_stamp_uses_seoul_regardless_of_host_tz(tmp_path, host_tz):
    """호스트가 어느 시간대에 있든 log.md에는 같은 기준(서울) 벽시계가 찍힌다.

    고치기 전 코드는 호스트 현지시각을 그대로 적으므로 UTC에서 9시간, 뉴욕에서
    13~14시간 어긋나 이 단언에서 실패한다.
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    _make_pool_task(home, "p1", "t1")

    line = _record_with_host_tz(home, host_tz)
    stamped = _parse_stamp(line)
    expected = datetime.now(_SEOUL).replace(tzinfo=None)

    assert abs(stamped - expected) < timedelta(minutes=2), (
        f"host_tz={host_tz}: 기록된 {stamped}, 서울 기준 {expected}"
    )


def test_created_task_start_line_uses_seoul_too(tmp_path):
    """create=True, body='생략' 경로(task.md의 생성일 + [시작] 줄)도 같은 시계를 쓴다 —
    한쪽만 고치면 새 task의 생성일과 첫 줄이 서로 어긋난다."""
    home = tmp_path / "fake_home"
    home.mkdir()
    (home / ".namu" / "tasks" / "p1").mkdir(parents=True)

    probe = """
import sys
sys.path.insert(0, {plugin_dir!r})
import mcp_server
print('OUT', mcp_server.namu_record(
    bowl='tasks', project='p1', task='t-new', create=True, body='생략', purpose='시간대 확인'))
""".format(plugin_dir=str(_NAMU_PLUGIN_DIR))

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TZ"] = "UTC"
    env.pop("NAMU_HOME", None)
    env.pop("NAMU_TZ", None)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    task_dir = home / ".namu" / "tasks" / "p1" / "t-new"
    seoul_today = datetime.now(_SEOUL).strftime("%Y-%m-%d")
    assert f"📅 생성 {seoul_today}" in (task_dir / "task.md").read_text(encoding="utf-8")

    start_line = next(
        l for l in (task_dir / "log.md").read_text(encoding="utf-8").splitlines()
        if l.startswith("[시작]")
    )
    assert abs(_parse_stamp(start_line) - datetime.now(_SEOUL).replace(tzinfo=None)) < timedelta(
        minutes=2
    )


# ---------------------------------------------------------------------------
# ③ 읽는 쪽 — last_ts는 "파일의 마지막 줄"이 아니라 "가장 늦은 시각"
# ---------------------------------------------------------------------------


def _write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# log\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def test_latest_log_ts_ignores_out_of_order_last_line(tmp_path):
    """마지막 줄이 더 이른 시각이어도 last_ts는 가장 늦은 시각을 고른다.

    이미 기록된 UTC 줄(append-only라 지울 수 없다)과 union merge로 섞인 줄 순서,
    두 경우 모두에 해당한다.
    """
    log_path = tmp_path / "t1" / "log.md"
    _write_log(
        log_path,
        [
            "[기록] 2026-07-25 17:50:25 hp · 로컬 기록(한국시각)",
            "[기록] 2026-07-25 09:31:51 web · 웹 기록(과거 UTC 줄)",
        ],
    )
    assert _latest_log_ts(log_path) == ("2026-07-25", "17:50:25")


def test_latest_log_ts_none_when_no_stamped_line(tmp_path):
    log_path = tmp_path / "t1" / "log.md"
    _write_log(log_path, ["설명만 있고 시각 줄이 없다"])
    assert _latest_log_ts(log_path) is None


def test_open_tasks_briefing_sorts_by_latest_not_last_line(tmp_path, monkeypatch):
    """브리핑의 task 정렬(가장 최근 활동 순)이 이른 줄 하나에 흔들리지 않아야 한다 —
    흔들리면 ▸(가장 최근 활동)가 엉뚱한 task를 가리킨다."""
    home = tmp_path / "fake_home"
    monkeypatch.setenv("HOME", str(home))
    pool = home / ".namu" / "tasks" / "p1"

    for slug, lines in {
        "t-recent": [
            "[기록] 2026-07-25 17:50:25 hp · 오늘 저녁 작업",
            "[기록] 2026-07-25 09:31:51 web · 나중에 붙었지만 시각은 이른 줄",
        ],
        "t-older": ["[기록] 2026-07-25 11:00:00 hp · 오전 작업"],
    }.items():
        (pool / slug).mkdir(parents=True)
        (pool / slug / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
        _write_log(pool / slug / "log.md", lines)

    rows = open_tasks_briefing(["p1"])
    assert [r["slug"] for r in rows] == ["t-recent", "t-older"]
    assert rows[0]["last_ts"] == "2026-07-25 17:50:25"


# ---------------------------------------------------------------------------
# ④ yaml 그릇들(learnings/profile/memo)이 같은 시계를 쓰는가 — namu-71
#
# 같은 클라우드 서버에서 5분 간격으로 저장한 쪽지(+09:00)와 교훈(+00:00)의 시각이
# 9시간 어긋난 실물 사고. 원인은 db.record/profile.record_fact 두 곳만 cfg.now()가
# 아니라 datetime.now(timezone.utc)를 쓰고 있었던 것이다. 고치기 전 코드는 호스트
# TZ와 무관하게 +00:00을 적으므로 아래 단언에서 반드시 실패한다.
# ---------------------------------------------------------------------------


_YAML_PROBE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import db, memo, profile
db.record('t-tz', 'success', '이유', task_type='other', verified_by='ai',
          tags=[], summary='요약', body='상세')
profile.record_fact('주제', summary='요약', reason='이유', body='상세')
memo.add('쪽지', reason='이유', body='상세')
print('OK')
"""


def _record_all_bowls_with_host_tz(home: Path, host_tz: str) -> dict[str, str]:
    """호스트 TZ를 지정해 세 그릇에 한 건씩 기록하고, 각 yaml의 timestamp를 돌려준다."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TZ"] = host_tz
    env.pop("NAMU_HOME", None)
    env.pop("NAMU_TZ", None)

    result = subprocess.run(
        [sys.executable, "-c", _YAML_PROBE.format(plugin_dir=str(_NAMU_PLUGIN_DIR))],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    stamps = {}
    for bowl, filename in [
        ("learnings", "learnings.yaml"),
        ("profile", "profile.yaml"),
        ("memo", "memo.yaml"),
    ]:
        text = (home / ".namu" / "memory" / filename).read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.strip().startswith("timestamp:"))
        stamps[bowl] = line.split("timestamp:", 1)[1].strip().strip("'\"")
    return stamps


@pytest.mark.parametrize("host_tz", ["UTC", "America/New_York"])
def test_yaml_bowls_share_one_clock(tmp_path, host_tz):
    """세 그릇의 저장 시각이 같은 기준 시간대(서울)로 찍힌다.

    그릇마다 다르면 브리핑·목록이 여러 그릇을 최근순으로 섞을 때 실제보다 오래된
    것이 위로 온다(namu-71 발단).
    """
    home = tmp_path / "fake_home"
    home.mkdir()

    stamps = _record_all_bowls_with_host_tz(home, host_tz)
    expected = datetime.now(_SEOUL)

    for bowl, raw in stamps.items():
        stamped = datetime.fromisoformat(raw)
        assert stamped.utcoffset() == timedelta(hours=9), f"{bowl}: {raw}"
        assert abs(stamped - expected) < timedelta(minutes=2), f"{bowl}: {raw}"

    # 문자열을 그대로 사전순 비교하는 코드(db.py의 since/until)가 조용히 어긋나지
    # 않으려면 표기까지 같아야 한다 — 오프셋이 갈리면 같은 순간도 다르게 정렬된다.
    assert len({s[-6:] for s in stamps.values()}) == 1, stamps


# ---------------------------------------------------------------------------
# ④ 진단용 로그(db/sync.log · db/git_check.log)도 같은 시계를 쓴다
#
# 이 두 파일은 git 추적 대상이 아니라(db/ 는 .gitignore) 기기 사이에 섞이지 않는다.
# 그런데도 기준 시간대를 강제하는 이유는 **같은 기계 안에서 시간대가 갈리기 때문**이다:
# 웹 컨테이너의 시계는 UTC라 `datetime.now()`로 찍으면 sync.log만 9시간 이르게 남고,
# 바로 옆 작업일지·기억 기록은 서울 벽시계로 남는다. 2026-08-16 무한 재시작 사고를
# 뒤쫓을 때 실제로 이 어긋남에 걸렸다 — 고장을 들여다보는 바로 그 순간에 걸린다.
# 고치기 전 코드는 host_tz='UTC' 케이스에서 반드시 실패한다(대조군 없는 통과 방지).
# ---------------------------------------------------------------------------


_LOG_PROBE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import config as cfg
import memory_sync
import session_context

memory_sync._append_sync_log('PROBE 동기화 로그')
session_context._append_git_check_log(str(cfg.NAMU_DATA_ROOT), 'PROBE 점검 로그')
print('OK')
"""


def _write_diagnostic_logs_with_host_tz(home: Path, host_tz: str) -> dict[str, str]:
    """호스트 TZ를 지정해 두 진단 로그에 한 줄씩 남기고, 각 줄의 시각을 돌려준다."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TZ"] = host_tz
    env.pop("NAMU_HOME", None)
    env.pop("NAMU_TZ", None)

    result = subprocess.run(
        [sys.executable, "-c", _LOG_PROBE.format(plugin_dir=str(_NAMU_PLUGIN_DIR))],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    stamps = {}
    for name, filename in [("sync", "sync.log"), ("git_check", "git_check.log")]:
        path = home / ".namu" / "db" / filename
        assert path.exists(), f"{filename}이 만들어지지 않았습니다"
        line = path.read_text(encoding="utf-8").splitlines()[-1]
        stamps[name] = line.split("|", 1)[0].strip()
    return stamps


@pytest.mark.parametrize("host_tz", ["UTC", "America/New_York"])
def test_diagnostic_logs_share_the_record_clock(tmp_path, host_tz):
    """진단 로그의 시각이 기억 기록과 같은 기준 시간대(서울)로 찍힌다."""
    home = tmp_path / "fake_home"
    home.mkdir()

    stamps = _write_diagnostic_logs_with_host_tz(home, host_tz)
    expected = datetime.now(_SEOUL).replace(tzinfo=None)

    for name, raw in stamps.items():
        stamped = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        assert abs(stamped - expected) < timedelta(minutes=2), f"{name}: {raw}"


def test_no_module_reaches_for_the_host_clock_directly():
    """`datetime.now()`를 직접 부르는 자리가 다시 생기지 않게 못 박는다.

    이 검사가 필요한 이유는 새로 쓰는 로그 한 줄이 늘 같은 방식으로 새기 때문이다 —
    "그냥 로그니까"라고 생각하는 순간 호스트 시계로 돌아간다. 예외는 둘뿐이다:
    `config.now()` 자신(여기가 기준 시간대를 만드는 자리)과 statusline 계열(config를
    일부러 안 부르는 plain python3 소비자이고, 개인 PC에서만 도는 화면 표시라
    호스트 시계와 기준 시간대가 어차피 같다).

    글자로 찾지 않고 구문 트리로 실제 호출만 본다 — 설명문에서 "`datetime.now()`를 쓰면
    안 된다"고 적어 둔 문장까지 위반으로 잡으면, 규칙을 설명한 주석이 규칙 위반이 되는
    자가당착이 된다(첫 판에서 실제로 그렇게 걸렸다).
    """
    allowed ={"config.py", "namu_setup_statusline.py", "namu_statusline.py"}
    offenders = []
    for path in _NAMU_PLUGIN_DIR.rglob("*.py"):
        if path.name in allowed or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or node.args or node.keywords:
                continue  # datetime.now(tz)처럼 시간대를 넘기는 호출은 대상이 아니다
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "now":
                owner = func.value
                name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
                if name == "datetime":
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "기록 시각은 cfg.now()로 찍어야 합니다(호스트 시계 금지): " + ", ".join(offenders)
    )
