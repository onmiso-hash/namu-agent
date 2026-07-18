import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import yaml
from ulid import ULID

import config as cfg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learnings (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    task        TEXT NOT NULL,
    task_type   TEXT,
    outcome     TEXT CHECK(outcome IS NULL OR outcome IN ('success','failure','partial')),
    reason      TEXT NOT NULL,
    machine     TEXT,
    verified_by TEXT CHECK(verified_by IN ('human','ai','unverified')),
    tags        TEXT,
    kind        TEXT,
    via         TEXT
);

CREATE INDEX IF NOT EXISTS idx_learnings_type    ON learnings(task_type);
CREATE INDEX IF NOT EXISTS idx_learnings_outcome ON learnings(outcome);

CREATE VIRTUAL TABLE IF NOT EXISTS learnings_fts USING fts5(
    task, reason, tags,
    content='learnings',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS learnings_ai AFTER INSERT ON learnings BEGIN
  INSERT INTO learnings_fts(rowid, task, reason, tags)
  VALUES (new.rowid, new.task, new.reason, new.tags);
END;
"""

_VALID_OUTCOMES = {"success", "failure", "partial"}
_VALID_VERIFIED_BY = {"human", "ai", "unverified"}


def init_db() -> None:
    cfg.NAMU_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(cfg.NAMU_DB_PATH)) as conn:
        with conn:
            conn.executescript(_SCHEMA)


_VALID_KINDS = {"lesson", "note"}


def record(
    task: str,
    outcome: str | None,
    reason: str,
    task_type: str = "other",
    verified_by: str = "human",
    tags: list | None = None,
    kind: str = "lesson",
    via: str | None = None,
) -> str:
    if not reason:
        raise ValueError("reason은 필수입니다")
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind는 {_VALID_KINDS} 중 하나여야 합니다")
    if kind == "lesson":
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(f"outcome은 {_VALID_OUTCOMES} 중 하나여야 합니다")
    else:  # kind == "note": outcome 생략 가능, 주어지면 검증
        if outcome is not None and outcome not in _VALID_OUTCOMES:
            raise ValueError(f"outcome은 {_VALID_OUTCOMES} 중 하나여야 합니다")
    if verified_by not in _VALID_VERIFIED_BY:
        raise ValueError(f"verified_by는 {_VALID_VERIFIED_BY} 중 하나여야 합니다")

    if tags is None:
        tags = []

    entry_id = str(ULID())
    timestamp = datetime.now(timezone.utc).isoformat()
    machine = cfg.NAMU_MACHINE

    doc = {
        "id": entry_id,
        "timestamp": timestamp,
        "task": task,
        "task_type": task_type,
        "outcome": outcome,
        "reason": reason,
        "machine": machine,
        "verified_by": verified_by,
        "tags": tags,
        "kind": kind,
        "via": via,
    }

    # YAML 먼저 (진실의 원천)
    yaml_path = cfg.LEARNINGS_YAML_PATH
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    # SQLite 나중 (검색 캐시)
    init_db()
    with closing(sqlite3.connect(cfg.NAMU_DB_PATH)) as conn:
        with conn:
            conn.execute(
                """INSERT INTO learnings
                   (id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags, kind, via)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, timestamp, task, task_type, outcome, reason,
                 machine, verified_by, json.dumps(tags, ensure_ascii=False), kind, via),
            )

    return entry_id


def rebuild_from_yaml() -> int:
    yaml_path = cfg.LEARNINGS_YAML_PATH
    cfg.NAMU_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    docs = []
    if yaml_path.exists():
        docs = [d for d in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")) if d]

    with closing(sqlite3.connect(cfg.NAMU_DB_PATH)) as conn:
        conn.executescript(
            "DROP TRIGGER IF EXISTS learnings_ai;"
            "DROP TABLE IF EXISTS learnings_fts;"
            "DROP TABLE IF EXISTS learnings;"
            + _SCHEMA
        )
        with conn:
            for d in docs:
                tags = d.get("tags") or []
                kind = d.get("kind") or "lesson"
                conn.execute(
                    """INSERT OR IGNORE INTO learnings
                       (id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags, kind, via)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (d.get("id"), d.get("timestamp"), d.get("task"), d.get("task_type"),
                     d.get("outcome"), d.get("reason"), d.get("machine"), d.get("verified_by"),
                     json.dumps(tags, ensure_ascii=False), kind, d.get("via")),
                )
    return len(docs)


def count_yaml_docs(yaml_path) -> int:
    """yaml 파일에서 최상위 `id:` 줄 수를 세어 entry 수를 반환. 파싱 없이 줄만 스캔."""
    if not yaml_path.exists():
        return 0
    count = 0
    with yaml_path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("id:"):
                count += 1
    return count


def cache_is_stale(yaml_path, db_path) -> bool:
    """캐시가 낡았으면 True (→ rebuild 필요). 두 가지를 검사한다:

    ① 스키마 — db `learnings` 테이블이 최신 기대 컬럼셋(_COLS)을 다 갖췄는지.
       스키마 변경 릴리스(예: namu-52의 `kind` 컬럼 추가)에서 개수만 같은 옛 스키마
       db를 방치하면, 새 코드가 없는 컬럼을 쿼리하다 `no such column`으로 깨진다
       (0.1.26 웹 배포에서 실측). 개수 검사만으로는 못 잡으므로 스키마를 먼저 본다.
    ② 개수 — yaml entry 수와 db row 수가 다른지(git pull 등으로 원본이 늘어난 경우).
    """
    yaml_count = count_yaml_docs(yaml_path)
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            db_cols = {row[1] for row in conn.execute("PRAGMA table_info(learnings)")}
            if not set(_COLS) <= db_cols:
                return True  # 스키마 낡음(기대 컬럼 누락) → rebuild
            db_count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
    except sqlite3.OperationalError:
        return True
    return yaml_count != db_count


_COLS = (
    "id", "timestamp", "task", "task_type", "outcome",
    "reason", "machine", "verified_by", "tags", "kind", "via",
)


def _row_to_dict(row: tuple) -> dict:
    d = dict(zip(_COLS, row))
    try:
        d["tags"] = json.loads(d["tags"]) if d["tags"] else []
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def _fts_query(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    order: str,
    outcome_filter: str | None = None,
    task_type: str | None = None,
) -> list[dict]:
    q = query.strip()

    if len(q) >= 3:
        fts_term = '"' + q.replace('"', '""') + '"'
        order_clause = "ORDER BY bm25(learnings_fts)" if order == "bm25" else "ORDER BY l.id DESC"
        conds: list[str] = ["learnings_fts MATCH ?"]
        params: list = [fts_term]
        if outcome_filter:
            conds.append("l.outcome = ?")
            params.append(outcome_filter)
        if task_type:
            conds.append("l.task_type = ?")
            params.append(task_type)
        sql = (
            "SELECT l.id, l.timestamp, l.task, l.task_type, l.outcome,"
            " l.reason, l.machine, l.verified_by, l.tags, l.kind, l.via"
            " FROM learnings_fts"
            " JOIN learnings l ON l.rowid = learnings_fts.rowid"
            f" WHERE {' AND '.join(conds)}"
            f" {order_clause}"
            " LIMIT ?"
        )
        rows = conn.execute(sql, params + [limit]).fetchall()
    else:
        like_term = f"%{q}%"
        conds = ["(task LIKE ? OR reason LIKE ? OR tags LIKE ?)"]
        params = [like_term, like_term, like_term]
        if outcome_filter:
            conds.append("outcome = ?")
            params.append(outcome_filter)
        if task_type:
            conds.append("task_type = ?")
            params.append(task_type)
        sql = (
            "SELECT id, timestamp, task, task_type, outcome,"
            " reason, machine, verified_by, tags, kind, via"
            " FROM learnings"
            f" WHERE {' AND '.join(conds)}"
            " ORDER BY id DESC"
            " LIMIT ?"
        )
        rows = conn.execute(sql, params + [limit]).fetchall()

    return [_row_to_dict(row) for row in rows]


def recall(
    conn: sqlite3.Connection,
    query: str | None = None,
    task_type: str | None = None,
    limit: int = 5,
) -> list[dict]:
    def _latest(lim: int) -> list[dict]:
        conds: list[str] = []
        params: list = []
        if task_type:
            conds.append("task_type = ?")
            params.append(task_type)
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        sql = (
            "SELECT id, timestamp, task, task_type, outcome,"
            " reason, machine, verified_by, tags, kind, via"
            f" FROM learnings {where} ORDER BY id DESC LIMIT ?"
        )
        return [_row_to_dict(r) for r in conn.execute(sql, params + [lim]).fetchall()]

    q = (query or "").strip()
    if not q:
        return _latest(limit)

    matches = _fts_query(conn, q, limit, order="recent", task_type=task_type)
    return matches if matches else _latest(limit)


def search(
    conn: sqlite3.Connection,
    query: str,
    outcome_filter: str | None = None,
    limit: int = 10,
) -> dict:
    results = _fts_query(conn, query, limit, order="bm25", outcome_filter=outcome_filter)

    summary: dict[str, int] = {"success": 0, "failure": 0, "partial": 0}
    q = query.strip()
    if len(q) >= 3:
        fts_term = '"' + q.replace('"', '""') + '"'
        rows = conn.execute(
            "SELECT l.outcome, COUNT(*)"
            " FROM learnings_fts"
            " JOIN learnings l ON l.rowid = learnings_fts.rowid"
            " WHERE learnings_fts MATCH ?"
            " GROUP BY l.outcome",
            [fts_term],
        ).fetchall()
    else:
        like_term = f"%{q}%"
        rows = conn.execute(
            "SELECT outcome, COUNT(*)"
            " FROM learnings"
            " WHERE (task LIKE ? OR reason LIKE ? OR tags LIKE ?)"
            " GROUP BY outcome",
            [like_term, like_term, like_term],
        ).fetchall()

    for outcome, count in rows:
        if outcome in summary:
            summary[outcome] = count

    return {"results": results, "summary": summary}
