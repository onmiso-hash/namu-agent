"""session_context 단위 테스트 — 실제 tasks/db 건드리지 않음.

repo 루트 .env(NAMU_MACHINE=samsung, NAMU_HOME=repo 루트)가 config 모듈 로드 시
os.environ에 주입돼(find_dotenv(usecwd=True)) 테스트를 오염시킬 수 있다(#26/#27
반복 함정) — git 체크·물증 로그 경로에 의존하는 부분은 반드시 monkeypatch.setenv로
NAMU_HOME을 tmp_path로 명시 격리하거나, check_git_behind 자체를 스텁으로 무력화한다.
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
    subprocess/.env NAMU_HOME에 의존하지 않게 한다. git 체크 자체를 검증하는
    테스트는 _real_check_git_behind를 직접 호출하거나 이 스텁을 재정의(override)한다."""
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: None)

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
    """완료 task가 더 최신이어도 건너뛰고 진행 중 task 반환. tasks는 project_dir/tasks/ 아래."""
    tasks_root = tmp_path / "tasks"
    _make_task(tasks_root, "done-task", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    _make_task(tasks_root, "active-task", "hp", "다음 단계 구현", log_lines=["[시작] 2026-06-28 10:00:00 hp · 시작"])
    result = _sc.find_active_task(tmp_path)
    assert result is not None
    assert result.name == "active-task"

def test_find_active_most_recent_in_progress(tmp_path):
    """진행 중 task 여럿일 때 가장 최근 log_ts task 반환."""
    tasks_root = tmp_path / "tasks"
    _make_task(tasks_root, "older-task", "hp", "이전 할 일", log_lines=["[시작] 2026-06-28 10:00:00 hp · 시작"])
    _make_task(tasks_root, "newer-task", "hp", "최신 할 일", log_lines=["[시작] 2026-06-29 10:00:00 hp · 시작"])
    result = _sc.find_active_task(tmp_path)
    assert result is not None
    assert result.name == "newer-task"

def test_find_active_all_complete_returns_none(tmp_path):
    """전부 완료면 None."""
    tasks_root = tmp_path / "tasks"
    _make_task(tasks_root, "done1", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    _make_task(tasks_root, "done2", "hp", "(완료)", log_lines=["[완료] 2026-06-29 10:00:00 hp · 완료"])
    assert _sc.find_active_task(tmp_path) is None

def test_find_active_ignores_namu_home_uses_project_dir(monkeypatch, tmp_path):
    """NAMU_HOME이 설정돼 있어도 tasks는 project_dir 기준(이원화 — namu-26)."""
    namu_home = tmp_path / "namu_home"
    namu_home_tasks = namu_home / "tasks"
    _make_task(namu_home_tasks, "memory-root-task", "hp", "여기는 안 보여야 함")

    project_dir = tmp_path / "project"
    project_tasks = project_dir / "tasks"
    _make_task(project_tasks, "project-task", "hp", "여기가 보여야 함")

    monkeypatch.setenv("NAMU_HOME", str(namu_home))

    result = _sc.find_active_task(project_dir)
    assert result is not None
    assert result.name == "project-task"

def test_build_markdown_has_task_and_learnings(tmp_path):
    """진행 중 task + 교훈 → '📌 진행 중'과 '💡' 둘 다 포함."""
    tasks_root = tmp_path / "tasks"
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
    tasks_root = tmp_path / "tasks"
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
    monkeypatch.setenv("NAMU_HOME", str(tmp_path))

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
    monkeypatch.setenv("NAMU_HOME", str(tmp_path))

    def fake_run(cmd, **kwargs):
        if "fetch" in cmd:
            return _FakeCompleted(returncode=0)
        return _FakeCompleted(returncode=128, stderr="fatal: no upstream configured")

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    assert _real_check_git_behind(str(tmp_path)) is None


def test_check_git_behind_none_on_timeout(monkeypatch, tmp_path):
    """타임아웃 → None, 예외 전파 안 함."""
    import subprocess as _subprocess

    monkeypatch.setenv("NAMU_HOME", str(tmp_path))

    def fake_run(cmd, **kwargs):
        raise _subprocess.TimeoutExpired(cmd=cmd, timeout=3)

    monkeypatch.setattr(_sc.subprocess, "run", fake_run)
    result = _real_check_git_behind(str(tmp_path))
    assert result is None

    log_path = tmp_path / "db" / "git_check.log"
    assert log_path.exists()
    assert "SKIP" in log_path.read_text(encoding="utf-8")


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


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
