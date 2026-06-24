import sqlite3
from contextlib import closing

import config as cfg
from mcp.server.fastmcp import FastMCP
from memory.db import init_db, rebuild_from_yaml, record
from memory.db import recall as _recall
from memory.db import search as _search

mcp = FastMCP("namu-memory")


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(cfg.NAMU_DB_PATH)


def _ensure_db() -> None:
    if not cfg.NAMU_DB_PATH.exists():
        init_db()
        rebuild_from_yaml()


_ensure_db()


@mcp.tool()
def namu_recall(query: str | None = None, task_type: str | None = None, limit: int = 5):
    """Load relevant past learnings BEFORE starting a task (context loading).
    Use at task/session start to recall how similar work went before. Returns
    something useful even on weak matches: if the query matches nothing, falls
    back to the most recent entries. For warming up context, not precise analysis.
    For pattern/trend analysis use namu_search instead.

    Args:
      query: topic keywords (optional; omit to get the most recent entries)
      task_type: filter by code/doc/analysis/other (optional)
      limit: max entries (default 5, small for token efficiency)
    Returns: list of learning dicts (timestamp, task, outcome, reason, tags, ...)
    """
    with closing(get_conn()) as conn:
        return _recall(conn, query, task_type, limit)


@mcp.tool()
def namu_search(query: str, outcome_filter: str | None = None, limit: int = 10):
    """Search accumulated learnings for PATTERNS (analytical lookup during judgment).
    Use when you need precise matches to analyze success/failure trends, e.g.
    'have approaches like this failed before?'. Exact matches only — returns empty
    if nothing matches (NO recency fallback). Always attaches a trend summary
    counting outcomes across ALL matches. For general context loading use namu_recall.

    Args:
      query: search terms
      outcome_filter: 'success'/'failure'/'partial' to narrow returned rows (optional)
      limit: max returned rows (default 10)
    Returns: {"results": [...dicts...], "summary": {"success": N, "failure": M, "partial": K}}
    """
    with closing(get_conn()) as conn:
        return _search(conn, query, outcome_filter, limit)


@mcp.tool()
def namu_record(
    task: str,
    outcome: str,
    reason: str,
    task_type: str = "other",
    verified_by: str = "ai",
    tags: list[str] | None = None,
):
    """Record a task outcome AND the reasoning behind it (append-only self-learning).
    Call after finishing a task. 'reason' is MANDATORY — later pattern analysis
    depends on it; an empty reason is rejected (ValueError). Writes learnings.yaml
    first (source of truth), then the SQLite cache. id/timestamp/machine are filled
    in automatically by the server.

    Args:
      task: what was done
      outcome: 'success' | 'failure' | 'partial'
      reason: WHY it succeeded/failed (required, non-empty)
      task_type: code/doc/analysis/other (default 'other')
      verified_by: 'human'/'ai'/'unverified' (default 'ai' = AI-judged)
      tags: list of string tags (optional)
    Returns: the new entry's ULID (str)
    """
    return record(task, outcome, reason, task_type, verified_by, tags)


if __name__ == "__main__":
    mcp.run(transport="stdio")
