"""namu-27 ② — 낡은 캐시 해소: 훅의 _ensure_db가 'db 파일 없음'뿐 아니라
'yaml과 count 불일치(stale)'일 때도 rebuild_from_yaml()을 수행하는지 검증.

시나리오: 외부 터미널에서 git pull 후(learnings.yaml 갱신) CC/agy를 시작 —
db 파일은 이미 존재하지만 낡은 상태(07-10 실측: yaml 40건 vs db 37건).

test_cache_stale.py의 test_rebuild_self_heals_stale과 같은 패턴(실제 config
모듈 전역을 monkeypatch)을 따른다 — db.rebuild_from_yaml()은 인자 없이
전역 config를 참조하므로, 훅에 넘기는 cfg도 반드시 이 전역 config 모듈이어야
실제 동작을 재현한다.
"""
import importlib.util
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import db as _db

_RECALL_HOOK_SRC = Path(__file__).parent / "hooks" / "session_recall.py"
_INJECT_HOOK_SRC = Path(__file__).parent / "hooks" / "session_inject.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _isolate_cfg(monkeypatch, tmp_path):
    yaml_path = tmp_path / "learnings.yaml"
    db_path = tmp_path / "namu.db"
    monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path, db_path


def test_session_recall_ensure_db_rebuilds_when_stale(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    for i in range(3):
        _db.record(f"task{i}", "success", f"reason{i}", task_type="other",
                   verified_by="human", tags=[])

    # git pull 시뮬레이션: db에서 1행 삭제 → yaml(3) vs db(2) 불일치(stale)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM learnings WHERE rowid IN (SELECT rowid FROM learnings LIMIT 1)")
    assert _db.cache_is_stale(yaml_path, db_path)

    hook = _load_module(_RECALL_HOOK_SRC, "session_recall_hook_test")
    hook._ensure_db(cfg)

    assert not _db.cache_is_stale(yaml_path, db_path)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    assert count == 3


def test_session_inject_ensure_db_rebuilds_when_stale(monkeypatch, tmp_path):
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    for i in range(4):
        _db.record(f"task{i}", "success", f"reason{i}", task_type="other",
                   verified_by="human", tags=[])

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM learnings WHERE rowid IN (SELECT rowid FROM learnings LIMIT 1)")
    assert _db.cache_is_stale(yaml_path, db_path)

    hook = _load_module(_INJECT_HOOK_SRC, "session_inject_hook_test")
    hook._ensure_db(cfg)

    assert not _db.cache_is_stale(yaml_path, db_path)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    assert count == 4


def test_ensure_db_no_op_when_fresh(monkeypatch, tmp_path):
    """이미 최신 상태면 불필요한 rebuild를 하지 않는다(count 불변으로 간접 확인)."""
    yaml_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    for i in range(2):
        _db.record(f"task{i}", "success", f"reason{i}", task_type="other",
                   verified_by="human", tags=[])
    assert not _db.cache_is_stale(yaml_path, db_path)

    hook = _load_module(_RECALL_HOOK_SRC, "session_recall_hook_test2")
    hook._ensure_db(cfg)

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    assert count == 2


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
