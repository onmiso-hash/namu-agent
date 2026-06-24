import json
import sqlite3
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
    outcome     TEXT NOT NULL CHECK(outcome IN ('success','failure','partial')),
    reason      TEXT NOT NULL,
    machine     TEXT,
    verified_by TEXT CHECK(verified_by IN ('human','ai','unverified')),
    tags        TEXT
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
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        conn.executescript(_SCHEMA)


def record(
    task: str,
    outcome: str,
    reason: str,
    task_type: str = "other",
    verified_by: str = "human",
    tags: list | None = None,
) -> str:
    if not reason:
        raise ValueError("reason은 필수입니다")
    if outcome not in _VALID_OUTCOMES:
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
    }

    # YAML 먼저 (진실의 원천)
    yaml_path = cfg.LEARNINGS_YAML_PATH
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    # SQLite 나중 (검색 캐시)
    init_db()
    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        conn.execute(
            """INSERT INTO learnings
               (id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                entry_id,
                timestamp,
                task,
                task_type,
                outcome,
                reason,
                machine,
                verified_by,
                json.dumps(tags, ensure_ascii=False),
            ),
        )

    return entry_id


def rebuild_from_yaml() -> int:
    cfg.NAMU_DB_PATH.unlink(missing_ok=True)
    init_db()

    yaml_path = cfg.LEARNINGS_YAML_PATH
    if not yaml_path.exists():
        return 0

    docs = list(yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")))
    docs = [d for d in docs if d]  # None 필터 (빈 문서 구분자 처리)

    with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
        for d in docs:
            tags = d.get("tags") or []
            conn.execute(
                """INSERT OR IGNORE INTO learnings
                   (id, timestamp, task, task_type, outcome, reason, machine, verified_by, tags)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    d.get("id"),
                    d.get("timestamp"),
                    d.get("task"),
                    d.get("task_type"),
                    d.get("outcome"),
                    d.get("reason"),
                    d.get("machine"),
                    d.get("verified_by"),
                    json.dumps(tags, ensure_ascii=False),
                ),
            )

    return len(docs)
