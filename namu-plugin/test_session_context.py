"""session_context 단위 테스트 — 실제 tasks/db 건드리지 않음."""
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as _cfg
import db as _db
import session_context as _sc


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
    log_body = log_lines or [f"- 📅2026-06-28 🕐10:00 [{machine}] [시작] 생성"]
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


def test_find_active_skips_completed(monkeypatch, tmp_path):
    """완료 task가 더 최신 mtime이어도 건너뛰고 진행 중 task 반환."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    done = _make_task(tmp_path, "done-task", machine, "(완료)")
    active = _make_task(tmp_path, "active-task", machine, "다음 단계 구현")

    now = time.time()
    os.utime(done / f"context.{machine}.md", (now, now))
    os.utime(active / f"context.{machine}.md", (now - 100, now - 100))

    result = _sc.find_active_task(machine)
    assert result is not None
    assert result.name == "active-task"


def test_find_active_most_recent_in_progress(monkeypatch, tmp_path):
    """진행 중 task 여럿일 때 가장 최근 mtime task 반환."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    older = _make_task(tmp_path, "older-task", machine, "이전 할 일")
    newer = _make_task(tmp_path, "newer-task", machine, "최신 할 일")

    now = time.time()
    os.utime(older / f"context.{machine}.md", (now - 200, now - 200))
    os.utime(newer / f"context.{machine}.md", (now, now))

    result = _sc.find_active_task(machine)
    assert result is not None
    assert result.name == "newer-task"


def test_find_active_all_complete_returns_none(monkeypatch, tmp_path):
    """전부 완료면 None."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    _make_task(tmp_path, "done1", machine, "(완료)")
    _make_task(tmp_path, "done2", machine, "(완료)")

    assert _sc.find_active_task(machine) is None


def test_build_markdown_has_task_and_learnings(monkeypatch, tmp_path):
    """진행 중 task + 교훈 → '📌 진행 중'과 '💡' 둘 다 포함."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    _make_task(
        tmp_path, "my-task", machine, "헬퍼 통합 구현",
        log_lines=[
            "- 📅2026-06-28 🕐09:00 [hp] [시작] 생성",
            "- 📅2026-06-28 🕐10:00 [hp] [결정] 방향 확정",
        ],
    )

    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])

    md = _sc.build_context_markdown(conn, machine)
    conn.close()

    assert md is not None
    assert "📌 진행 중" in md
    assert "다음 할 일" in md
    assert "💡" in md


def test_build_markdown_no_task_learnings_only(monkeypatch, tmp_path):
    """활성 task 없고 교훈 있음 → '💡 최근 교훈'만, '📌 진행 중' 없음."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "이전작업", "other",
         "success", "이유0", "hp", "human", "[]"),
        ("FAKE0002", "2026-01-02T00:00:00+00:00", "이전작업2", "other",
         "failure", "이유1", "hp", "human", "[]"),
    ])

    md = _sc.build_context_markdown(conn, machine)
    conn.close()

    assert md is not None
    assert "📌 진행 중" not in md
    assert "💡 최근 교훈" in md


def test_build_markdown_empty_returns_none(monkeypatch, tmp_path):
    """활성 task 없고 교훈 0 → None."""
    machine = "hp"
    monkeypatch.setattr(_cfg, "TASKS_DIR", tmp_path)

    conn = _setup_mem_db([])
    result = _sc.build_context_markdown(conn, machine)
    conn.close()

    assert result is None


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
