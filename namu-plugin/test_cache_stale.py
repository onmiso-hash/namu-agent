"""
cache_is_stale / count_yaml_docs 단위 테스트.
실제 learnings.yaml 을 건드리지 않고 임시 파일만 사용.
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

# namu-plugin 디렉터리를 sys.path에 추가 (직접 실행 시)
sys.path.insert(0, str(Path(__file__).parent))

import db as _db  # noqa: E402 (path manipulation must come first)


def _make_yaml(path: Path, n: int) -> None:
    """n개의 최소 entry를 yaml 파일에 기록."""
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                f"---\nid: FAKE{i:04d}\ntask: t{i}\noutcome: success\n"
                f"reason: r{i}\ntask_type: other\ntimestamp: 2025-01-01T00:00:00+00:00\n"
                f"machine: test\nverified_by: human\ntags: []\n"
            )


def _make_db(path: Path, n: int) -> None:
    """n개의 row를 가진 최신 스키마 SQLite DB 생성(kind/via 컬럼 포함)."""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS learnings ("
            "id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, task TEXT NOT NULL,"
            "task_type TEXT, outcome TEXT, reason TEXT NOT NULL,"
            "machine TEXT, verified_by TEXT, tags TEXT, kind TEXT, via TEXT);"
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO learnings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"FAKE{i:04d}", "2025-01-01T00:00:00+00:00", f"t{i}",
                 "other", "success", f"r{i}", "test", "human", "[]", "lesson", None),
            )


def _make_db_old_schema(path: Path, n: int) -> None:
    """kind 컬럼이 없는 옛(0.1.25) 스키마 DB 생성 — 스키마 드리프트 재현용."""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS learnings ("
            "id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, task TEXT NOT NULL,"
            "task_type TEXT, outcome TEXT NOT NULL, reason TEXT NOT NULL,"
            "machine TEXT, verified_by TEXT, tags TEXT);"
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO learnings VALUES (?,?,?,?,?,?,?,?,?)",
                (f"FAKE{i:04d}", "2025-01-01T00:00:00+00:00", f"t{i}",
                 "other", "success", f"r{i}", "test", "human", "[]"),
            )


def _make_db_missing_via(path: Path, n: int) -> None:
    """via 컬럼만 없는(kind는 있는) 0.1.27 스키마 DB 생성 — namu-50 스키마 드리프트 재현용."""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS learnings ("
            "id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, task TEXT NOT NULL,"
            "task_type TEXT, outcome TEXT, reason TEXT NOT NULL,"
            "machine TEXT, verified_by TEXT, tags TEXT, kind TEXT);"
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO learnings VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"FAKE{i:04d}", "2025-01-01T00:00:00+00:00", f"t{i}",
                 "other", "success", f"r{i}", "test", "human", "[]", "lesson"),
            )


def test_fresh_is_not_stale():
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"
        _make_yaml(yaml_path, 3)
        _make_db(db_path, 3)
        assert not _db.cache_is_stale(yaml_path, db_path), "count 일치 → stale 아님"


def test_yaml_more_than_db_is_stale():
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"
        _make_yaml(yaml_path, 4)  # yaml에 entry 4개
        _make_db(db_path, 3)      # db에 row 3개 (git pull 시뮬레이션)
        assert _db.cache_is_stale(yaml_path, db_path), "yaml > db → stale"


def test_old_schema_missing_kind_is_stale():
    """개수는 같아도 옛 스키마(kind 컬럼 없음)면 stale — 0.1.26 배포 회귀 재현.
    스키마 변경 릴리스에서 개수만 같은 옛 db를 방치하면 새 코드가 kind를 쿼리하다
    깨지므로, cache_is_stale이 개수뿐 아니라 스키마도 봐야 한다."""
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"
        _make_yaml(yaml_path, 3)
        _make_db_old_schema(db_path, 3)  # 개수 일치, but kind 컬럼 없음
        assert _db.cache_is_stale(yaml_path, db_path), "옛 스키마(kind 없음) → stale"


def test_old_schema_missing_via_is_stale():
    """개수·kind는 같아도 via 컬럼이 없는 0.1.27 스키마면 stale — namu-50 스키마
    드리프트 재현(0.1.26의 kind 갭과 동일 패턴)."""
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"
        _make_yaml(yaml_path, 3)
        _make_db_missing_via(db_path, 3)  # 개수 일치, kind 있음, but via 컬럼 없음
        assert _db.cache_is_stale(yaml_path, db_path), "옛 스키마(via 없음) → stale"


def test_rebuild_from_missing_via_schema_restores_none(monkeypatch):
    """via 컬럼 없는 옛 db + via 없는 yaml → rebuild 후 via가 None으로 복원."""
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"

        import config as cfg
        monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
        monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
        monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")

        _make_yaml(yaml_path, 3)  # via 키 없는 옛 yaml
        _make_db_missing_via(db_path, 3)

        assert _db.cache_is_stale(yaml_path, db_path)
        _db.rebuild_from_yaml()
        assert not _db.cache_is_stale(yaml_path, db_path)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT via FROM learnings").fetchall()
        assert rows == [(None,)] * 3


def test_missing_yaml_not_stale_when_db_empty():
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"  # 파일 없음
        db_path   = Path(td) / "namu.db"
        _make_db(db_path, 0)
        assert not _db.cache_is_stale(yaml_path, db_path), "yaml 없고 db 0행 → 일치"


def test_rebuild_self_heals_stale(monkeypatch):
    """db row 1개 삭제로 불일치 유발 → rebuild → 복구 확인 (실제 db.py 사용)."""
    with tempfile.TemporaryDirectory() as td:
        yaml_path = Path(td) / "learnings.yaml"
        db_path   = Path(td) / "namu.db"

        # config 경로를 임시 파일로 교체
        import config as cfg
        monkeypatch.setattr(cfg, "LEARNINGS_YAML_PATH", yaml_path)
        monkeypatch.setattr(cfg, "NAMU_DB_PATH", db_path)
        monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")

        # 실제 record()로 3개 기록
        for i in range(3):
            _db.record(f"task{i}", "success", f"reason{i}", task_type="other",
                       verified_by="human", tags=[])

        # 정상 상태 확인
        assert not _db.cache_is_stale(yaml_path, db_path)

        # row 1개 DELETE → 불일치 유발
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM learnings LIMIT 1")

        assert _db.cache_is_stale(yaml_path, db_path), "row 삭제 후 stale"

        # rebuild로 복구
        _db.rebuild_from_yaml()

        assert not _db.cache_is_stale(yaml_path, db_path), "rebuild 후 복구"
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
        assert count == 3, f"row 수 복구 실패: {count}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
