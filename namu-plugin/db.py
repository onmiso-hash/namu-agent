import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone

import yaml
from ulid import ULID

import config as cfg
import memo as _memo
import profile as _profile
import task_resolve

# namu-65 3단계 — 3층(summary/reason/body) 중 summary·body 컬럼 추가.
# 저장 이름 규칙: **3층은 도입하되 축 이름(task/outcome/task_type/verified_by)은
# 손대지 않는다.** 입력 이름은 boundary(record_input)에서 topic/status/category/
# confidence로 통일되지만, 저장 키까지 바꾸면 161건 yaml + 이 스키마 + 읽는 곳
# (세션 브리핑·statusline·웹 라우팅 등 이 repo 밖 소비자 포함)이 한꺼번에 흔들린다.
# reason이라는 이름이 살아남은 덕에 교훈 159건 이관이 안전했던 것과 같은 판단이다.
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
    via         TEXT,
    summary     TEXT,
    body        TEXT
);

CREATE INDEX IF NOT EXISTS idx_learnings_type    ON learnings(task_type);
CREATE INDEX IF NOT EXISTS idx_learnings_outcome ON learnings(outcome);

CREATE VIRTUAL TABLE IF NOT EXISTS learnings_fts USING fts5(
    task, reason, tags, summary, body,
    content='learnings',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS learnings_ai AFTER INSERT ON learnings BEGIN
  INSERT INTO learnings_fts(rowid, task, reason, tags, summary, body)
  VALUES (new.rowid, new.task, new.reason, new.tags, new.summary, new.body);
END;
"""

_VALID_OUTCOMES = {"success", "failure", "partial"}
_VALID_VERIFIED_BY = {"human", "ai", "unverified"}


def init_db(paths: "cfg.DataPaths | None" = None) -> None:
    p = paths or cfg.data_paths_for()
    p.db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(p.db_path)) as conn:
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
    paths: "cfg.DataPaths | None" = None,
    *,
    summary: str | None = None,
    body: str | None = None,
) -> str:
    """교훈 한 건을 남긴다(append-only).

    summary/body는 namu-65 3단계에서 더한 3층의 1·3층이다. **여기서는 필수로 걸지
    않는다** — 필수 여부는 그릇별로 다르고 그 판단은 입력 경계(record_input)가 표에서
    파생해 이미 내린 뒤다. 저장 계층이 같은 규칙을 한 번 더 구현하면 두 곳이 어긋날 때
    어느 쪽이 옳은지 알 수 없어진다. 옛 호출(3층 없음)도 그대로 통과한다.
    """
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

    p = paths or cfg.data_paths_for()

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
        "summary": summary,
        "body": body,
    }

    # YAML 먼저 (진실의 원천)
    yaml_path = p.learnings_yaml
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    # SQLite 나중 (검색 캐시)
    init_db(paths=p)
    with closing(sqlite3.connect(p.db_path)) as conn:
        with conn:
            conn.execute(
                """INSERT INTO learnings
                   (id, timestamp, task, task_type, outcome, reason, machine, verified_by,
                    tags, kind, via, summary, body)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, timestamp, task, task_type, outcome, reason,
                 machine, verified_by, json.dumps(tags, ensure_ascii=False), kind, via,
                 summary, body),
            )

    return entry_id


def rebuild_from_yaml(paths: "cfg.DataPaths | None" = None) -> int:
    p = paths or cfg.data_paths_for()
    yaml_path = p.learnings_yaml
    p.db_path.parent.mkdir(parents=True, exist_ok=True)

    docs = []
    if yaml_path.exists():
        docs = [d for d in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")) if d]

    with closing(sqlite3.connect(p.db_path)) as conn:
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
                       (id, timestamp, task, task_type, outcome, reason, machine, verified_by,
                        tags, kind, via, summary, body)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (d.get("id"), d.get("timestamp"), d.get("task"), d.get("task_type"),
                     d.get("outcome"), d.get("reason"), d.get("machine"), d.get("verified_by"),
                     json.dumps(tags, ensure_ascii=False), kind, d.get("via"),
                     d.get("summary"), d.get("body")),
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


# 조회 컬럼 목록. **끝에 추가한다** — `_row_to_dict`가 SELECT 결과를 이 순서로
# 짝지으므로 중간에 끼우면 값이 한 칸씩 밀린다. 여기에 이름을 더하면
# `cache_is_stale`이 옛 스키마 db를 자동으로 낡음 판정해 재생성한다(namu-65 3단계에서
# summary/body를 더한 것이 그 경로를 그대로 탄다 — 새 감지 장치를 만들 필요 없음).
_COLS = (
    "id", "timestamp", "task", "task_type", "outcome",
    "reason", "machine", "verified_by", "tags", "kind", "via",
    "summary", "body",
)

# SELECT 절은 _COLS에서 만든다 — 컬럼을 더할 때 네 군데 하드코딩된 목록을 손으로
# 맞추다 어긋나면, 값이 조용히 다른 칸으로 들어간다(자리만 밀리므로 예외도 안 난다).
_SELECT_COLS = ", ".join(_COLS)
_SELECT_COLS_L = ", ".join(f"l.{col}" for col in _COLS)


def _row_to_dict(row: tuple) -> dict:
    d = dict(zip(_COLS, row))
    try:
        d["tags"] = json.loads(d["tags"]) if d["tags"] else []
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def _until_bound(until: str) -> tuple[str, str]:
    """until 인자를 (비교연산자, 경계값)으로 정규화한다. SQL과 파이썬 필터 양쪽에서 재사용.

    날짜만(길이<=10) 주면 그날을 포함해야 하므로 다음날 날짜 미만(`<`, 다음날)으로
    확장하고, 시각까지 주면 그 값 이하(`<=`, 그대로)로 비교한다.
    """
    value = until.strip()
    if len(value) <= 10:
        d = date.fromisoformat(value)
        return ("<", (d + timedelta(days=1)).isoformat())
    return ("<=", value)


def _until_clause(column: str, until: str) -> tuple[str, str]:
    """`_until_bound`을 SQL 조건절(`"<column> < ?"` 등)과 파라미터값으로 변환."""
    op, bound = _until_bound(until)
    return f"{column} {op} ?", bound


def _axis_conds(
    prefix: str,
    *,
    outcome_filter: str | None = None,
    task_type: str | None = None,
    machine: str | None = None,
    via: str | None = None,
    task: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> tuple[list[str], list]:
    """machine/via/task/task_type/outcome/since/until 축 필터를 SQL 조건 리스트로 변환.

    prefix는 컬럼 앞에 붙는 테이블 별칭(FTS 조인 시 `"l."`, 아니면 `""`).
    machine/via/task_type/outcome_filter는 정확 일치, task는 LIKE 부분일치
    (learnings의 task 컬럼은 "namu-57 1단계 — …" 같은 자유 문장이라 정확 일치로
    걸면 못 찾는다). since/until은 timestamp(ISO8601 UTC 문자열) 사전순 비교.

    ⚠️ timestamp는 UTC 저장값이다(db.record). tasks 그릇(task_resolve.journal)의
    log.md 시각은 PC 현지시각이라 그릇마다 기준이 다르다 — KST 등 UTC+9면 날짜
    경계가 최대 9시간 어긋날 수 있다. 저장 형식을 통일하지 않은 채 필터만 얹은
    상태이므로 since/until 값을 그릇 간에 그대로 재사용하면 안 된다.
    """
    conds: list[str] = []
    params: list = []
    if outcome_filter:
        conds.append(f"{prefix}outcome = ?")
        params.append(outcome_filter)
    if task_type:
        conds.append(f"{prefix}task_type = ?")
        params.append(task_type)
    if machine:
        conds.append(f"{prefix}machine = ?")
        params.append(machine)
    if via:
        conds.append(f"{prefix}via = ?")
        params.append(via)
    if task:
        conds.append(f"{prefix}task LIKE ?")
        params.append(f"%{task}%")
    if since:
        conds.append(f"{prefix}timestamp >= ?")
        params.append(since)
    if until:
        clause, val = _until_clause(f"{prefix}timestamp", until)
        conds.append(clause)
        params.append(val)
    return conds, params


def _fts_query(
    conn: sqlite3.Connection,
    query: str | None,
    limit: int,
    order: str,
    outcome_filter: str | None = None,
    task_type: str | None = None,
    machine: str | None = None,
    via: str | None = None,
    task: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    q = (query or "").strip()

    if len(q) >= 3:
        fts_term = '"' + q.replace('"', '""') + '"'
        order_clause = "ORDER BY bm25(learnings_fts)" if order == "bm25" else "ORDER BY l.id DESC"
        extra_conds, extra_params = _axis_conds(
            "l.", outcome_filter=outcome_filter, task_type=task_type,
            machine=machine, via=via, task=task, since=since, until=until,
        )
        conds = ["learnings_fts MATCH ?"] + extra_conds
        params = [fts_term] + extra_params
        sql = (
            f"SELECT {_SELECT_COLS_L}"
            " FROM learnings_fts"
            " JOIN learnings l ON l.rowid = learnings_fts.rowid"
            f" WHERE {' AND '.join(conds)}"
            f" {order_clause}"
            " LIMIT ?"
        )
        rows = conn.execute(sql, params + [limit]).fetchall()
    else:
        extra_conds, extra_params = _axis_conds(
            "", outcome_filter=outcome_filter, task_type=task_type,
            machine=machine, via=via, task=task, since=since, until=until,
        )
        if q:
            like_term = f"%{q}%"
            conds = [
                "(task LIKE ? OR reason LIKE ? OR tags LIKE ?"
                " OR summary LIKE ? OR body LIKE ?)"
            ] + extra_conds
            params = [like_term] * 5 + extra_params
        else:
            # 검색어 없음 — 필터만 적용(없으면 무조건 전체), 최신순으로 답한다.
            # ("어제 hp에서 뭐 했지"처럼 축만으로 묻는 질문에 답하기 위함.)
            conds = extra_conds
            params = extra_params
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        sql = (
            f"SELECT {_SELECT_COLS}"
            " FROM learnings"
            f" {where}"
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
            f"SELECT {_SELECT_COLS}"
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
    query: str | None = None,
    outcome_filter: str | None = None,
    limit: int = 10,
    *,
    machine: str | None = None,
    via: str | None = None,
    task: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """learnings를 검색·필터링해 결과와 outcome 추세 요약을 함께 반환한다.

    위치 인자 순서 `(conn, query, outcome_filter, limit)`는 mcp_server.py가 위치
    인자로 호출하므로 바꾸지 않는다(namu-57 2단계 1단위) — 새 축(machine/via/
    task/task_type/since/until)은 전부 키워드 전용으로 뒤에 붙인다.

    query는 선택이다. None/빈 문자열이면 텍스트 매칭 없이 필터만 적용해
    `ORDER BY id DESC`(최신순)로 반환한다 — "어제 hp에서 뭐 했지"처럼 검색어
    없이 축만으로 묻는 질문에도 답하기 위함이다.

    필터 의미:
      - machine/via/task_type/outcome_filter: 정확히 일치.
      - task: task 컬럼 부분일치(LIKE `%값%`) — learnings의 task 컬럼은
        "namu-57 1단계 — …" 같은 자유 문장이라 `task='namu-57'`로 걸려야 한다.
      - since/until: timestamp(ISO8601 UTC 문자열) 사전순 비교. since는
        `timestamp >= ?`. until은 날짜만 주면(길이<=10) 그날을 포함해야 하므로
        다음날 날짜로 `timestamp < ?`, 시각까지 주면 `timestamp <= ?`.
        ⚠️ 이 timestamp는 UTC 저장값이다(db.record). tasks 그릇(log.md)의 시각은
        PC 현지시각이라 그릇마다 기준이 다르다 — KST면 9시간차로 날짜 경계가
        어긋날 수 있다(저장 형식은 이번엔 고치지 않고 여기 명시만 한다).

    summary(outcome 집계)는 기존 의미를 유지한다 — outcome_filter와 limit은
    무시하고 query + 나머지 필터(machine/via/task/task_type/since/until)에 걸린
    전체를 집계하는 추세 요약이다.
    """
    results = _fts_query(
        conn, query, limit, order="bm25",
        outcome_filter=outcome_filter, task_type=task_type,
        machine=machine, via=via, task=task, since=since, until=until,
    )

    summary: dict[str, int] = {"success": 0, "failure": 0, "partial": 0}
    q = (query or "").strip()
    if len(q) >= 3:
        fts_term = '"' + q.replace('"', '""') + '"'
        extra_conds, extra_params = _axis_conds(
            "l.", task_type=task_type, machine=machine, via=via,
            task=task, since=since, until=until,
        )
        conds = ["learnings_fts MATCH ?"] + extra_conds
        params = [fts_term] + extra_params
        rows = conn.execute(
            "SELECT l.outcome, COUNT(*)"
            " FROM learnings_fts"
            " JOIN learnings l ON l.rowid = learnings_fts.rowid"
            f" WHERE {' AND '.join(conds)}"
            " GROUP BY l.outcome",
            params,
        ).fetchall()
    else:
        extra_conds, extra_params = _axis_conds(
            "", task_type=task_type, machine=machine, via=via,
            task=task, since=since, until=until,
        )
        if q:
            like_term = f"%{q}%"
            conds = [
                "(task LIKE ? OR reason LIKE ? OR tags LIKE ?"
                " OR summary LIKE ? OR body LIKE ?)"
            ] + extra_conds
            params = [like_term] * 5 + extra_params
        else:
            conds = extra_conds
            params = extra_params
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        rows = conn.execute(
            "SELECT outcome, COUNT(*)"
            " FROM learnings"
            f" {where}"
            " GROUP BY outcome",
            params,
        ).fetchall()

    for outcome, count in rows:
        if outcome in summary:
            summary[outcome] = count

    return {"results": results, "summary": summary}


_VALID_BOWLS = ("learnings", "tasks", "profile", "memo")


def search_bowl(
    conn: sqlite3.Connection,
    bowl: str = "learnings",
    query: str | None = None,
    project: str | None = None,
    task: str | None = None,
    machine: str | None = None,
    via: str | None = None,
    since: str | None = None,
    until: str | None = None,
    outcome_filter: str | None = None,
    task_type: str | None = None,
    limit: int = 10,
) -> dict:
    """learnings/tasks/profile 3그릇을 같은 축 집합(query/project/task/machine/via/
    since/until/…)으로 조회하는 단일 분기 진입점(namu-57 2단계 1단위).

    - `learnings` → `search()` 그대로 위임. 반환 `{"bowl","results","count","summary"}`.
    - `tasks` → `task_resolve.journal(...)`을 그대로 재사용한다(SQLite 인덱싱하지
      않는다 — log.md가 권위이고 프로젝트당 파일 수십 개라 인덱스 유지 비용이
      이득보다 크다). query가 있으면 text/tag/task_slug 부분일치(대소문자 무시)로
      거른 **뒤에** limit을 적용한다(순서 중요 — 먼저 자르면 걸러질 결과가
      사라진다). 반환 `{"bowl","results","count"}`.
    - `profile` → `profile.active()`(supersede된 항목 제외) 로드 후 파이썬 필터:
      query는 subject/statement/source/tags 부분일치, machine/via는 정확 일치,
      since/until은 timestamp 비교, timestamp 내림차순 정렬 후 limit. 반환
      `{"bowl","results","count"}`.

    `project`는 tasks 전용 축이다 — learnings/profile에 project를 주면 조용히
    무시하지 않고 ValueError로 명시 거절한다(조용히 무시하면 웹 AI가 필터가
    걸린 줄 알고 잘못된 결론을 낸다).
    """
    if bowl not in _VALID_BOWLS:
        raise ValueError(f"bowl은 {list(_VALID_BOWLS)} 중 하나여야 합니다: {bowl!r}")

    if bowl != "tasks" and project is not None:
        raise ValueError(
            f"project는 tasks 전용 축입니다 (bowl={bowl!r}에는 쓸 수 없습니다)"
        )

    if bowl == "learnings":
        result = search(
            conn, query, outcome_filter, limit,
            machine=machine, via=via, task=task, task_type=task_type,
            since=since, until=until,
        )
        return {
            "bowl": bowl,
            "results": result["results"],
            "count": len(result["results"]),
            "summary": result["summary"],
        }

    if bowl == "tasks":
        entries = task_resolve.journal(
            project=project, since=since, until=until,
            machine=machine, task=task, via=via, limit=None,
        )
        if query:
            q = query.lower()
            entries = [
                e for e in entries
                if q in (e.get("text") or "").lower()
                or q in (e.get("tag") or "").lower()
                or q in (e.get("task_slug") or "").lower()
            ]
        if limit is not None:
            entries = entries[:limit]
        return {"bowl": bowl, "results": entries, "count": len(entries)}

    if bowl == "memo":
        # 붙어 있는 메모 조회(namu-56). SQLite를 타지 않는 것은 profile과 같지만
        # 이유가 다르다 — profile은 작아서 통째 로딩이 싸기 때문이고, memo는
        # **learnings 검색 인덱스에 섞이면 안 되는 것**이 그릇의 존재 이유이기
        # 때문이다. 붙인 순서(오래된 것 먼저)가 스틱노트의 자연스러운 순서라
        # 다른 그릇과 달리 시간 역순으로 뒤집지 않는다.
        memos = _memo.load_all()
        if machine is not None:
            memos = [m for m in memos if m.get("machine") == machine]
        if via is not None:
            memos = [m for m in memos if m.get("via") == via]
        if since is not None:
            memos = [m for m in memos if (m.get("timestamp") or "") >= since]
        if until is not None:
            op, bound = _until_bound(until)
            if op == "<":
                memos = [m for m in memos if (m.get("timestamp") or "") < bound]
            else:
                memos = [m for m in memos if (m.get("timestamp") or "") <= bound]
        if query:
            q = query.lower()
            def _memo_matches(m: dict) -> bool:
                # 3층 전부를 훑는다 — 원문(body)에만 있는 말로도 찾혀야 붙여둔 자료를
                # 다시 꺼낼 수 있다. 옛 메모(text 한 칸)도 같은 헬퍼가 돌려준다.
                summary, reason, body = _memo.layers(m)
                haystack = " ".join([summary, reason, body])
                haystack += " " + " ".join(str(t) for t in (m.get("tags") or []))
                return q in haystack.lower()

            memos = [m for m in memos if _memo_matches(m)]
        if limit is not None:
            memos = memos[:limit]
        return {"bowl": bowl, "results": memos, "count": len(memos)}

    # bowl == "profile"
    docs = _profile.active()
    if machine is not None:
        docs = [d for d in docs if d.get("machine") == machine]
    if via is not None:
        docs = [d for d in docs if d.get("via") == via]
    if since is not None:
        docs = [d for d in docs if (d.get("timestamp") or "") >= since]
    if until is not None:
        op, bound = _until_bound(until)
        if op == "<":
            docs = [d for d in docs if (d.get("timestamp") or "") < bound]
        else:
            docs = [d for d in docs if (d.get("timestamp") or "") <= bound]
    if query:
        q = query.lower()

        def _matches(d: dict) -> bool:
            # 3층 전부를 훑는다(완료조건 11). 옛 이름(statement/source)으로 쌓인
            # 항목도 같은 헬퍼가 돌려주므로 검색에서 빠지지 않는다.
            summary, reason, body = _profile.layers(d)
            fields = [d.get("subject"), summary, reason, body]
            tags = d.get("tags") or []
            haystack = " ".join(str(f) for f in fields if f) + " " + " ".join(str(t) for t in tags)
            return q in haystack.lower()

        docs = [d for d in docs if _matches(d)]

    docs = sorted(docs, key=lambda d: d.get("timestamp") or "", reverse=True)
    if limit is not None:
        docs = docs[:limit]
    return {"bowl": bowl, "results": docs, "count": len(docs)}
