"""리뷰 B 수정(2026-09-25) 회귀 시험 — task_resolve / task_move / config 기기 이름.

리뷰어가 결함을 재현한 시험(`reviewB/test_reviewB_tasks.py`)의 단언을 뒤집은 것이다.
HOME은 tmp로 격리한다.
"""
import sqlite3
from contextlib import closing

import pytest

import config as cfg
import db as _db
import task_move
import task_resolve


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


# ── 2. 방 이름은 현재 폴더와 상관없이 그대로 방 이름이다 ─────────────────────────
def test_room_name_not_resolved_against_cwd(home, monkeypatch):
    repo = home / "work" / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "naite").mkdir()
    monkeypatch.chdir(repo)
    assert task_resolve.tasks_root_for("naite").name == "naite"
    assert task_resolve.project_key_for("naite") == "naite"
    monkeypatch.chdir(home)
    assert task_resolve.tasks_root_for("naite").name == "naite"


def test_folder_paths_still_find_project_root(home):
    """구분자가 든 값(폴더 경로)은 종전대로 뿌리(.git)를 찾아 올라간다."""
    repo = home / "work" / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "naite").mkdir()
    assert task_resolve.tasks_root_for(str(repo / "naite")).name == "repo"
    assert task_resolve.tasks_root_for(str(repo) + "/").name == "repo"
    assert cfg.tasks_dir_for(repo / "naite").name == "repo"


# ── 1. 풀 밖을 가리키는 방 이름은 거절한다 ───────────────────────────────────────
@pytest.mark.parametrize("bad", ["..", ".", "", "  ", "..\\x", "/", "../"])
def test_bad_room_keys_rejected(home, monkeypatch, bad):
    monkeypatch.chdir(home)
    with pytest.raises(ValueError):
        task_resolve.tasks_root_for(bad)


def test_dotdot_project_cannot_escape_pool(home, monkeypatch):
    monkeypatch.chdir(home)
    (home / ".namu" / "tasks").mkdir(parents=True)
    (home / ".namu" / "memory").mkdir(parents=True)
    (home / ".namu" / "memory" / "log.md").write_text(
        "[기록] 2026-09-01 10:00:00 hp · 풀밖\n", encoding="utf-8")
    with pytest.raises(ValueError):
        task_resolve.journal(project="..")
    with pytest.raises(ValueError):
        task_resolve.task_docs(project="..")
    # 색인 검색의 project 축도 같은 문지기를 지난다.
    p = cfg.data_paths_for(home / "d")
    p.db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(p.db_path)) as conn:
        with pytest.raises(ValueError):
            _db.search_bowl(conn, bowl="tasks", project="..", paths=p)


def test_resolve_active_task_filesystem_root_is_none(home):
    assert task_resolve.resolve_active_task("/") is None


# ── 9. 이관 줄·상세 없는 [기록]이 '상세' 포인터를 가로채지 않는다 ─────────────────
def test_move_line_does_not_hijack_detail_pointer(tmp_path):
    src = tmp_path / "tasks" / "a"
    dst = tmp_path / "tasks" / "b"
    (src / "t1").mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "t1" / "task.md").write_text("# t1 — 제목\n", encoding="utf-8")
    (src / "t1" / "log.md").write_text(
        "[시작] 2026-09-01 10:00:00 hp · 시작\n"
        "[기록] 2026-09-10 10:00:00 hp · 측정\n    상세: 기준선 수치 전부\n",
        encoding="utf-8")
    task_move.move_task(source_root=src, dest_root=dst, slug="t1",
                        machine="hp", ts="2026-09-20 09:00:00")
    assert task_resolve.latest_record_date(dst / "t1") == "2026-09-10"


def test_plain_record_line_without_detail_does_not_hijack(tmp_path):
    d = tmp_path / "t"
    d.mkdir()
    (d / "log.md").write_text(
        "[기록] 2026-09-10 10:00:00 hp · 측정\n    상세: 수치\n"
        "[기록] 2026-09-12 10:00:00 hp · 그냥 진행 메모\n", encoding="utf-8")
    assert task_resolve.latest_record_date(d) == "2026-09-10"


# ── 10. 이관 줄 문안과 책갈피 정리 실패 ──────────────────────────────────────────
def test_move_line_is_particle_free(tmp_path):
    src = tmp_path / "tasks" / "a"
    dst = tmp_path / "tasks" / "web-project"
    (src / "t1").mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "t1" / "log.md").write_text("[시작] 2026-09-01 10:00:00 hp · s\n", encoding="utf-8")
    task_move.move_task(source_root=src, dest_root=dst, slug="t1", machine="hp",
                        ts="2026-09-20 09:00:00")
    text = (dst / "t1" / "log.md").read_text(encoding="utf-8")
    assert "방을 옮김: a → web-project" in text
    assert "으로 옮김" not in text
    last = task_resolve._parse_log_line(text.splitlines()[-1])
    assert last["tag"] == "기록" and last["machine"] == "hp"


def test_move_survives_bad_pin_filename(tmp_path):
    src = tmp_path / "tasks" / "a"
    dst = tmp_path / "tasks" / "b"
    (src / "t1").mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "t1" / "log.md").write_text("[시작] 2026-09-01 10:00:00 hp · s\n", encoding="utf-8")
    (src / ".pin.hp~").write_text("t1\n2026-09-01 11:00:00\n", encoding="utf-8")
    (src / ".pin.hp").write_text("t1\n2026-09-01 12:00:00\n", encoding="utf-8")
    result = task_move.move_task(source_root=src, dest_root=dst, slug="t1",
                                 machine="hp", ts="2026-09-20 09:00:00")
    assert (dst / "t1").is_dir()
    assert "옮김" in (dst / "t1" / "log.md").read_text(encoding="utf-8")
    assert result["pin_error"] is None
    assert [p["machine"] for p in result["moved_pins"]] == ["hp"]
    # 규칙 밖 파일은 책갈피로 읽히지 않는다.
    assert [p["machine"] for p in task_resolve.read_pins(src)] == []


def test_move_records_even_if_pin_cleanup_fails(tmp_path, monkeypatch):
    src = tmp_path / "tasks" / "a"
    dst = tmp_path / "tasks" / "b"
    (src / "t1").mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "t1" / "log.md").write_text("[시작] 2026-09-01 10:00:00 hp · s\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("디스크 오류")

    monkeypatch.setattr(task_move, "_move_pins", boom)
    result = task_move.move_task(source_root=src, dest_root=dst, slug="t1",
                                 machine="hp", ts="2026-09-20 09:00:00")
    assert "옮김" in (dst / "t1" / "log.md").read_text(encoding="utf-8")
    assert "디스크 오류" in result["pin_error"]


# ── 12. 설명서 본문과 slug 접두 ───────────────────────────────────────────────
def test_task_doc_body_line_with_created_pattern_kept(home):
    d = home / ".namu" / "tasks" / "p" / "t1"
    d.mkdir(parents=True)
    (d / "task.md").write_text(
        "# t1 — 제목\n📅 생성 2026-07-31 [hp]\n\n## 목적\n"
        "색인을 생성 2026-01-01에 만들기로 했다 유니크낱말\n", encoding="utf-8")
    entry = task_resolve.parse_task_doc(d / "task.md", "p")
    assert "유니크낱말" in entry["detail"]
    assert "📅" not in entry["detail"]
    assert entry["ts"] == "2026-07-31 00:00:00"


@pytest.mark.parametrize("title,slug,want", [
    ("deployment 절차", "deploy", "deployment 절차"),
    ("deploy — 절차", "deploy", "절차"),
    ("deploy: 절차", "deploy", "절차"),
    ("namu-57 — namu-57 — 설명", "namu-57", "설명"),
    ("deploy", "deploy", "deploy"),
])
def test_strip_slug_prefix_word_boundary(title, slug, want):
    assert task_resolve.strip_slug_prefix(title, slug) == want


# ── 6. 기기 이름 규칙 한 곳 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,want", [
    ("hp", "hp"),
    ("samsung", "samsung"),
    ("web", "web"),
    ("3f2a9c1d7e44", "3f2a9c1d7e44"),
    ("a" * 64, "a" * 64),
    ("a" * 70, "a" * 64),
    ("  My-Laptop  ", "My-Laptop"),
    ("집 컴", None),
    ("hp 집", "hp"),
    ("my laptop", "my-laptop"),
    ("../x", "x"),
    ("", None),
    (None, None),
])
def test_normalize_machine_name(raw, want):
    assert task_resolve.normalize_machine_name(raw) == want


def test_config_machine_falls_back_when_unusable(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "HP-DESKTOP")
    assert cfg._resolve_machine("집 컴") == "hp-desktop"
    monkeypatch.setattr("config.platform.node", lambda: "")
    assert cfg._resolve_machine("집 컴") == "unknown"


def test_long_machine_name_parsed_from_log_line():
    """쓰는 쪽이 받는 64자 이름은 읽는 쪽도 machine으로 읽는다."""
    cid = "f" * 64
    got = task_resolve._parse_log_line(f"[기록] 2026-09-01 10:00:00 {cid} · 본문")
    assert got["machine"] == cid and got["text"] == "본문"


def test_clear_pin_if_points_to_swallows_bad_machine(tmp_path):
    assert task_resolve.clear_pin_if_points_to(tmp_path, "집 컴", "t1") is False
