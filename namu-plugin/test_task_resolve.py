import pytest
from pathlib import Path
from task_resolve import _parse_log_ts, find_active_task, resolve_active_task

def test_parse_log_ts():
    # 시각 있는 줄
    assert _parse_log_ts("[시작] 2026-06-28 10:15:30 hp · 시작") == ("2026-06-28", "10:15:30")
    # 대괄호 안의 태그만 있는 줄 (시각 없음)
    assert _parse_log_ts("[시작] 2026-06-28 hp · 내용") == ("2026-06-28", "00:00:00")
    # 시각 있는 줄 (다른 포맷)
    assert _parse_log_ts("[결정] 2026-06-29 07:35:51 hp · 내용") == ("2026-06-29", "07:35:51")
    # 비-log 줄
    assert _parse_log_ts("그냥 텍스트") is None
    assert _parse_log_ts("# log — task") is None

def _make_task(tasks_root: Path, slug: str, next_body: str | None, log_ts: str, machine: str = "hp"):
    task_dir = tasks_root / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    
    if next_body is not None:
        (task_dir / f"context.{machine}.md").write_text(
            f"## ▶ 다음\n{next_body}\n", encoding="utf-8"
        )
    
    (task_dir / "log.md").write_text(
        f"# log\n[시작] {log_ts} {machine} · 시작함\n", encoding="utf-8"
    )
    return task_dir

def test_find_active_latest_log_ts(tmp_path):
    _make_task(tmp_path, "older", "진행중", "2026-06-28 10:00:00")
    _make_task(tmp_path, "newer", "진행중", "2026-06-29 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "newer"

def test_find_active_skips_all_done(tmp_path):
    _make_task(tmp_path, "done", "(완료)", "2026-06-29 10:00:00")
    _make_task(tmp_path, "active", "진행중", "2026-06-28 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "active"

def test_find_active_no_context_is_active(tmp_path):
    # context 파일이 아예 없음
    _make_task(tmp_path, "no-context", None, "2026-06-29 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "no-context"

def test_find_active_missing_machine_context_still_found(tmp_path):
    # context.hp.md만 있고, context.samsung.md는 없어도 잡힘
    _make_task(tmp_path, "only-hp", "진행중", "2026-06-29 10:00:00", machine="hp")

    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "only-hp"


def test_resolve_active_task_uses_ws_tasks_subdir(tmp_path):
    """resolve_active_task(ws)는 ws/tasks/ 아래에서 찾는다."""
    _make_task(tmp_path / "tasks", "ws-task", "진행중", "2026-06-29 10:00:00")

    res = resolve_active_task(str(tmp_path))
    assert res is not None
    assert res[0] == "ws-task"


def test_resolve_active_task_ignores_namu_home_env(monkeypatch, tmp_path):
    """NAMU_HOME 환경변수가 설정돼 있어도 ws(프로젝트) 기준만 본다(namu-26 이원화).

    이전 동작(NAMU_HOME 우선)이었다면 이 테스트는 실패한다 — NAMU_HOME 아래
    tasks에 활성 task를 심어 놓고 ws 쪽엔 아무것도 안 둬서, 옛 로직이면
    NAMU_HOME의 task를 찾고 새 로직이면 None을 반환해야 정상이다.
    """
    namu_home = tmp_path / "namu_home"
    _make_task(namu_home / "tasks", "memory-root-task", "진행중", "2026-06-29 10:00:00")

    ws_dir = tmp_path / "project"
    ws_dir.mkdir()

    monkeypatch.setenv("NAMU_HOME", str(namu_home))

    res = resolve_active_task(str(ws_dir))
    assert res is None


def test_resolve_active_task_empty_ws_returns_none():
    """ws가 비어있으면 안전 폴백으로 None."""
    assert resolve_active_task("") is None
