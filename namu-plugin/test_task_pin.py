"""책갈피(pin, namu-70) — 꽂기/빼기/순서/표시.

핵심 불변식 넷:
  ① 책갈피를 꽂아도 log.md는 한 글자도 변하지 않는다(순서는 표시의 문제)
  ② 기기마다 파일이 갈려 서로의 것을 건드리지 않는다(git 충돌 0의 근거)
  ③ 여러 개 꽂히면 최근에 꽂은 것부터, 안 꽂힌 것들의 기존 순서는 그대로
  ④ 닫힌 task의 책갈피는 파일을 지우지 않아도 화면에서 사라진다
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as _cfg  # noqa: E402
import session_context as _sc  # noqa: E402
import task_resolve  # noqa: E402


def _make_task(tasks_dir: Path, slug: str, ts: str, closed: bool = False) -> Path:
    task_dir = tasks_dir / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug} — 제목\n", encoding="utf-8")
    lines = [f"[시작] {ts} hp · 작업 생성"]
    if closed:
        lines.append(f"[완료] {ts} hp · 끝")
    (task_dir / "log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return task_dir


@pytest.fixture()
def tasks_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tasks" / "proj"
    d.mkdir(parents=True)
    return d


# ── ① 기록을 건드리지 않는다 ────────────────────────────────────────────


def test_pin_does_not_touch_log(tasks_dir: Path):
    task = _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    before = (task / "log.md").read_text(encoding="utf-8")

    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")

    assert (task / "log.md").read_text(encoding="utf-8") == before


def test_pin_does_not_change_last_activity_time(tasks_dir: Path):
    """책갈피는 last_ts에 영향이 없다 — 있으면 '기록으로 순서 속이기'와 같아진다."""
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 23:00:00")

    ts = task_resolve._latest_log_ts(tasks_dir / "a-task" / "log.md")
    assert ts == ("2026-08-01", "10:00:00")


# ── ② 기기마다 파일이 갈린다 ────────────────────────────────────────────


def test_pin_file_is_per_machine(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    _make_task(tasks_dir, "b-task", "2026-08-01 09:00:00")

    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "samsung", "b-task", "2026-08-01 12:00:00")

    assert (tasks_dir / ".pin.hp").exists()
    assert (tasks_dir / ".pin.samsung").exists()
    machines = {p["machine"]: p["slug"] for p in task_resolve.read_pins(tasks_dir)}
    assert machines == {"hp": "a-task", "samsung": "b-task"}


def test_unpin_leaves_other_machines_alone(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "samsung", "a-task", "2026-08-01 12:00:00")

    removed = task_resolve.clear_pin(tasks_dir, "hp")

    assert removed == "a-task"
    assert not (tasks_dir / ".pin.hp").exists()
    assert [p["machine"] for p in task_resolve.read_pins(tasks_dir)] == ["samsung"]


def test_unpin_without_pin_returns_none(tasks_dir: Path):
    assert task_resolve.clear_pin(tasks_dir, "hp") is None


def test_pin_replaces_previous_pin_of_same_machine(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    _make_task(tasks_dir, "b-task", "2026-08-01 09:00:00")

    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "b-task", "2026-08-01 12:00:00")

    pins = task_resolve.read_pins(tasks_dir)
    assert [(p["machine"], p["slug"]) for p in pins] == [("hp", "b-task")]


def test_machine_name_with_path_separator_is_rejected(tasks_dir: Path):
    with pytest.raises(ValueError):
        task_resolve.set_pin(tasks_dir, "../evil", "a-task", "2026-08-01 11:00:00")


# ── ③ 순서 ──────────────────────────────────────────────────────────────


def test_pinned_task_comes_first(tasks_dir: Path):
    """namu-70 실물 재현: 26초 늦게 만든 사소한 작업이 앞자리를 가져가던 상황."""
    _make_task(tasks_dir, "urgent", "2026-07-31 20:00:00")
    _make_task(tasks_dir, "trivial", "2026-07-31 20:00:26")

    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["trivial", "urgent"]

    task_resolve.set_pin(tasks_dir, "hp", "urgent", "2026-08-01 09:00:00")

    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["urgent", "trivial"]


def test_multiple_pins_most_recently_pinned_first(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    _make_task(tasks_dir, "b-task", "2026-08-01 09:00:00")
    _make_task(tasks_dir, "c-task", "2026-08-01 08:00:00")

    task_resolve.set_pin(tasks_dir, "hp", "c-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "samsung", "b-task", "2026-08-01 12:00:00")

    # 꽂힌 것 둘이 최근 꽂은 순으로 앞, 안 꽂힌 a-task는 뒤.
    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == [
        "b-task",
        "c-task",
        "a-task",
    ]


def test_unpinned_keep_recent_activity_order(tasks_dir: Path):
    _make_task(tasks_dir, "old", "2026-08-01 08:00:00")
    _make_task(tasks_dir, "mid", "2026-08-01 09:00:00")
    _make_task(tasks_dir, "new", "2026-08-01 10:00:00")

    task_resolve.set_pin(tasks_dir, "hp", "old", "2026-08-01 11:00:00")

    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["old", "new", "mid"]


def test_no_pin_keeps_old_behaviour(tasks_dir: Path):
    _make_task(tasks_dir, "old", "2026-08-01 08:00:00")
    _make_task(tasks_dir, "new", "2026-08-01 10:00:00")

    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["new", "old"]


# ── ④ 닫힌 task ────────────────────────────────────────────────────────


def test_pin_on_closed_task_is_ignored_without_deleting_file(tasks_dir: Path):
    _make_task(tasks_dir, "done-task", "2026-08-01 10:00:00", closed=True)
    _make_task(tasks_dir, "open-task", "2026-08-01 09:00:00")

    task_resolve.set_pin(tasks_dir, "samsung", "done-task", "2026-08-01 12:00:00")

    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["open-task"]
    # 남의 기기 파일은 지우지 않는다 — 지우면 그쪽에서 되살아나 깜빡인다.
    assert (tasks_dir / ".pin.samsung").exists()


# ── 깨진 파일 내성 ──────────────────────────────────────────────────────


def test_broken_pin_file_is_skipped(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    (tasks_dir / ".pin.hp").write_text("", encoding="utf-8")
    (tasks_dir / ".pin.samsung").write_text("a-task\n", encoding="utf-8")  # 시각 줄 없음

    pins = task_resolve.read_pins(tasks_dir)

    assert [(p["machine"], p["slug"], p["ts"]) for p in pins] == [("samsung", "a-task", "")]
    assert [d.name for d in task_resolve.find_open_tasks(tasks_dir)] == ["a-task"]


def test_closing_clears_only_this_machines_pin_for_that_task(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    _make_task(tasks_dir, "b-task", "2026-08-01 09:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "samsung", "a-task", "2026-08-01 12:00:00")

    assert task_resolve.clear_pin_if_points_to(tasks_dir, "hp", "a-task") is True

    assert not (tasks_dir / ".pin.hp").exists()
    assert (tasks_dir / ".pin.samsung").exists()  # 남의 기기 것은 그대로


def test_closing_other_task_leaves_pin_alone(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")

    assert task_resolve.clear_pin_if_points_to(tasks_dir, "hp", "b-task") is False
    assert (tasks_dir / ".pin.hp").exists()


def test_pins_by_slug_keeps_most_recent(tasks_dir: Path):
    _make_task(tasks_dir, "a-task", "2026-08-01 10:00:00")
    task_resolve.set_pin(tasks_dir, "hp", "a-task", "2026-08-01 11:00:00")
    task_resolve.set_pin(tasks_dir, "samsung", "a-task", "2026-08-01 12:00:00")

    assert task_resolve.pins_by_slug(tasks_dir)["a-task"]["machine"] == "samsung"


# ── 브리핑 화면 ────────────────────────────────────────────────────────
#
# 완료조건 ①("왜 이게 맨 위인지 사용자가 알 수 있다")은 화면 글자로만 확인된다 —
# 순서가 맞아도 이유가 안 적혀 있으면 사용자는 여전히 알 수 없다.


@pytest.fixture()
def briefing_home(tmp_path, monkeypatch):
    """실제 ~/.namu를 건드리지 않도록 HOME과 데이터 루트를 함께 격리한다."""
    home = tmp_path / "_fake_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(_cfg, "NAMU_DATA_ROOT", home / ".namu")
    monkeypatch.setattr(_sc, "check_git_behind", lambda project_dir: None)
    tasks_dir = home / ".namu" / "tasks" / "proj"
    tasks_dir.mkdir(parents=True)
    return tasks_dir


def _render(tasks_dir: Path) -> str:
    parts, _top = _sc._build_task_section(str(tasks_dir.parent.parent.parent / "proj"), tasks_dir)
    return "\n".join(parts)


def test_briefing_marks_pinned_task_and_says_why_it_is_first(briefing_home: Path):
    _make_task(briefing_home, "urgent", "2026-07-31 20:00:00")
    _make_task(briefing_home, "trivial", "2026-07-31 20:00:26")
    task_resolve.set_pin(briefing_home, "hp", "urgent", "2026-08-01 09:00:00")

    md = _render(briefing_home)

    assert "📌 **urgent**" in md          # 맨 위 항목이 책갈피 표시로 바뀐다
    assert "hp가 꽂음" in md               # 어느 PC가 꽂았는지
    assert md.count("📌 **urgent**") == 1  # 한 줄에 두 번 찍히지 않는다
    assert "책갈피" in md                  # 왜 맨 위인지 글자로 설명
    assert "최근 활동순" in md             # 나머지 정렬 기준도 함께


def test_briefing_states_sort_basis_when_nothing_is_pinned(briefing_home: Path):
    _make_task(briefing_home, "a-task", "2026-08-01 10:00:00")

    md = _render(briefing_home)

    assert "▸ **a-task**" in md
    assert "최근 활동순" in md
    assert "namu_task_pin" in md          # 정해두는 방법을 알려준다
