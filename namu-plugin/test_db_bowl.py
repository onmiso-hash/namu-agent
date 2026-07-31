"""db.py 축(axis)·search_bowl 회귀 테스트 (namu-57 2단계 1단위 — 코어 조회 계층).

learnings/tasks/profile 3그릇을 같은 축 집합(query/project/task/machine/via/
since/until)으로 조회할 수 있는지 검증한다. 실제 ~/.namu는 절대 건드리지 않는다:
learnings/profile은 cfg.LEARNINGS_YAML_PATH/PROFILE_YAML_PATH/NAMU_DB_PATH를
tmp_path로 monkeypatch(test_db_via.py/test_profile.py 패턴), tasks는 HOME을
tmp 아래 가짜 홈으로 격리(test_task_resolve.py의 fake_home 패턴)한다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

import config as cfg
import db as _db
import profile as _profile


def _isolate_cfg(monkeypatch, tmp_path):
    yaml_path = tmp_path / "learnings.yaml"
    db_path = tmp_path / "namu.db"
    profile_path = tmp_path / "profile.yaml"
    monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
    monkeypatch.setattr(cfg, "PROFILE_YAML_PATH", profile_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path, db_path, profile_path


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """실제 ~/.namu를 건드리지 않도록 HOME을 tmp 아래 가짜 홈으로 격리(namu-33 교훈)."""
    home = tmp_path / "fake_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _make_pool_task(home: Path, project: str, slug: str, log_body: str) -> Path:
    task_dir = home / ".namu" / "tasks" / project / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    (task_dir / "log.md").write_text(log_body, encoding="utf-8")
    return task_dir


# ---------------------------------------------------------------------------
# ① 인자 없는 기존 호출 — 하위 호환
# ---------------------------------------------------------------------------


def test_search_no_new_args_behaves_as_before(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("gemini task", "success", "gemini reason", task_type="other",
               verified_by="human", tags=[], via="gemini")
    _db.record("other task", "failure", "other reason", task_type="other",
               verified_by="human", tags=[])

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search(conn, "gemini")

    assert len(result["results"]) == 1
    assert result["results"][0]["task"] == "gemini task"
    assert result["summary"] == {"success": 1, "failure": 0, "partial": 0}


def test_search_positional_call_still_works(monkeypatch, tmp_path):
    """mcp_server.py가 위치 인자로 호출하는 형태(conn, query, outcome_filter, limit)."""
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("t1", "success", "r1", task_type="other", verified_by="human", tags=[])
    _db.record("t2", "failure", "r2", task_type="other", verified_by="human", tags=[])

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search(conn, "t", "success", 5)

    assert len(result["results"]) == 1
    assert result["results"][0]["task"] == "t1"


# ---------------------------------------------------------------------------
# ② 검색어 없이 축만으로 조회
# ---------------------------------------------------------------------------


def test_search_without_query_filters_by_axis_only(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("task-hp", "success", "hp에서 한 일", task_type="other",
               verified_by="human", tags=[], via="claude")
    _db.record("task-samsung", "success", "samsung에서 한 일", task_type="other",
               verified_by="human", tags=[], via="gemini")

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search(conn, via="claude")

    assert len(result["results"]) == 1
    assert result["results"][0]["task"] == "task-hp"


def test_search_bowl_without_query_returns_all_filtered(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("task-a", "success", "reason a", task_type="other",
               verified_by="human", tags=[], via="claude")
    _db.record("task-b", "success", "reason b", task_type="other",
               verified_by="human", tags=[], via="gemini")

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search_bowl(conn, bowl="learnings", via="claude")

    assert result["bowl"] == "learnings"
    assert result["count"] == 1
    assert result["results"][0]["task"] == "task-a"


# ---------------------------------------------------------------------------
# ③ until에 날짜만 줬을 때 그날 기록 포함
# ---------------------------------------------------------------------------


def test_search_until_date_only_includes_that_day(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    entry_id = _db.record("dated task", "success", "reason", task_type="other",
                           verified_by="human", tags=[])

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        # 오늘 기록된 timestamp를 오늘 날짜로 until을 걸어도 포함돼야 한다.
        today = conn.execute(
            "SELECT substr(timestamp, 1, 10) FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()[0]
        result = _db.search(conn, until=today)

    assert any(r["id"] == entry_id for r in result["results"])


def test_search_until_date_only_excludes_next_day(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.init_db()
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        conn.execute(
            """INSERT INTO learnings
               (id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags, kind, via)
               VALUES ('X1', '2026-07-25T10:00:00+00:00', 'future task', 'other', 'success',
                       'reason', 'test', 'human', '[]', 'lesson', NULL)"""
        )
        conn.commit()
        result = _db.search(conn, until="2026-07-24")

    assert all(r["id"] != "X1" for r in result["results"])


# ---------------------------------------------------------------------------
# ④ bowl 3종 분기
# ---------------------------------------------------------------------------


def test_search_bowl_learnings(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("learn task", "success", "learn reason", task_type="other",
               verified_by="human", tags=[])

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search_bowl(conn, bowl="learnings", query="learn")

    assert result["bowl"] == "learnings"
    assert result["count"] == 1
    assert "summary" in result


def test_search_bowl_tasks(monkeypatch, tmp_path, fake_home):
    _isolate_cfg(monkeypatch, tmp_path)
    _make_pool_task(
        fake_home, "namu-agent", "namu-57-core",
        "# log\n[결정] 2026-07-25 10:00:00 hp · 코어 조회 계층 설계\n",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        _db.init_db()
        result = _db.search_bowl(conn, bowl="tasks")

    assert result["bowl"] == "tasks"
    assert result["count"] == 1
    assert result["results"][0]["text"] == "코어 조회 계층 설계"
    assert "summary" not in result


def test_search_bowl_profile(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _profile.record_fact(
        subject="user", statement="선호 언어는 한국어", source="사용자가 직접 말함",
        via="claude",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search_bowl(conn, bowl="profile", query="한국어")

    assert result["bowl"] == "profile"
    assert result["count"] == 1
    assert result["results"][0]["subject"] == "user"


def test_search_bowl_unknown_bowl_raises(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        with pytest.raises(ValueError):
            _db.search_bowl(conn, bowl="nope")


# ---------------------------------------------------------------------------
# ⑤ tasks에서 query 필터가 limit보다 먼저 적용되는지
# ---------------------------------------------------------------------------


def test_search_bowl_tasks_query_filter_applies_before_limit(monkeypatch, tmp_path, fake_home):
    _isolate_cfg(monkeypatch, tmp_path)
    _make_pool_task(
        fake_home, "namu-agent", "namu-57-core",
        "# log\n"
        "[결정] 2026-07-25 09:00:00 hp · 관련 없는 줄 A\n"
        "[결정] 2026-07-25 10:00:00 hp · 관련 없는 줄 B\n"
        "[결정] 2026-07-25 11:00:00 hp · 목표 키워드 포함 줄\n",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        _db.init_db()
        # limit=1이지만 최신순으로 자르면 목표 줄이 안 걸릴 위치인지 확인하기 위해
        # query로 걸러 낸 뒤에 limit이 적용되는지 검증한다.
        result = _db.search_bowl(conn, bowl="tasks", query="목표", limit=1)

    assert result["count"] == 1
    assert result["results"][0]["text"] == "목표 키워드 포함 줄"


def test_search_bowl_tasks_query_filter_no_match_after_limit_would_hide_it(monkeypatch, tmp_path, fake_home):
    """limit을 먼저 적용했다면 사라졌을 결과가, query 필터를 먼저 적용하면 남는다."""
    _isolate_cfg(monkeypatch, tmp_path)
    _make_pool_task(
        fake_home, "namu-agent", "namu-57-core",
        "# log\n"
        "[결정] 2026-07-25 09:00:00 hp · 오래된 목표 키워드 줄\n"
        "[결정] 2026-07-25 10:00:00 hp · 무관 줄 1\n"
        "[결정] 2026-07-25 11:00:00 hp · 무관 줄 2\n"
        "[결정] 2026-07-25 12:00:00 hp · 무관 줄 3\n",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        _db.init_db()
        result = _db.search_bowl(conn, bowl="tasks", query="목표", limit=1)

    assert result["count"] == 1
    assert result["results"][0]["text"] == "오래된 목표 키워드 줄"


# ---------------------------------------------------------------------------
# ⑥ learnings/profile에 project를 주면 ValueError
# ---------------------------------------------------------------------------


def test_search_bowl_learnings_with_project_raises(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        with pytest.raises(ValueError):
            _db.search_bowl(conn, bowl="learnings", project="namu-agent")


def test_search_bowl_profile_with_project_raises(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        with pytest.raises(ValueError):
            _db.search_bowl(conn, bowl="profile", project="namu-agent")


def test_search_bowl_tasks_with_project_is_allowed(monkeypatch, tmp_path, fake_home):
    """project는 tasks 전용 축이라 tasks bowl에서는 정상 동작해야 한다."""
    _isolate_cfg(monkeypatch, tmp_path)
    _make_pool_task(
        fake_home, "namu-agent", "namu-57-core",
        "# log\n[결정] 2026-07-25 10:00:00 hp · 프로젝트 필터 확인\n",
    )
    _make_pool_task(
        fake_home, "onnamu-project", "deploy-1",
        "# log\n[시작] 2026-07-22 10:00:00 samsung · 배포\n",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        _db.init_db()
        result = _db.search_bowl(conn, bowl="tasks", project="namu-agent")

    assert result["count"] == 1
    assert result["results"][0]["project"] == "namu-agent"


# ---------------------------------------------------------------------------
# ⑦ (via <label>) 꼬리표 파싱·필터 — learnings via 필터도 함께 확인
# ---------------------------------------------------------------------------


def test_search_bowl_learnings_via_filter(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _db.record("claude task", "success", "claude reason", task_type="other",
               verified_by="human", tags=[], via="claude")
    _db.record("gemini task", "success", "gemini reason", task_type="other",
               verified_by="human", tags=[], via="gemini")

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search_bowl(conn, bowl="learnings", via="claude")

    assert result["count"] == 1
    assert result["results"][0]["task"] == "claude task"


def test_search_bowl_tasks_via_tail_parsed_and_filtered(monkeypatch, tmp_path, fake_home):
    """`(via claude)` 꼬리표가 파싱돼 via 축으로 걸린다(namu-50 웹 기록 형식)."""
    _isolate_cfg(monkeypatch, tmp_path)
    _make_pool_task(
        fake_home, "namu-agent", "namu-57-web",
        "# log\n"
        "[결정] 2026-07-25 15:40:00 web · 웹에서 남김 (via claude)\n"
        "[결정] 2026-07-25 16:00:00 hp · hp에서 남김\n",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        _db.init_db()
        result = _db.search_bowl(conn, bowl="tasks", via="claude")

    assert result["count"] == 1
    assert result["results"][0]["text"] == "웹에서 남김"
    assert result["results"][0]["via"] == "claude"


def test_search_bowl_profile_via_filter(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    _profile.record_fact(
        subject="user", statement="사실 A", source="src", via="claude",
    )
    _profile.record_fact(
        subject="user", statement="사실 B", source="src", via="gemini",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        result = _db.search_bowl(conn, bowl="profile", via="claude")

    assert result["count"] == 1
    assert result["results"][0]["summary"] == "사실 A"


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
