"""db.py via 필드(namu-50 출처 꼬리표) 회귀 테스트.

learnings.yaml/SQLite 캐시에 via(어떤 AI/클라이언트가 남겼는지)가 추가된다.
실제 ~/.namu를 건드리지 않도록 test_db_kind.py의 monkeypatch 패턴을 따른다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import db as _db


def _isolate_cfg(monkeypatch, tmp_path):
    yaml_path = tmp_path / "learnings.yaml"
    db_path = tmp_path / "namu.db"
    monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path, db_path


def test_record_stores_via_in_yaml_and_db(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record(
        "task0", "success", "reason0", task_type="other",
        verified_by="human", tags=[], via="claude",
    )

    # yaml에 via 기록됐는지
    yaml_text = yaml_path.read_text(encoding="utf-8")
    assert "via: claude" in yaml_text

    # db에도 via 기록됐는지
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT via FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == ("claude",)


def test_recall_and_search_expose_via(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record(
        "gemini task", "success", "gemini reason", task_type="other",
        verified_by="human", tags=[], via="gemini",
    )

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        recalled = _db.recall(conn, query="gemini")
        searched = _db.search(conn, query="gemini")

    recall_matches = [r for r in recalled if r["id"] == entry_id]
    assert len(recall_matches) == 1
    assert recall_matches[0]["via"] == "gemini"

    search_matches = [r for r in searched["results"] if r["id"] == entry_id]
    assert len(search_matches) == 1
    assert search_matches[0]["via"] == "gemini"


def test_record_without_via_defaults_to_none(monkeypatch, tmp_path):
    """하위호환: via를 안 주면(기존 호출) None으로 저장된다."""
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record("task0", "success", "reason0", task_type="other",
                           verified_by="human", tags=[])

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT via FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == (None,)

    with sqlite3.connect(db_path) as conn:
        recalled = _db.recall(conn, query="task0")
    matches = [r for r in recalled if r["id"] == entry_id]
    assert len(matches) == 1
    assert matches[0]["via"] is None


def test_rebuild_restores_via_from_yaml(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record(
        "task with via", "success", "reason", task_type="other",
        verified_by="human", tags=[], via="chatgpt",
    )

    n = _db.rebuild_from_yaml()
    assert n == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT via FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == ("chatgpt",)


def test_rebuild_defaults_missing_via_to_none(monkeypatch, tmp_path):
    """옛(via 키 없는) yaml 항목은 rebuild 시 via가 None으로 복원된다(회귀)."""
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as f:
        f.write(
            "---\nid: OLD0001\ntask: old task\noutcome: success\n"
            "reason: old reason\ntask_type: other\n"
            "timestamp: 2025-01-01T00:00:00+00:00\n"
            "machine: test\nverified_by: human\ntags: []\nkind: lesson\n"
        )

    n = _db.rebuild_from_yaml()
    assert n == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT via FROM learnings WHERE id = ?", ("OLD0001",)
        ).fetchone()
    assert row == (None,)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
