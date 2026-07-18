# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp[cli]>=1.28,<2", "python-ulid>=3.0.0", "PyYAML>=6.0", "python-dotenv>=1.0.0"]
# ///
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import config as cfg
import memory_sync
import profile
from mcp.server.fastmcp import Context, FastMCP
from db import init_db, rebuild_from_yaml, record, cache_is_stale
from db import recall as _recall
from db import search as _search

mcp = FastMCP("namu-memory")


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(cfg.NAMU_DB_PATH)


def _ensure_db() -> None:
    if not cfg.NAMU_DB_PATH.exists() or cache_is_stale(cfg.LEARNINGS_YAML_PATH, cfg.NAMU_DB_PATH):
        rebuild_from_yaml()


def _ensure_tasks_gitattributes() -> None:
    """기존 개통분(hp·samsung)의 `~/.namu/.gitattributes`에 tasks union 라인을
    멱등 ensure한다(namu-34 ③-c). 신규 개통은 namu_sync_setup이 이미 챙기므로,
    이건 "sync_setup을 다시 부르지 않는 기존 사용자"를 위한 보정이다.

    대상은 항상 `Path.home()/".namu"`다(tasks 개인 풀 규칙과 동일 근거, namu-34 ①
    — namu-35 이후로는 cfg.NAMU_DATA_ROOT와도 같은 경로). `.git`이 없으면(미개통)
    완전 스킵하고, 그 외 모든 실패도 서버 부팅을 절대 막으면 안 되므로 전예외
    무해 처리한다.
    """
    try:
        home = Path.home() / ".namu"
        if (home / ".git").exists():
            memory_sync.ensure_gitattributes_union(home)
    except Exception:
        pass


_ensure_db()
_ensure_tasks_gitattributes()


_VIA_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

_VIA_ERROR_MSG = (
    "출처(client) 식별값이 없거나 형식이 올바르지 않습니다 — NAMU 체험 MCP 주소 끝에 "
    "?client=<당신의 AI 이름>을 붙여 등록하거나 URL을 고쳐 주세요. 예: "
    "https://.../mcp?client=claude  |  Missing/invalid 'client' provenance tag: "
    "append ?client=<your-ai-name> to the MCP URL, e.g. https://.../mcp?client=claude"
)


def _resolve_via(ctx: Context | None) -> str | None:
    """URL 쿼리(`?client=`)에서 출처(via) 태그를 읽어 검증한다(namu-50).

    stateless HTTP(웹) 경로에서만 request가 도달하므로, req가 None이면(stdio/직접
    호출/테스트) 검증을 완전히 면제하고 None을 반환한다 — 기존 로컬 동작을 절대
    바꾸지 않기 위함이다.
    """
    if ctx is None:
        return None
    req = getattr(getattr(ctx, "request_context", None), "request", None)
    if req is None:
        return None
    client = (req.query_params.get("client") or "").strip()
    if not _VIA_RE.match(client):
        raise ValueError(_VIA_ERROR_MSG)
    return client


def _normalize_tags(tags: list[str] | str | None) -> list[str] | None:
    if tags is None or isinstance(tags, list):
        return tags
    # str 경로
    stripped = tags.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return [tags]


@mcp.tool()
def namu_recall(
    query: str | None = None,
    task_type: str | None = None,
    limit: int = 5,
    ctx: Context | None = None,
):
    """Load relevant past memory BEFORE starting a task (context loading).
    Use at task/session start to recall how similar work went before and what
    facts/preferences are on file. Returns something useful even on weak
    matches: if the query matches nothing, learnings falls back to the most
    recent entries. For warming up context, not precise analysis. For
    pattern/trend analysis use namu_search instead.

    Args:
      query: topic keywords (optional; omit to get the most recent learnings)
      task_type: filter by code/doc/analysis/other (optional; learnings only)
      limit: max learnings entries (default 5, small for token efficiency)
    Returns: two-bowl dict —
      {"profile": [...active facts/preferences, all of them, no limit...],
       "learnings": [...lesson/note dicts: timestamp, task, outcome, reason,
       kind, tags, ...]}
    """
    _resolve_via(ctx)
    _ensure_db()
    with closing(get_conn()) as conn:
        return {
            "profile": profile.active(),
            "learnings": _recall(conn, query, task_type, limit),
        }


@mcp.tool()
def namu_search(
    query: str,
    outcome_filter: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
):
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
    _resolve_via(ctx)
    _ensure_db()
    with closing(get_conn()) as conn:
        return _search(conn, query, outcome_filter, limit)


@mcp.tool()
def namu_record(
    task: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    task_type: str = "other",
    verified_by: str = "ai",
    tags: list[str] | None = None,
    kind: str = "lesson",
    subject: str | None = None,
    statement: str | None = None,
    source: str | None = None,
    supersedes: str | None = None,
    ctx: Context | None = None,
):
    """Record memory into one of two bowls (append-only self-learning).
    Which bowl depends on `kind`:
      - kind='lesson' (default): a task outcome AND the reasoning behind it,
        into learnings.yaml. Call after finishing a task when there's a
        generalizable pattern worth keeping. 'reason' is MANDATORY (empty
        rejected with ValueError). 'outcome' is required too
        ('success'/'failure'/'partial'). Storage trigger: AI's own judgment
        that the outcome/reason is worth remembering — call directly, no need
        to ask first.
      - kind='note': a conversation snippet worth keeping, also into
        learnings.yaml (kind differentiates it from 'lesson'; no success/
        failure concept so 'outcome' may be omitted). 'reason' still
        MANDATORY. Storage trigger: only when the user explicitly asks to
        remember this conversation (e.g. "remember this").
      - kind='fact': a fact or preference (user/environment/preference-ish
        subject), into the separate profile.yaml bowl (no SQLite cache,
        loaded whole every time). Use subject/statement/source/supersedes
        instead of task/outcome/reason. 'source' is MANDATORY — WHY/how you
        know this is true (empty rejected with ValueError). To correct a
        prior fact, don't edit it — record a new one with `supersedes` set
        to the old entry's id (profile.yaml is append-only; the old entry is
        superseded, not deleted). Storage trigger (soft policy only, NOT
        enforced by code): AI should propose ("should I remember this?") and
        get the user's agreement before calling with kind='fact'.

    Writes the yaml first (source of truth), then the SQLite cache for
    lesson/note (fact has no cache). id/timestamp/machine are filled in
    automatically by the server.

    Args:
      task: what was done (lesson/note only)
      outcome: 'success' | 'failure' | 'partial' (lesson: required; note: optional)
      reason: WHY it succeeded/failed, or why this note matters (lesson/note,
        required, non-empty)
      task_type: code/doc/analysis/other (default 'other'; lesson/note only)
      verified_by: 'human'/'ai'/'unverified' (default 'ai' = AI-judged)
      tags: list of string tags (optional)
      kind: 'lesson' (default) | 'note' | 'fact' — selects the bowl and
        validation rules, see above
      subject: what/who this fact is about, free-form (fact only, e.g.
        user/environment/preference)
      statement: the fact/preference itself (fact only)
      source: WHY/how you know this is true (fact only, required, non-empty)
      supersedes: id of the prior fact entry this one corrects (fact only,
        optional)
    Returns: the new entry's ULID (str)
    """
    # namu-38: samsung 라이브 실측에서 record 직후 git 단계까지 12분 공백이
    # 관측됐다 — ensure_db(캐시 재생성)/record(yaml+sqlite)/sync(git push) 세 구간
    # 중 어디서 지연이 생기는지 판정하려면 구간별 시간이 반드시 필요하다. db.py는
    # 코어라 침습을 최소화하고, record()는 전체 구간 하나로만 잰다.
    via = _resolve_via(ctx)
    t0 = time.perf_counter()
    _ensure_db()
    t1 = time.perf_counter()
    if kind in ("lesson", "note"):
        entry_id = record(
            task, outcome, reason, task_type, verified_by, _normalize_tags(tags), kind=kind,
            via=via,
        )
    elif kind == "fact":
        vb = verified_by if verified_by in ("human", "ai", "unverified") else "human"
        entry_id = profile.record_fact(
            subject, statement, source, supersedes=supersedes,
            verified_by=vb, tags=_normalize_tags(tags), via=via,
        )
    else:
        raise ValueError("kind는 'lesson'/'note'/'fact' 중 하나여야 합니다")
    t2 = time.perf_counter()
    # 설치형(~/.namu) 자동 동기화 활성 시에만 실제 push가 일어난다(sync_enabled 하드가드).
    # 반환값이 False여도(비활성/실패) record 자체의 성공 결과에는 영향을 주지 않는다.
    label = (task or statement or subject or "")[:50]
    memory_sync.sync_push(f"learn: {label} ({cfg.NAMU_MACHINE})")
    t3 = time.perf_counter()
    memory_sync._append_sync_log(
        f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
    )
    return entry_id


@mcp.tool()
def namu_sync_setup(remote_url: str) -> str:
    """Enable git auto-sync for the standalone (~/.namu) learnings install.

    Wires up local git (init/.gitignore/.gitattributes/remote/marker) so that
    subsequent namu_record calls auto-push and session-start hooks auto-pull.
    The remote git repository itself must already exist and be prepared by the
    user beforehand (e.g. an empty private GitHub repo) — this tool only sets
    up the local side, it does not create the remote.

    Args:
      remote_url: git remote URL to push learnings to
    Returns: human-readable result string (per-step success/failure notes)
    """
    return memory_sync.sync_setup(remote_url)


if __name__ == "__main__":
    mcp.run(transport="stdio")
