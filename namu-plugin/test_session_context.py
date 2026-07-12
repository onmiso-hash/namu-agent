"""session_context 단위 테스트 — 실제 tasks/db 건드리지 않음.

namu-35: 데이터 루트(config.NAMU_DATA_ROOT)는 `Path.home() / ".namu"` 고정 상수로,
config 모듈이 처음 import될 때 딱 한 번 계산된다 — 이후 테스트에서 HOME 환경변수를
바꿔도 이미 계산된 값은 갱신되지 않는다. 그래서 git 체크·물증 로그 경로에 의존하는
부분은 monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", tmp_path)로 직접 격리하거나(#26/#27
반복 함정 방지), check_git_behind 자체를 스텁으로 무력화한다.
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as _cfg
import db as _db
import session_context as _sc

# 실제(패치 전) check_git_behind를 미리 붙잡아 둔다 — 아래 autouse 픽스처가
# _sc.check_git_behind를 스텁으로 덮어써도, git 체크 자체를 검증하는 테스트는
# 이 참조로 진짜 구현을 직접 호출한다(subprocess는 함수 전역에서 조회하므로
# monkeypatch.setattr(_sc.subprocess, "run", ...)는 이 참조로 호출해도 그대로 적용됨).
_real_check_git_behind = _sc.check_git_behind


@pytest.fixture(autouse=True)
def _stub_git_check(monkeypatch):
    """대부분의 테스트는 git 체크와 무관 — 기본적으로 무력화(None)해 실제
    subprocess/.env 상태에 의존하지 않게 한다. git 체크 자체를 검증하는
    테스트는 _real_check_git_behind를 직접 호출하거나 이 스텁을 재정의(override)한다."""
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: None)


@pytest.fixture(autouse=True)
def _fake_home(tmp_path, monkeypatch):
    """tasks 저장 위치가 개인 풀(~/.namu/tasks/<basename>/, namu-34)로 바뀌어 tasks
    조회·마커 기록이 Path.home()을 거친다 — 실제 ~/.namu를 절대 건드리지 않도록
    모든 테스트에서 HOME을 tmp_path 아래 가짜 홈으로 격리한다(namu-33 교훈).

    config.NAMU_DATA_ROOT는 config 모듈이 처음 import될 때 `Path.home()/".namu"`로
    딱 한 번 계산되는 고정 상수라, 여기서 HOME만 바꿔도 이미 계산된 값은 갱신되지
    않는다 — _git_check_log_path 등 cfg.NAMU_DATA_ROOT를 참조하는 코드가 실 ~/.namu에
    쓰는 사고(namu-35 회귀 발견)를 막기 위해 이 속성도 함께 monkeypatch한다."""
    home = tmp_path / "_fake_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", home / ".namu")
    return home


def _make_task(
    tasks_root: Path,
    slug: str,
    machine: str,
    next_body: str,
    log_lines: list[str] | None = None,
) -> Path:
    task_dir = tasks_root / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(
        f"# {slug} — 테스트 작업\n\n## 목적\n테스트\n\n## 완료조건\n- [ ] 완료\n",
        encoding="utf-8",
    )
    (task_dir / f"context.{machine}.md").write_text(
        f"# context @ {machine} — {slug}\n\n## ▶ 다음\n{next_body}\n\n## 지금 어디까지\n-\n",
        encoding="utf-8",
    )
    log_body = log_lines or [f"[시작] 2026-06-28 10:00:00 {machine} · 시작"]
    (task_dir / "log.md").write_text(
        f"# log — {slug}\n" + "\n".join(log_body), encoding="utf-8"
    )
    return task_dir

def _setup_mem_db(rows: list[tuple]) -> sqlite3.Connection:
    """In-memory SQLite with full NAMU schema and given learnings rows."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_db._SCHEMA)
    for row in rows:
        conn.execute(
            "INSERT INTO learnings "
            "(id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            row,
        )
    conn.commit()
    return conn

def test_find_active_skips_completed(tmp_path):
    """완료 task가 더 최신이어도 건너뛰고 진행 중 task 반환.
    tasks는 개인 풀 ~/.namu/tasks/<basename(project_dir)>/ 아래(namu-34)."""
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(tasks_root, "done-task", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    _make_task(tasks_root, "active-task", "hp", "다음 단계 구현", log_lines=["[시작] 2026-06-28 10:00:00 hp · 시작"])
    result = _sc.find_active_task(tmp_path)
    assert result is not None
    assert result.name == "active-task"

def test_find_active_most_recent_in_progress(tmp_path):
    """진행 중 task 여럿일 때 가장 최근 log_ts task 반환."""
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(tasks_root, "older-task", "hp", "이전 할 일", log_lines=["[시작] 2026-06-28 10:00:00 hp · 시작"])
    _make_task(tasks_root, "newer-task", "hp", "최신 할 일", log_lines=["[시작] 2026-06-29 10:00:00 hp · 시작"])
    result = _sc.find_active_task(tmp_path)
    assert result is not None
    assert result.name == "newer-task"

def test_find_active_all_complete_returns_none(tmp_path):
    """전부 완료면 None."""
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(tasks_root, "done1", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    _make_task(tasks_root, "done2", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    assert _sc.find_active_task(tmp_path) is None

def test_find_active_ignores_namu_home_uses_project_dir(monkeypatch, tmp_path):
    """NAMU_HOME 환경변수(namu-35: 완전 폐지)를 설정해도 아무 효과가 없고, tasks는
    항상 project_dir 기준 개인 풀에서 찾는다(이원화 — namu-26, 저장 위치는 namu-34로
    개인 풀 통합)."""
    namu_home = tmp_path / "namu_home"
    namu_home_tasks = namu_home / "tasks"
    _make_task(namu_home_tasks, "memory-root-task", "hp", "여기는 안 보여야 함")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_tasks = _cfg.tasks_dir_for(project_dir)
    _make_task(project_tasks, "project-task", "hp", "여기가 보여야 함")

    monkeypatch.setenv("NAMU_HOME", str(namu_home))

    result = _sc.find_active_task(project_dir)
    assert result is not None
    assert result.name == "project-task"

def test_build_markdown_has_task_and_learnings(tmp_path):
    """진행 중 task + 교훈 → '📌 진행 중'과 '💡' 둘 다 포함."""
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(
        tasks_root, "my-task", "hp", "헬퍼 통합 구현",
        log_lines=[
            "[시작] 2026-06-28 09:00:00 hp · 시작",
            "[결정] 2026-06-28 10:00:00 hp · 방향 확정",
        ],
    )
    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "📌 진행 중" in md
    assert "다음 할 일" in md
    assert "💡" in md

def test_build_markdown_no_task_learnings_only(tmp_path):
    """활성 task 없고 교훈 있음 → '💡 최근 교훈'만, '📌 진행 중' 없음."""
    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
        ("FAKE0002", "2026-01-02T00:00:00+00:00", "이전작업2", "other",
         "failure", "이유1", "hp", "human", "[]"),
    ])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "📌 진행 중" not in md
    assert "💡 최근 교훈" in md

def test_build_markdown_empty_returns_welcome(tmp_path):
    """활성 task 없고 교훈 0 → None이 아니라 환영 안내 문자열(신규 환경 정상 안내)."""
    conn = _setup_mem_db([])
    result = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert result is not None
    assert "NAMU" in result
    assert "/namu-task" in result

# ---------------------------------------------------------------------------
# ④ 이월 안내 — _extract_carryover
# ---------------------------------------------------------------------------

# 실물 함정: tasks/namu-26-single-source/log.md 마지막 [완료] 줄. "이월:" 뒤에
# "커밋·푸시 진행" 같은 무관한 후속 메모가 붙어 있어, 문장 경계 없이 통째로
# 잘라내면 불필요한 텍스트까지 섞인다.
_NAMU26_LOG_FIXTURE = """# log — namu-26-single-source
(append만. context 꼬이면 이걸로 복원)

[시작] 2026-07-09 21:18:00 hp · 작업 생성, 목적·완료조건 확정.
[분담] 2026-07-09 21:48:58 hp · 1차 코더 위임 완료 → 리뷰어 검수 FAIL
[결정] 2026-07-09 21:48:58 hp · 검수 게이트 중 근본 방향 전환(사용자 결정)
[분담] 2026-07-09 22:13:59 hp · 2차 코더 재위임(이원화 방향) → 리뷰어 검수 PASS
[완료] 2026-07-09 22:13:59 hp · #26 종료 — 완료조건 ①~⑥ 전부 충족(리뷰어 PASS + 사용자 라이브 실측 PASS). 이월: agy 라이브 재설치 실측(새 코드 반영)·소비자 환경 재실측·~/.namu git 자동동기화(로드맵). 커밋·푸시 진행
"""


def test_extract_carryover_present():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "log.md"
        log_path.write_text(_NAMU26_LOG_FIXTURE, encoding="utf-8")
        result = _sc._extract_carryover(log_path)
        assert result == (
            "agy 라이브 재설치 실측(새 코드 반영)·소비자 환경 재실측·"
            "~/.namu git 자동동기화(로드맵)."
        )


def test_extract_carryover_absent_when_no_marker(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n"
        "[완료] 2026-06-29 10:00:00 hp · 완료. 남은 것 없음\n",
        encoding="utf-8",
    )
    assert _sc._extract_carryover(log_path) is None


def test_extract_carryover_none_when_no_done_line(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text("[시작] 2026-06-28 10:00:00 hp · 시작\n", encoding="utf-8")
    assert _sc._extract_carryover(log_path) is None


def test_build_markdown_shows_carryover_when_all_closed_no_active(tmp_path):
    """활성 task 없고 마감 task에 이월 마커가 있으면 '⏭ 다음 작업 후보' 섹션 표시."""
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(
        tasks_root,
        "namu-26-single-source",
        "hp",
        "(완료)",
        log_lines=_NAMU26_LOG_FIXTURE.strip("\n").splitlines()[3:],
    )
    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "⏭ 다음 작업 후보" in md
    assert "namu-26-single-source" in md
    assert "agy 라이브 재설치 실측" in md


def test_build_markdown_no_carryover_section_when_no_closed_task(tmp_path):
    """마감 task 자체가 없으면(진행 중 task도, 닫힌 task도 없음) 이월 섹션 생략."""
    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "⏭ 다음 작업 후보" not in md


# ---------------------------------------------------------------------------
# ① git 동기화 체크 — check_git_behind
# ---------------------------------------------------------------------------

class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_check_git_behind_returns_count(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "fetch" in cmd:
            return _FakeCompleted(returncode=0)
        if "rev-list" in cmd:
            return _FakeCompleted(returncode=0, stdout="3\n")
        raise AssertionError(f"unexpected cmd {cmd}")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    result = _real_check_git_behind(str(tmp_path))
    assert result == 3
    assert len(calls) == 2


def test_check_git_behind_up_to_date_is_zero(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        if "fetch" in cmd:
            return _FakeCompleted(returncode=0)
        return _FakeCompleted(returncode=0, stdout="0\n")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    assert _real_check_git_behind(str(tmp_path)) == 0


def test_check_git_behind_none_and_silent_on_fetch_failure(monkeypatch, tmp_path):
    """비 git 폴더 등 fetch 실패 → None, 물증 로그는 남지만 예외는 전파 안 함."""
    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        if "fetch" in cmd:
            return _FakeCompleted(returncode=128, stderr="fatal: not a git repository")
        raise AssertionError("rev-list should not be called after fetch failure")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    result = _real_check_git_behind(str(tmp_path))
    assert result is None

    log_path = tmp_path / "db" / "git_check.log"
    assert log_path.exists()
    assert "SKIP" in log_path.read_text(encoding="utf-8")


def test_check_git_behind_none_on_no_upstream(monkeypatch, tmp_path):
    """upstream 미설정 → rev-list 실패 → None."""
    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        if "fetch" in cmd:
            return _FakeCompleted(returncode=0)
        return _FakeCompleted(returncode=128, stderr="fatal: no upstream configured")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    assert _real_check_git_behind(str(tmp_path)) is None


def test_check_git_behind_none_on_timeout(monkeypatch, tmp_path):
    """타임아웃 → None, 예외 전파 안 함."""
    import subprocess as _subprocess

    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        raise _subprocess.TimeoutExpired(cmd=cmd, timeout=3)

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    result = _real_check_git_behind(str(tmp_path))
    assert result is None

    log_path = tmp_path / "db" / "git_check.log"
    assert log_path.exists()
    assert "SKIP" in log_path.read_text(encoding="utf-8")


def test_check_git_behind_uses_devnull_stdin(monkeypatch, tmp_path):
    """모든 git 호출은 stdin=DEVNULL이어야 한다(namu-38) — MCP 서버(stdio)의 stdin
    파이프를 자식 git이 상속하면 Windows에서 EOF 미도달로 communicate가 블록되는
    실측 결함의 회귀 방지."""
    import subprocess as _subprocess

    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", tmp_path)
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(kwargs)
        return _FakeCompleted(returncode=0, stdout="0\n")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    _real_check_git_behind(str(tmp_path))

    assert len(captured) == 2  # fetch + rev-list
    for kwargs in captured:
        assert kwargs.get("stdin") is _subprocess.DEVNULL


def test_check_git_behind_disabled_via_env_skips_subprocess(monkeypatch, tmp_path):
    """NAMU_GIT_CHECK=0이면 subprocess를 아예 호출하지 않고 즉시 None."""
    monkeypatch.setenv("NAMU_GIT_CHECK", "0")
    called = []

    def fake_run(cmd, **kwargs):
        called.append(cmd)
        return _FakeCompleted(returncode=0, stdout="0\n")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    result = _real_check_git_behind(str(tmp_path))
    assert result is None
    assert called == []


def test_build_markdown_prepends_warning_when_behind(monkeypatch, tmp_path):
    """behind > 0이면 브리핑 맨 앞에 경고 섹션이 온다."""
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: 4)

    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert md.startswith("### ⚠ 원격 미동기화")
    assert "새 커밋 4개" in md
    assert "git pull --ff-only" in md
    # 경고가 본문(🌳 헤더)보다 앞에 온다
    assert md.index("⚠") < md.index("🌳")


def test_build_markdown_no_warning_when_up_to_date(monkeypatch, tmp_path):
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: 0)

    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "⚠ 원격 미동기화" not in md


def test_build_markdown_warning_prepended_to_welcome(monkeypatch, tmp_path):
    """활성 task도 교훈도 이월도 없을 때(환영 메시지)도 behind 경고는 앞에 붙는다."""
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: 2)

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert md.startswith("### ⚠ 원격 미동기화")
    assert "NAMU" in md


# ---------------------------------------------------------------------------
# ①-d ~/.namu(개인 풀) behind 경고 확장 (namu-34 ③-d)
# ---------------------------------------------------------------------------

def test_build_markdown_warns_when_home_namu_behind(monkeypatch, tmp_path, _fake_home):
    """project_dir 저장소는 최신이어도 ~/.namu가 behind면 별도 경고가 붙는다."""
    home_namu = _fake_home / ".namu"

    def fake_check(project_dir):
        return 5 if str(project_dir) == str(home_namu) else None

    monkeypatch.setattr(_sc, "check_git_behind", fake_check)

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()

    assert md is not None
    assert "⚠ 개인 풀(~/.namu) 미동기화" in md
    assert "새 커밋 5개" in md


def test_build_markdown_no_home_namu_warning_when_up_to_date(monkeypatch, tmp_path, _fake_home):
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: 0)

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()

    assert md is not None
    assert "개인 풀(~/.namu) 미동기화" not in md


def test_build_markdown_dedupes_check_when_project_dir_is_home_namu(
    monkeypatch, tmp_path, _fake_home
):
    """project_dir가 우연히 ~/.namu와 같은 실제 경로면 같은 저장소를 두 번
    fetch하지 않는다(_same_resolved_path 중복 방지)."""
    home_namu = _fake_home / ".namu"
    home_namu.mkdir(parents=True)
    calls: list[str] = []

    def fake_check(project_dir):
        calls.append(str(project_dir))
        return None

    monkeypatch.setattr(_sc, "check_git_behind", fake_check)

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", home_namu)
    conn.close()

    assert md is not None
    assert len(calls) == 1


def _init_git_repo_for_check(path):
    import subprocess as _subp

    path.mkdir(parents=True, exist_ok=True)
    _subp.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    _subp.run(
        ["git", "-C", str(path), "config", "user.email", "t@example.com"],
        check=True, capture_output=True,
    )
    _subp.run(
        ["git", "-C", str(path), "config", "user.name", "T"], check=True, capture_output=True
    )


def test_build_markdown_real_git_detects_home_namu_behind(monkeypatch, tmp_path, _fake_home):
    """실제 git(스텁 없이) — ~/.namu가 bare 원격보다 behind면 경고가 뜨고,
    project_dir(비 git 폴더)는 감지 불가로 무음 스킵된다(회귀 방지: 두 체크가
    서로 간섭하지 않는지)."""
    import subprocess as _subp

    monkeypatch.setattr(_sc, "check_git_behind", _real_check_git_behind)

    bare = tmp_path / "remote.git"
    _subp.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    seed = tmp_path / "seed"
    _init_git_repo_for_check(seed)
    (seed / "f.txt").write_text("1", encoding="utf-8")
    _subp.run(["git", "-C", str(seed), "add", "-A"], check=True, capture_output=True)
    _subp.run(
        ["git", "-C", str(seed), "commit", "-q", "-m", "c1"], check=True, capture_output=True
    )
    _subp.run(
        ["git", "-C", str(seed), "remote", "add", "origin", str(bare)],
        check=True, capture_output=True,
    )
    _subp.run(
        ["git", "-C", str(seed), "push", "-q", "-u", "origin", "main"],
        check=True, capture_output=True,
    )

    home_namu = _fake_home / ".namu"
    _subp.run(
        ["git", "clone", "-q", str(bare), str(home_namu)], check=True, capture_output=True
    )
    _subp.run(
        ["git", "-C", str(home_namu), "config", "user.email", "t@example.com"],
        check=True, capture_output=True,
    )
    _subp.run(
        ["git", "-C", str(home_namu), "config", "user.name", "T"], check=True, capture_output=True
    )

    # seed에서 추가 커밋을 만들어 push — home_namu(클론)는 아직 fetch 전이라 behind.
    (seed / "f.txt").write_text("2", encoding="utf-8")
    _subp.run(["git", "-C", str(seed), "add", "-A"], check=True, capture_output=True)
    _subp.run(
        ["git", "-C", str(seed), "commit", "-q", "-m", "c2"], check=True, capture_output=True
    )
    _subp.run(["git", "-C", str(seed), "push", "-q"], check=True, capture_output=True)

    project_dir = tmp_path / "not_a_git_repo"
    project_dir.mkdir()

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", project_dir)
    conn.close()

    assert md is not None
    assert "⚠ 개인 풀(~/.namu) 미동기화" in md
    assert "새 커밋 1개" in md
    assert "### ⚠ 원격 미동기화" not in md  # project_dir 쪽은 비 git이라 감지 불가·무음


# ---------------------------------------------------------------------------
# ② .project 마커 충돌 감지 (namu-34)
# ---------------------------------------------------------------------------


def test_build_markdown_no_conflict_warning_on_first_use(tmp_path):
    """이 키를 처음 쓰는 machine이면(.project 마커 없음) 충돌 경고가 없다."""
    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "프로젝트 키 충돌" not in md


def test_build_markdown_records_marker_after_first_call(tmp_path):
    """첫 호출 후 .project 마커가 현재 프로젝트 경로로 기록된다."""
    import os

    conn = _setup_mem_db([])
    _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()

    tasks_dir = _cfg.tasks_dir_for(tmp_path)
    marker = (tasks_dir / ".project").read_text(encoding="utf-8")
    assert marker.strip() == f"hp={os.path.realpath(tmp_path)}"


def test_build_markdown_warns_on_project_marker_conflict(tmp_path):
    """같은 키를 같은 machine에서 다른 경로 프로젝트가 쓰면 경고 1줄이 붙는다."""
    from task_resolve import record_project_marker

    project_a = tmp_path / "namesame"
    project_a.mkdir()
    project_b = tmp_path / "other" / "namesame"
    project_b.mkdir(parents=True)

    # project_a가 먼저 이 키를 등록해둔 상태를 재현.
    tasks_dir = _cfg.tasks_dir_for(project_a)
    record_project_marker(tasks_dir, "hp", str(project_a))

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", project_b)
    conn.close()

    assert md is not None
    assert "프로젝트 키 충돌" in md
    assert str(project_a.resolve()) in md
    assert str(project_b.resolve()) in md


def test_build_markdown_no_conflict_warning_when_second_call_matches(tmp_path):
    """같은 프로젝트로 두 번째 호출하면(경로 그대로) 충돌 경고가 없다(멱등 기록 확인)."""
    conn = _setup_mem_db([])
    _sc.build_context_markdown(conn, "hp", tmp_path)
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "프로젝트 키 충돌" not in md


# ---------------------------------------------------------------------------
# ⑤ 구 위치(project_dir/tasks/) 감지 (namu-34)
# ---------------------------------------------------------------------------


def test_build_markdown_warns_on_legacy_tasks(tmp_path):
    """project_dir/tasks/*/log.md가 남아있으면 이관 안내 경고가 붙는다."""
    legacy_task = tmp_path / "tasks" / "old-task"
    legacy_task.mkdir(parents=True)
    (legacy_task / "log.md").write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n", encoding="utf-8"
    )

    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()

    assert md is not None
    assert "구 위치" in md
    assert "이관 필요" in md


def test_build_markdown_no_legacy_warning_when_absent(tmp_path):
    """구 위치 tasks/가 아예 없으면 이관 경고가 없다."""
    conn = _setup_mem_db([])
    md = _sc.build_context_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md is not None
    assert "구 위치" not in md


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
