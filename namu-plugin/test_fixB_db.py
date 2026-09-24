"""리뷰 B 수정(2026-09-25) 회귀 시험 — db.py 쪽.

리뷰어가 결함을 재현한 시험(`reviewB/test_reviewB_db.py`)의 단언을 뒤집은 것이다.
실제 ~/.namu는 건드리지 않는다(HOME·paths 모두 tmp).
"""
import sqlite3
import threading
import warnings
from contextlib import closing

import pytest

import config as cfg
import db as _db
import memo as _memo


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    p = cfg.data_paths_for(tmp_path / "data")
    p.db_path.parent.mkdir(parents=True, exist_ok=True)
    p.learnings_yaml.parent.mkdir(parents=True, exist_ok=True)
    return p


def _search(p, bowl, **kw):
    with closing(sqlite3.connect(p.db_path)) as conn:
        return _db.search_bowl(conn, bowl=bowl, paths=p, **kw)


# ── 3. 재색인 도중 원본이 바뀌어도 색인이 "최신"으로 굳지 않는다 ─────────────────
def test_rebuild_race_does_not_leave_index_stale(paths, monkeypatch):
    _memo.add(summary="첫째쪽지", reason="r", body="b", paths=paths)
    orig_rows = _db._bowl_rows

    def rows_then_concurrent_write(bowl, p):
        rows = orig_rows(bowl, p)
        if bowl == "memo":
            _memo.add(summary="둘째쪽지", reason="r", body="b", paths=p)
        return rows

    monkeypatch.setattr(_db, "_bowl_rows", rows_then_concurrent_write)
    _db.rebuild_bowl_index("memo", paths)
    monkeypatch.setattr(_db, "_bowl_rows", orig_rows)

    # 서명을 원본보다 먼저 쟀으므로 다음 판정은 "낡음"이다.
    assert _db.bowl_index_is_stale("memo", paths) is True
    # 그래서 다음 검색이 다시 만들고 둘째 쪽지가 잡힌다.
    assert _search(paths, "memo", query="둘째쪽지")["count"] == 1


# ── 5. 재색인은 원자적이다 — 도중에 읽는 쪽은 옛 색인 전체를 본다 ───────────────
def test_rebuild_is_atomic_reader_sees_old_rows(paths, monkeypatch):
    for i in range(3):
        _memo.add(summary=f"쪽지{i}번", reason="r", body="b", paths=paths)
    _db.rebuild_bowl_index("memo", paths)

    gate, go = threading.Event(), threading.Event()
    real_now = cfg.now

    def blocking_now():
        # rebuild_bowl_index는 트랜잭션 안(INSERT 뒤, COMMIT 전)에서 cfg.now()를 부른다.
        gate.set()
        go.wait(5)
        return real_now()

    monkeypatch.setattr(cfg, "now", blocking_now)
    t = threading.Thread(target=_db.rebuild_bowl_index, args=("memo", paths))
    t.start()
    try:
        assert gate.wait(5)
        with closing(sqlite3.connect(paths.db_path, timeout=0.5)) as reader:
            seen = reader.execute("SELECT COUNT(*) FROM bowl_memo").fetchone()[0]
            fts = reader.execute(
                "SELECT COUNT(*) FROM bowl_memo_fts WHERE bowl_memo_fts MATCH ?",
                ('"쪽지1"',),
            ).fetchone()[0]
    finally:
        go.set()
        t.join()
    assert seen == 3
    assert fts == 1
    # 끝난 뒤에도 색인과 FTS(트리거)가 멀쩡하다.
    monkeypatch.setattr(cfg, "now", real_now)
    assert _search(paths, "memo", query="쪽지2번")["count"] == 1


def test_learnings_rebuild_is_atomic(paths, monkeypatch):
    """교훈 재생성(rebuild_from_yaml)도 한 트랜잭션이다 — 도중에 실패하면 옛 표가 남는다."""
    _db.record("t", "success", "옛교훈이유", paths=paths)
    _db.rebuild_from_yaml(paths=paths)

    def boom(*_a, **_k):
        raise RuntimeError("도중 실패")

    real_dumps = _db.json.dumps
    monkeypatch.setattr(_db.json, "dumps", boom)
    with pytest.raises(RuntimeError):
        _db.rebuild_from_yaml(paths=paths)
    monkeypatch.setattr(_db.json, "dumps", real_dumps)
    with closing(sqlite3.connect(paths.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0] == 1
        assert _db.search(conn, "옛교훈이유")["results"]


# ── 4. since/until은 어느 구분자로 줘도 그릇마다 같은 뜻이다 ─────────────────────
def test_since_until_separator_memo(paths):
    _memo.add(summary="오늘쪽지", reason="r", body="b", paths=paths)
    ts = _memo.load_all(paths)[0]["timestamp"]
    day = ts[:10]
    for sep in (" ", "T"):
        late = 1 if ts[11:19] >= "23:59:59" else 0
        assert _search(paths, "memo", since=f"{day}{sep}23:59:59")["count"] == late
        assert _search(paths, "memo", until=f"{day}{sep}23:59:59")["count"] == 1
        assert _search(paths, "memo", since=f"{day}{sep}00:00:00")["count"] == 1


def test_until_with_time_includes_that_second(paths):
    """저장값에 소수초·시간대 꼬리가 붙어도 준 초는 포함한다."""
    _memo.add(summary="쪽지", reason="r", body="b", paths=paths)
    ts = _memo.load_all(paths)[0]["timestamp"]
    assert _search(paths, "memo", until=ts[:19])["count"] == 1
    assert _search(paths, "memo", until=ts[:10] + " " + ts[11:16])["count"] == 1


def test_since_separator_tasks(paths):
    import os
    from pathlib import Path

    d = Path(os.environ["HOME"]) / ".namu" / "tasks" / "proj" / "t1"
    d.mkdir(parents=True)
    (d / "log.md").write_text("[기록] 2026-09-01 12:00:00 hp · 정오기록\n", encoding="utf-8")
    for since in ("2026-09-01T00:00:00", "2026-09-01 00:00:00",
                  "2026-09-01T00:00:00+09:00", "2026-09-01T12:00"):
        assert _search(paths, "tasks", query="정오기록", since=since)["count"] == 1, since
    assert _search(paths, "tasks", query="정오기록", since="2026-09-01T12:00:01")["count"] == 0
    assert _search(paths, "tasks", query="정오기록", until="2026-09-01T12:00")["count"] == 1
    assert _search(paths, "tasks", query="정오기록", until="2026-09-01T11:59")["count"] == 0


def test_learnings_since_space_separator(paths):
    _db.record("t", "success", "교훈이유", paths=paths)
    with closing(sqlite3.connect(paths.db_path)) as conn:
        ts = conn.execute("SELECT timestamp FROM learnings").fetchone()[0]
        day = ts[:10]
        assert len(_db.search(conn, since=f"{day} 00:00:00")["results"]) == 1
        assert len(_db.search(conn, until=f"{day} 23:59:59")["results"]) == 1


# ── 8. 교훈 LIKE 폴백도 %·_ 를 글자 그대로 찾는다 ────────────────────────────────
def test_learnings_like_fallback_escapes_wildcards(paths):
    _db.record("t", "success", "평범한 이유", paths=paths)
    _db.record("할인_50%", "success", "진짜 퍼센트", paths=paths)
    with closing(sqlite3.connect(paths.db_path)) as conn:
        assert _db.search_bowl(conn, bowl="learnings", query="평_", paths=paths)["count"] == 0
        got = _db.search_bowl(conn, bowl="learnings", query="%", paths=paths)
        assert got["count"] == 1 and got["results"][0]["task"] == "할인_50%"
        # task 축의 LIKE도 같다.
        assert len(_db.search(conn, task="_")["results"]) == 1
        assert len(_db.search(conn, task="t%")["results"]) == 0


# ── 7. 따옴표 없는 yaml 시각도 ISO 문자열로 담긴다 ──────────────────────────────
def test_unquoted_yaml_timestamp_kept_iso(paths):
    paths.learnings_yaml.write_text(
        "---\nid: A1\ntask: t\noutcome: success\nreason: r\ntask_type: other\n"
        "timestamp: 2026-09-01T12:00:00+09:00\nmachine: m\nverified_by: human\n"
        "tags: []\nkind: lesson\n",
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        _db.rebuild_from_yaml(paths=paths)
    with closing(sqlite3.connect(paths.db_path)) as conn:
        stored = conn.execute("SELECT timestamp FROM learnings").fetchone()[0]
        assert stored == "2026-09-01T12:00:00+09:00"
        assert len(_db.search(conn, since="2026-09-01T11:00:00")["results"]) == 1


def test_profile_mixed_timestamp_types_do_not_crash(paths):
    paths.profile_yaml.write_text(
        "---\nid: P1\nsummary: a\nreason: r\nbody: b\ntimestamp: '2026-09-01T10:00:00+09:00'\n"
        "---\nid: P2\nsummary: c\nreason: r\nbody: b\ntimestamp: 2026-09-02T10:00:00+09:00\n",
        encoding="utf-8")
    got = _search(paths, "profile")
    assert [d["id"] for d in got["results"]] == ["P2", "P1"]
    assert got["results"][0]["timestamp"] == "2026-09-02T10:00:00+09:00"
    assert _search(paths, "profile", since="2026-09-02")["count"] == 1
