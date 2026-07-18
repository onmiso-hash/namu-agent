"""config.DataPaths / data_paths_for() 이음새 회귀 테스트 (namu-53).

공용 라우팅 MCP 서비스(별도 repo)가 이 코어를 의존성으로 재사용해, 요청마다 다른
데이터 루트(`/store/users/<키>`)를 넘길 수 있도록 db.py/profile.py의 쓰기 함수에
`paths` 인자를 연 것을 검증한다. 핵심 불변식: paths를 안 넘기면(개인/stdio 기본
동작) 지금과 바이트 단위로 동일하게 전역 ~/.namu(테스트에서는 monkeypatch한
cfg.LEARNINGS_YAML_PATH/cfg.PROFILE_YAML_PATH/cfg.NAMU_DB_PATH)에 기록된다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import db as _db
import profile as _profile


def _isolate_cfg(monkeypatch, tmp_path):
    """test_db_kind.py/test_profile.py와 동일한 격리 패턴 — 전역 상수를 tmp 하위로."""
    yaml_path = tmp_path / "learnings.yaml"
    profile_path = tmp_path / "profile.yaml"
    db_path = tmp_path / "namu.db"
    monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "PROFILE_YAML_PATH", profile_path)
    monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path, profile_path, db_path


def test_data_paths_for_no_root_returns_current_module_constants(monkeypatch, tmp_path):
    """root 없이 호출하면 재계산 없이 기존 모듈 상수 3개를 그대로 담는다."""
    yaml_path, profile_path, db_path = _isolate_cfg(monkeypatch, tmp_path)

    p = cfg.data_paths_for()

    assert p.learnings_yaml == cfg.LEARNINGS_YAML_PATH == yaml_path
    assert p.profile_yaml == cfg.PROFILE_YAML_PATH == profile_path
    assert p.db_path == cfg.NAMU_DB_PATH == db_path


def test_data_paths_for_with_root_derives_paths(tmp_path):
    root = tmp_path / "users" / "alice"

    p = cfg.data_paths_for(root)

    assert p.learnings_yaml == root / "memory" / "learnings.yaml"
    assert p.profile_yaml == root / "memory" / "profile.yaml"
    assert p.db_path == root / "db" / "namu.db"


def test_data_paths_for_with_string_root_derives_paths(tmp_path):
    root = tmp_path / "users" / "bob"

    p = cfg.data_paths_for(str(root))

    assert p.learnings_yaml == root / "memory" / "learnings.yaml"
    assert p.db_path == root / "db" / "namu.db"


def test_data_paths_is_frozen(tmp_path):
    p = cfg.data_paths_for(tmp_path)
    with __import__("pytest").raises(Exception):
        p.db_path = tmp_path / "other.db"


def test_record_with_explicit_paths_writes_only_under_that_root(monkeypatch, tmp_path):
    """전역(monkeypatch된 cfg 상수)은 안 건드리고, tmp_a 아래에만 쓴다."""
    global_yaml, global_profile, global_db = _isolate_cfg(monkeypatch, tmp_path / "global")

    tmp_a = tmp_path / "tenant_a"
    paths_a = cfg.data_paths_for(tmp_a)

    entry_id = _db.record(
        "task a", "success", "reason a", paths=paths_a,
    )

    # tenant_a 아래에 생성됨
    assert paths_a.learnings_yaml.exists()
    assert paths_a.db_path.exists()

    with sqlite3.connect(paths_a.db_path) as conn:
        row = conn.execute(
            "SELECT id, task FROM learnings WHERE id = ?", (entry_id,)
        ).fetchone()
    assert row == (entry_id, "task a")

    # 전역(monkeypatch된 cfg 경로)은 전혀 건드리지 않음
    assert not global_yaml.exists()
    assert not global_db.exists()


def test_record_fact_with_explicit_paths_isolated_from_global(monkeypatch, tmp_path):
    _, global_profile, _ = _isolate_cfg(monkeypatch, tmp_path / "global")

    tmp_a = tmp_path / "tenant_a"
    paths_a = cfg.data_paths_for(tmp_a)

    entry_id = _profile.record_fact(
        subject="alice", statement="선호 언어는 한국어", source="본인 발화",
        paths=paths_a,
    )

    assert paths_a.profile_yaml == tmp_a / "memory" / "profile.yaml"
    assert paths_a.profile_yaml.exists()
    assert not global_profile.exists()

    docs = _profile.load_all(paths=paths_a)
    assert len(docs) == 1
    assert docs[0]["id"] == entry_id
    assert docs[0]["subject"] == "alice"

    active_docs = _profile.active(paths=paths_a)
    assert len(active_docs) == 1
    assert active_docs[0]["id"] == entry_id


def test_two_tenants_are_fully_isolated_from_each_other(monkeypatch, tmp_path):
    """서로 다른 root로 각각 record하면 교차오염 없이 완전히 격리된다."""
    _isolate_cfg(monkeypatch, tmp_path / "global")

    tmp_a = tmp_path / "tenant_a"
    tmp_b = tmp_path / "tenant_b"
    paths_a = cfg.data_paths_for(tmp_a)
    paths_b = cfg.data_paths_for(tmp_b)

    id_a = _db.record("task a", "success", "reason a", paths=paths_a)
    id_b = _db.record("task b", "failure", "reason b", paths=paths_b)

    fact_a = _profile.record_fact(
        subject="alice", statement="A", source="s1", paths=paths_a,
    )
    fact_b = _profile.record_fact(
        subject="bob", statement="B", source="s2", paths=paths_b,
    )

    with sqlite3.connect(paths_a.db_path) as conn:
        rows_a = conn.execute("SELECT id FROM learnings").fetchall()
    with sqlite3.connect(paths_b.db_path) as conn:
        rows_b = conn.execute("SELECT id FROM learnings").fetchall()

    assert rows_a == [(id_a,)]
    assert rows_b == [(id_b,)]

    docs_a = _profile.load_all(paths=paths_a)
    docs_b = _profile.load_all(paths=paths_b)
    assert [d["id"] for d in docs_a] == [fact_a]
    assert [d["id"] for d in docs_b] == [fact_b]

    # 물리적으로도 겹치지 않는다
    assert paths_a.learnings_yaml != paths_b.learnings_yaml
    assert paths_a.db_path != paths_b.db_path
    assert not paths_a.learnings_yaml.exists() or paths_a.learnings_yaml.read_text(
        encoding="utf-8"
    ).count("task b") == 0


def test_rebuild_from_yaml_with_explicit_paths(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path / "global")

    tmp_a = tmp_path / "tenant_a"
    paths_a = cfg.data_paths_for(tmp_a)

    _db.record("t1", "success", "r1", paths=paths_a)
    _db.record("t2", "failure", "r2", paths=paths_a)

    n = _db.rebuild_from_yaml(paths=paths_a)
    assert n == 2

    with sqlite3.connect(paths_a.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    assert count == 2


def test_init_db_with_explicit_paths_creates_schema_only_there(tmp_path):
    tmp_a = tmp_path / "tenant_a"
    paths_a = cfg.data_paths_for(tmp_a)

    _db.init_db(paths=paths_a)

    assert paths_a.db_path.exists()
    with sqlite3.connect(paths_a.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "learnings" in tables


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
