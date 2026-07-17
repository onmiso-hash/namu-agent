"""db.py kind 필드(namu-49 Unit A) 회귀 테스트.

learnings.yaml/SQLite 캐시에 kind('lesson'/'note')가 추가되며 outcome이
nullable로 완화됐다. 실제 ~/.namu를 건드리지 않도록 test_cache_stale.py의
monkeypatch 패턴을 따른다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

import config as cfg
import db as _db


def _isolate_cfg(monkeypatch, tmp_path):
    yaml_path = tmp_path / "learnings.yaml"
    db_path = tmp_path / "namu.db"
    monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path, db_path


def test_lesson_requires_outcome(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        _db.record("task0", None, "reason0", kind="lesson")


def test_lesson_default_kind_backward_compat(monkeypatch, tmp_path):
    """kind 인자를 안 주면 기존과 동일하게 'lesson'."""
    _isolate_cfg(monkeypatch, tmp_path)
    entry_id = _db.record("task0", "success", "reason0", task_type="other",
                           verified_by="human", tags=[])
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        row = conn.execute(
            "SELECT kind, outcome FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == ("lesson", "success")


def test_note_without_outcome_records_and_recalls(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record(
        "대화 요약", None, "사용자가 이 대화를 기억해달라고 요청함",
        task_type="other", verified_by="human", tags=[], kind="note",
    )

    with sqlite3.connect(db_path) as conn:
        results = _db.recall(conn, query="대화")
    matches = [r for r in results if r["id"] == entry_id]
    assert len(matches) == 1
    assert matches[0]["kind"] == "note"
    assert matches[0]["outcome"] is None


def test_note_with_outcome_is_validated(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    # 유효한 outcome이면 통과
    entry_id = _db.record("task", "success", "reason", kind="note")
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        row = conn.execute(
            "SELECT kind, outcome FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == ("note", "success")

    # 무효한 outcome이면 거부
    with pytest.raises(ValueError):
        _db.record("task2", "bogus", "reason2", kind="note")


def test_invalid_kind_rejected(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        _db.record("task", "success", "reason", kind="fact")


def test_rebuild_defaults_missing_kind_to_lesson(monkeypatch, tmp_path):
    """kind 필드가 없는 옛 yaml 항목은 rebuild 시 'lesson'으로 채워진다."""
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as f:
        f.write(
            "---\nid: OLD0001\ntask: old task\noutcome: success\n"
            "reason: old reason\ntask_type: other\n"
            "timestamp: 2025-01-01T00:00:00+00:00\n"
            "machine: test\nverified_by: human\ntags: []\n"
        )

    n = _db.rebuild_from_yaml()
    assert n == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT kind, outcome FROM learnings WHERE id = ?", ("OLD0001",)
        ).fetchone()
    assert row == ("lesson", "success")


def test_rebuild_preserves_note_kind_and_null_outcome(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    entry_id = _db.record(
        "note task", None, "note reason", kind="note",
    )

    n = _db.rebuild_from_yaml()
    assert n == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT kind, outcome FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == ("note", None)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
