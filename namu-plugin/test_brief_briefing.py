"""짧은 브리핑·압축 뒤 브리핑(2026-10-09 사용자 결정) 테스트.

세션을 켤 때는 쪽지와 이어받을 작업만, 압축 직후에는 맨 위 작업의 `다음:` 블록만
싣는다. 최근 활동·관련 교훈·다른 방 목록은 `/namu`로 볼 때만 나온다.
가짜 홈·git 체크 스텁은 test_session_context의 픽스처를 그대로 쓴다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as _cfg
import memo as _memo
import session_context as _sc
from test_session_context import (  # noqa: F401 — autouse 픽스처를 이 파일에도 건다
    _fake_home,
    _make_other_room_task,
    _make_task,
    _setup_mem_db,
    _stub_git_check,
)

_HOOKS = Path(__file__).parent / "hooks"


@pytest.fixture(autouse=True)
def _no_real_memos(monkeypatch):
    """쪽지 경로(cfg.MEMO_YAML_PATH)는 import 때 실제 ~/.namu로 정해진다 — 가짜 홈으로
    바꿔도 진짜 쪽지가 읽히므로 기본은 빈 목록으로 막고, 쪽지 테스트만 따로 채운다."""
    monkeypatch.setattr(_memo, "load_all", lambda paths=None: [])


def _two_tasks(tmp_path):
    tasks_root = _cfg.tasks_dir_for(tmp_path)
    _make_task(tasks_root, "older-task", "hp", "옛 작업 다음 할 일",
               log_lines=["[시작] 2026-06-28 09:00:00 hp · 시작"])
    _make_task(tasks_root, "newer-task", "hp", "새 작업 다음 할 일",
               log_lines=["[시작] 2026-06-29 09:00:00 hp · 시작"])


def test_brief_drops_activity_and_learnings(tmp_path):
    _two_tasks(tmp_path)
    conn = _setup_mem_db([
        ("FAKE0001", "2026-01-01T00:00:00+00:00", "newer-task", "other",
         "success", "이유0", "hp", "human", "[]"),
    ])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()

    assert md is not None
    assert "## 🌳 NAMU — 이어받기" in md
    assert "### 🕘 최근 활동" not in md
    assert "### 💡 관련 교훈" not in md
    assert "`/namu`" in md


def test_brief_only_top_task_has_next(tmp_path):
    _two_tasks(tmp_path)
    conn = _setup_mem_db([])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()

    assert "### 📂 이 방 열린 작업 2개" in md
    assert "새 작업 다음 할 일" in md
    assert "옛 작업 다음 할 일" not in md
    assert "older-task" in md  # 제목 줄은 남는다


def test_brief_other_rooms_are_one_count_line(tmp_path):
    _two_tasks(tmp_path)
    _make_other_room_task("onnamu-project", "deploy-1", "다른 방 다음",
                          log_lines=["[시작] 2026-07-01 09:00:00 hp · 시작"])
    _make_other_room_task("naite", "read-1", "나이테 다음",
                          log_lines=["[시작] 2026-07-02 09:00:00 hp · 시작"])
    conn = _setup_mem_db([])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()

    assert "다른 방에 열린 작업 2개" in md
    assert "deploy-1" not in md and "read-1" not in md


def test_brief_memo_has_id_but_no_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(_memo, "load_all", lambda paths=None: [{
        "id": "01KYKFDRAAAAAAAAAAAAAAAAAA", "timestamp": "2026-07-28T13:23:00",
        "machine": "web", "summary": "조사 자료", "reason": "생략", "body": "생략",
    }])
    conn = _setup_mem_db([])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()

    memo_line = next(l for l in md.splitlines() if "조사 자료" in l)
    assert "id `" in memo_line
    assert "2026-07-28" not in memo_line and "web" not in memo_line


def test_brief_welcome_when_nothing(tmp_path):
    conn = _setup_mem_db([])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()
    assert md == _sc._WELCOME_MARKDOWN


def test_brief_no_open_task_but_other_room(tmp_path):
    _make_other_room_task("onnamu-project", "deploy-1", "다른 방 다음",
                          log_lines=["[시작] 2026-07-01 09:00:00 hp · 시작"])
    conn = _setup_mem_db([])
    md = _sc.build_brief_markdown(conn, "hp", tmp_path)
    conn.close()
    assert "에는 열린 작업이 없습니다" in md
    assert "다른 방에 열린 작업 1개" in md


def test_compact_only_top_task_block(tmp_path):
    _two_tasks(tmp_path)
    _make_other_room_task("onnamu-project", "deploy-1", "다른 방 다음",
                          log_lines=["[시작] 2026-07-01 09:00:00 hp · 시작"])
    md = _sc.build_compact_markdown(tmp_path)

    assert md.startswith("## 🌳 NAMU — 압축 뒤 이어받기")
    assert "newer-task" in md and "새 작업 다음 할 일" in md
    assert "older-task" not in md
    assert "deploy-1" not in md and "다른 방" not in md.replace("다른 방 목록", "")


def test_compact_none_without_open_task(tmp_path):
    assert _sc.build_compact_markdown(tmp_path) is None


def _run_recall_hook(fake_home: Path, stdin_data: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    env.update({"HOME": str(fake_home), "NAMU_MACHINE": "hp", "PYTHONIOENCODING": "utf-8"})
    return subprocess.run(
        [sys.executable, str(_HOOKS / "session_recall.py")],
        input=json.dumps(stdin_data), capture_output=True, encoding="utf-8",
        env=env, timeout=15,
    )


def test_recall_hook_compact_source(tmp_path):
    fake_home = tmp_path / "fake_home"
    (fake_home / ".namu" / "memory").mkdir(parents=True)
    project_dir = tmp_path / "project"
    _make_task(fake_home / ".namu" / "tasks" / "project", "hook-task", "hp", "훅 다음 할 일")

    result = _run_recall_hook(fake_home, {"cwd": str(project_dir), "source": "compact"})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "압축 뒤 이어받기" in ctx and "훅 다음 할 일" in ctx
    # 압축 경로는 색인(db)을 만들지 않는다
    assert not (fake_home / ".namu" / "db" / "namu.db").exists()


def test_recall_hook_compact_without_task_prints_nothing(tmp_path):
    fake_home = tmp_path / "fake_home"
    (fake_home / ".namu" / "memory").mkdir(parents=True)
    result = _run_recall_hook(fake_home, {"cwd": str(tmp_path / "empty"), "source": "compact"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_recall_hook_startup_is_brief(tmp_path):
    fake_home = tmp_path / "fake_home"
    (fake_home / ".namu" / "memory").mkdir(parents=True)
    (fake_home / ".namu" / "memory" / "learnings.yaml").write_text("", encoding="utf-8")
    project_dir = tmp_path / "project"
    _make_task(fake_home / ".namu" / "tasks" / "project", "hook-task", "hp", "훅 다음 할 일")

    result = _run_recall_hook(fake_home, {"cwd": str(project_dir), "source": "startup"})
    data = json.loads(result.stdout)
    assert "## 🌳 NAMU — 이어받기" in data["systemMessage"]


def test_hooks_json_checks_run_only_outside_compact():
    hooks = json.loads((_HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    groups = hooks["SessionStart"]
    recall = [g for g in groups if any("session_recall.py" in h["command"] for h in g["hooks"])]
    assert len(recall) == 1 and "matcher" not in recall[0]
    checks = [g for g in groups if g is not recall[0]]
    commands = " ".join(h["command"] for g in checks for h in g["hooks"])
    for name in ("repo_sync_check.py", "version_drift_check.py", "weekly_review_check.py"):
        assert name in commands
    # Grok은 새 세션을 "new", 이어 열기를 "load"로 보낸다(2026-10-09 실측) — 빠뜨리면
    # Grok에서는 검사가 시작할 때도 안 돈다. "compact"만은 들어가면 안 된다.
    for g in checks:
        names = set(g.get("matcher", "").split("|"))
        assert names == {"startup", "resume", "clear", "new", "load"}
