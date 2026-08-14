"""작업 옮기기(task_move, 설계서 4단계) — `docs/new_project_rule.md` 7장.

핵심 불변식:
  ① 이미 있는 방으로만 옮길 수 있다(새 프로젝트를 만드는 길이 없다)
  ② 목적지에 같은 슬러그가 있으면 거절하고 원본은 그대로 남는다(합치지 않는다)
  ③ 책갈피가 기기·시각을 보존한 채 따라오되, 목적지에 그 기기 책갈피가 이미
     있으면 덮어쓰지 않고 원본 것만 뗀다
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import task_move  # noqa: E402
import task_resolve  # noqa: E402


def _make_task(tasks_dir: Path, slug: str, ts: str) -> Path:
    task_dir = tasks_dir / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug} — 제목\n\n## 목적\n테스트\n", encoding="utf-8")
    (task_dir / "log.md").write_text(f"[시작] {ts} hp · 작업 생성\n", encoding="utf-8")
    return task_dir


@pytest.fixture()
def rooms(tmp_path: Path) -> tuple[Path, Path]:
    """원본 방(source)과 목적지 방(dest) 폴더 한 쌍."""
    source = tmp_path / "tasks" / "proj-a"
    dest = tmp_path / "tasks" / "proj-b"
    source.mkdir(parents=True)
    dest.mkdir(parents=True)
    return source, dest


# ── resolve_move_destination: 조건 ① 이미 있는 방으로만 ────────────────────


def test_unknown_room_is_rejected_with_room_list():
    with pytest.raises(ValueError) as exc:
        task_move.resolve_move_destination("no-such-room", known=["proj-a", "proj-b"])
    msg = str(exc.value)
    assert "proj-a" in msg
    assert "proj-b" in msg


def test_empty_destination_is_rejected_with_room_list():
    with pytest.raises(ValueError) as exc:
        task_move.resolve_move_destination(None, known=["proj-a", "proj-b"])
    msg = str(exc.value)
    assert "proj-a" in msg
    assert "proj-b" in msg


def test_rejection_message_never_offers_new_project():
    """되살아나는 것을 막는 시험 — 새 프로젝트를 만드는 선택지가 절대 없어야 한다."""
    with pytest.raises(ValueError) as exc:
        task_move.resolve_move_destination("no-such-room", known=["proj-a"])
    msg = str(exc.value)
    assert "새로 만들기" not in msg
    assert "새 프로젝트로 만들기" not in msg
    assert "새로 만들" not in msg


def test_known_room_passes_through():
    assert task_move.resolve_move_destination("proj-b", known=["proj-a", "proj-b"]) == "proj-b"


# ── move_task: 정상 이동 ──────────────────────────────────────────────────


def test_move_moves_folder_and_content_intact(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")

    result = task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    assert result["slug"] == "task-x"
    assert result["from_project"] == "proj-a"
    assert result["to_project"] == "proj-b"
    assert not (source / "task-x").exists()
    assert (dest / "task-x" / "task.md").exists()
    assert (dest / "task-x" / "task.md").read_text(encoding="utf-8").startswith("# task-x")
    assert (dest / "task-x" / "log.md").exists()


def test_move_appends_move_record_as_last_log_line(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")

    task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    lines = (dest / "task-x" / "log.md").read_text(encoding="utf-8").splitlines()
    assert lines[-1].startswith("[기록] 2026-08-14 09:00:00 hp ·")
    assert "proj-a" in lines[-1]
    assert "proj-b" in lines[-1]


def test_move_creates_dest_root_if_missing(tmp_path):
    source = tmp_path / "tasks" / "proj-a"
    dest = tmp_path / "tasks" / "proj-new"  # 아직 폴더 자체가 없다
    source.mkdir(parents=True)
    _make_task(source, "task-x", "2026-08-01 10:00:00")

    task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp", ts="2026-08-14 09:00:00"
    )

    assert (dest / "task-x" / "task.md").exists()


# ── move_task: 조건 ② 목적지에 같은 슬러그가 있으면 거절, 원본 유지 ────────


def test_move_rejects_when_dest_already_has_same_slug(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")
    _make_task(dest, "task-x", "2026-07-01 08:00:00")  # 목적지에 이미 있음

    with pytest.raises(ValueError):
        task_move.move_task(
            source_root=source, dest_root=dest, slug="task-x", machine="hp",
            ts="2026-08-14 09:00:00",
        )

    # 반쯤 옮겨진 상태가 아니다 — 원본이 그대로 남아 있다.
    assert (source / "task-x").exists()
    assert (source / "task-x" / "log.md").exists()


def test_move_missing_source_task_raises(rooms):
    source, dest = rooms
    with pytest.raises(ValueError):
        task_move.move_task(
            source_root=source, dest_root=dest, slug="no-such-task", machine="hp",
            ts="2026-08-14 09:00:00",
        )


def test_move_to_same_room_is_rejected(rooms):
    source, _dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")

    with pytest.raises(ValueError):
        task_move.move_task(
            source_root=source, dest_root=source, slug="task-x", machine="hp",
            ts="2026-08-14 09:00:00",
        )
    assert (source / "task-x").exists()


# ── move_task: 조건 ② 책갈피 정리 ────────────────────────────────────────


def test_move_carries_bookmark_preserving_machine_and_ts(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")
    task_resolve.set_pin(source, "hp", "task-x", "2026-08-05 12:00:00")

    result = task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    assert not (source / ".pin.hp").exists()
    pins = task_resolve.read_pins(dest)
    assert [(p["machine"], p["slug"], p["ts"]) for p in pins] == [
        ("hp", "task-x", "2026-08-05 12:00:00")
    ]
    assert result["moved_pins"] == [{"machine": "hp", "ts": "2026-08-05 12:00:00"}]
    assert result["dropped_pins"] == []


def test_move_carries_multiple_machines_bookmarks(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")
    task_resolve.set_pin(source, "hp", "task-x", "2026-08-05 12:00:00")
    task_resolve.set_pin(source, "samsung", "task-x", "2026-08-06 08:00:00")

    task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    machines = {p["machine"] for p in task_resolve.read_pins(dest)}
    assert machines == {"hp", "samsung"}
    assert not (source / ".pin.hp").exists()
    assert not (source / ".pin.samsung").exists()


def test_move_does_not_overwrite_existing_dest_bookmark_for_same_machine(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")
    _make_task(dest, "other-task", "2026-07-01 08:00:00")
    task_resolve.set_pin(source, "hp", "task-x", "2026-08-05 12:00:00")
    task_resolve.set_pin(dest, "hp", "other-task", "2026-08-10 09:00:00")  # 목적지에 이미 있음

    result = task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    # 목적지의 기존 hp 책갈피는 건드리지 않는다.
    dest_pins = {p["machine"]: p["slug"] for p in task_resolve.read_pins(dest)}
    assert dest_pins == {"hp": "other-task"}
    # 원본 것만 뗀다 — 어느 방향으로도 남아있지 않는다.
    assert not (source / ".pin.hp").exists()
    assert result["moved_pins"] == []
    assert result["dropped_pins"] == [{"machine": "hp"}]


def test_move_with_no_bookmarks_is_a_noop_for_pins(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")

    result = task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    assert result["moved_pins"] == []
    assert result["dropped_pins"] == []
    assert task_resolve.read_pins(dest) == []


def test_move_only_carries_bookmarks_pointing_to_the_moved_slug(rooms):
    source, dest = rooms
    _make_task(source, "task-x", "2026-08-01 10:00:00")
    _make_task(source, "task-y", "2026-08-02 10:00:00")
    task_resolve.set_pin(source, "hp", "task-y", "2026-08-05 12:00:00")  # 다른 작업 책갈피

    task_move.move_task(
        source_root=source, dest_root=dest, slug="task-x", machine="hp",
        ts="2026-08-14 09:00:00",
    )

    # task-y를 가리키던 hp 책갈피는 원본에 그대로 남는다.
    assert (source / ".pin.hp").exists()
    assert task_resolve.read_pins(source)[0]["slug"] == "task-y"
    assert task_resolve.read_pins(dest) == []
