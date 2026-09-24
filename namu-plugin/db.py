import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta

import yaml
from ulid import ULID

import attachments as _attachments
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
_LEARNINGS_SCHEMA = """
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

# ---------------------------------------------------------------------------
# 그릇 색인 (fts5-memo-tasks-index — docs/search_index_unify.md)
# ---------------------------------------------------------------------------
#
# 교훈만 색인을 타고 나머지 네 그릇은 질의마다 파일을 통째로 읽던 구조를, 다섯
# 그릇 모두 SQLite를 타도록 모은다. 판단 근거는 성능이 아니라 **통일성**이다
# (설계서 2장, 사용자 결정) — 조회 경로가 그릇마다 다르면 같은 결함을 다섯 번
# 고쳐야 하고, 실제로 "낱말을 띄어 쓰면 순서가 다를 때 0건"이라는 결함이 네 그릇
# 전부에서 따로 자랐다.
#
# 원본은 파일 그대로 둔다(개발 원칙 2). 색인은 지워도 다시 만들어지는 사본이며,
# 파일 읽기가 없어지는 게 아니라 **질의 시점에서 동기화 시점으로 옮겨간다.**
#
# 왜 그릇마다 "칸을 그대로 옮긴 표"가 아니라 text·doc 두 칸이냐:
#  - `doc`은 원본 dict를 JSON으로 통째 담는다. 검색 결과의 모양이 옛 경로와 글자
#    하나까지 같아야 하는데(설계서 4장 결정 5), 칸을 골라 옮기면 그릇에 칸이 하나
#    늘 때마다 색인이 조용히 그 칸을 빠뜨린다 — 첨부 기록 그릇이 실제로 그렇게
#    나중에 늘었다.
#  - `text`는 옛 파이썬 필터가 질의마다 만들던 건초더미를 색인 시점에 한 번 만들어
#    둔 것이다. 검색 대상 범위를 옛 경로와 같게 유지하면서, 두 곳이 어긋날 여지를
#    없앤다.
# 축 필터(machine/via/project/task/timestamp)만 별도 칸으로 뺀다 — 이건 SQL이
# 걸러야 색인의 이득이 난다.
#
# ⚠️ 첨부 기록의 급소(설계서 9.3): 이 색인의 입력원은 attachments.yaml **하나뿐**
# 이다. 파일 목록이나 크기를 사용자 저장소에 물어 보완하지 않는다 — 물으면 git이
# 크기를 알아내려고 빠진 파일 몸통을 전부 내려받아(2026-08-07 실측: 2,548개에 7분
# 넘게 안 끝남) "색인 다시 만들기" 한 번에 격리가 되돌릴 수 없이 뚫린다.

# 표 모양이 바뀌면 이 숫자를 올린다 — 서명에 섞여 들어가므로 기존 설치본의 색인이
# 자동으로 낡음 판정을 받아 재생성된다(옛 스키마 db가 방치되던 0.1.26 사고와 같은
# 경로를 미리 막는다).
_INDEX_SCHEMA_VERSION = 1

# 교훈은 제 표(learnings)를 따로 갖는다. 여기 넷은 같은 모양의 표를 나눠 쓴다.
# 쪽지가 자기 표를 갖는 것은 namu-56과 충돌하지 않는다 — 그때 금지한 것은 "교훈
# 검색 색인에 섞이는 것"이지 색인을 갖는 것 자체가 아니다(설계서 4장 결정 3).
_INDEXED_BOWLS = ("tasks", "memo", "profile", "attachments")


def _bowl_table(bowl: str) -> str:
    return f"bowl_{bowl}"


def _bowl_schema_sql(bowl: str) -> str:
    table = _bowl_table(bowl)
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    rowid     INTEGER PRIMARY KEY,
    id        TEXT,
    timestamp TEXT NOT NULL DEFAULT '',
    machine   TEXT NOT NULL DEFAULT '',
    via       TEXT NOT NULL DEFAULT '',
    project   TEXT NOT NULL DEFAULT '',
    task      TEXT NOT NULL DEFAULT '',
    text      TEXT NOT NULL DEFAULT '',
    doc       TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS {table}_fts USING fts5(
    text,
    content='{table}',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS {table}_ai AFTER INSERT ON {table} BEGIN
  INSERT INTO {table}_fts(rowid, text) VALUES (new.rowid, new.text);
END;
"""


# 그릇별 색인 상태. 낡았는지 판정하는 유일한 근거이며, 원본이 바뀌었는지를
# 서명(signature) 한 문자열로 비교한다.
_INDEX_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_meta (
    bowl       TEXT PRIMARY KEY,
    signature  TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    n          INTEGER NOT NULL
);
"""

_SCHEMA = (
    _LEARNINGS_SCHEMA
    + _INDEX_META_SCHEMA
    + "".join(_bowl_schema_sql(bowl) for bowl in _INDEXED_BOWLS)
)

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
    # 기준 시간대(cfg.now)로 찍는다 — namu-71. 여기만 UTC로 남아 있어서 같은 서버에
    # 5분 간격으로 저장한 쪽지(+09:00)와 교훈(+00:00)의 시각이 9시간 어긋났다.
    timestamp = cfg.now().isoformat()
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


def _iso_text(value):
    """yaml이 날짜·시각으로 읽어 버린 값을 ISO 문자열로 되돌린다. 나머지는 그대로.

    원본 yaml에 따옴표 없이 `timestamp: 2026-09-01T12:00:00+09:00`이 적혀 있으면
    PyYAML이 문자열이 아니라 datetime으로 읽는다(손으로 고친 파일, 다른 도구가 쓴
    파일). 그대로 SQLite에 넘기면 기본 변환기가 `2026-09-01 12:00:00+09:00`(공백
    구분)으로 담아 since/until 사전순 비교가 어긋나고(파이썬 3.12부터는
    DeprecationWarning), 따옴표 있는 항목(str)과 섞이면 정렬이 TypeError로 터진다
    (2026-09-25 리뷰 B 실측 — 개인 사실 검색 전체가 멈췄다). isoformat은 `T` 구분이라
    db.record가 적는 모양과 같다.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _iso_doc(doc: dict) -> dict:
    """기록 dict 한 건의 최상위 칸을 `_iso_text`로 맞춘 사본."""
    return {k: _iso_text(v) for k, v in doc.items()}


def _rebuild_in_one_transaction(db_path, script: str, fill) -> None:
    """표를 지우고 다시 채우는 일을 **트랜잭션 하나**로 한다(2026-09-25 리뷰 B).

    예전에는 DROP/CREATE(executescript, 자동 커밋)와 INSERT(`with conn:`)가 따로
    커밋돼, 그 사이에 다른 프로세스(다른 세션의 검색, 웹 서버)가 읽으면 빈 표나
    `no such table`을 받았다 — "쪽지 0건"이 오류 없이 답으로 나간다. 한 트랜잭션이면
    읽는 쪽은 커밋 전까지 **옛 색인 전체**를 본다.

    `BEGIN IMMEDIATE`를 스크립트 **안에** 넣는 이유: `executescript`는 이미 열린
    트랜잭션이 있으면 먼저 COMMIT해 버린다(파이썬 sqlite3의 옛 트랜잭션 모드). 스크립트가
    스스로 트랜잭션을 열게 하면 그 커밋이 끼어들 틈이 없고, 트리거 본문의 `;` 때문에
    스크립트를 문장별로 쪼갤 필요도 없다. isolation_level=None이라 뒤따르는
    executemany도 암묵 BEGIN/COMMIT 없이 같은 트랜잭션 안에서 돈다.
    """
    with closing(sqlite3.connect(db_path, isolation_level=None)) as conn:
        try:
            conn.executescript("BEGIN IMMEDIATE;" + script)
            fill(conn)
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def rebuild_from_yaml(paths: "cfg.DataPaths | None" = None) -> int:
    p = paths or cfg.data_paths_for()
    yaml_path = p.learnings_yaml
    p.db_path.parent.mkdir(parents=True, exist_ok=True)

    docs = []
    if yaml_path.exists():
        docs = [
            _iso_doc(d)
            for d in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8"))
            if d
        ]

    def fill(conn: sqlite3.Connection) -> None:
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

    _rebuild_in_one_transaction(
        p.db_path,
        "DROP TRIGGER IF EXISTS learnings_ai;"
        "DROP TABLE IF EXISTS learnings_fts;"
        "DROP TABLE IF EXISTS learnings;"
        + _SCHEMA,
        fill,
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


# ---------------------------------------------------------------------------
# 색인 2단계 — 원본 파일을 표에 채운다
# ---------------------------------------------------------------------------


def _bowl_source_files(bowl: str, paths: "cfg.DataPaths") -> list:
    """그 그릇의 원본 파일 목록. **낡음 판정과 재색인이 같은 목록을 본다.**

    작업일지만 파일이 여럿이다(개인 풀의 log.md와 task.md 전부, 2026-08-08 기준
    각 84개). 목록 자체가 판정 근거에 들어가야 새 작업 폴더가 생긴 것도 낡음으로
    잡힌다. **task.md도 반드시 함께 훑는다** — 색인에는 담고 판정에서 빼면, 설명서만
    고쳐 쓴 경우(완료조건 체크 등) 서명이 그대로라 색인이 영영 안 따라온다.

    첨부 기록은 yaml 한 장뿐이다 — 사용자 저장소(attach_file/)는 여기 절대 들어오지
    않는다(설계서 9.3).

    ⚠️ 작업일지는 `paths`를 보지 않는다 — 늘 `Path.home()/.namu/tasks` 풀이다
    (`task_resolve._tasks_pool_root`, DataPaths에 그 칸이 없다). 다른 데이터 루트를
    `paths`로 줘도 작업일지 색인은 **이 프로세스 HOME의 풀**을 담는다. 클라우드는
    그래서 작업일지만 코어 색인을 안 쓰고 회원 폴더를 직접 훑는다
    (namu-cloud-routing `_task_journal_for_user`). 막지 않고 적어 두는 이유: 시험과
    `ensure_indexes(paths)`가 가짜 HOME과 가짜 데이터 루트를 함께 쓰며 이 경로를
    정상으로 타기 때문이다.
    """
    if bowl == "tasks":
        try:
            pool = task_resolve._tasks_pool_root()
            return sorted(
                list(pool.glob("*/*/log.md")) + list(pool.glob("*/*/task.md"))
            )
        except OSError:
            return []
    if bowl == "memo":
        return [paths.memo_yaml or cfg.MEMO_YAML_PATH]
    if bowl == "profile":
        return [paths.profile_yaml]
    if bowl == "attachments":
        return [paths.attachments_yaml or cfg.ATTACHMENTS_YAML_PATH]
    raise ValueError(f"색인 대상 그릇이 아닙니다: {bowl!r}")


def _bowl_signature(bowl: str, paths: "cfg.DataPaths") -> str:
    """원본이 바뀌었는지 가리는 서명. 파일마다 (경로·크기·수정시각)을 모아 해시한다.

    왜 내용 해시가 아니라 stat이냐: 판정은 세션 시작·서버 부팅·pull 직후마다 도는데,
    작업일지 원본만 1.7MB/84개다. stat은 파일을 열지 않아 목록이 커져도 사실상 공짜다.
    크기와 나노초 수정시각이 **둘 다** 같으면서 내용만 다른 경우는 실질적으로 없다.

    왜 그릇마다 다른 판정이 아니라 하나로 통일했나: 설계서 6장 3단계는 그릇별 판정을
    권했고 9.6은 첨부 기록에 "기록 수 비교"를 적었지만, 그 둘을 합쳐 보면 결국
    ①작업일지는 파일 목록+크기·시각이 필요하고 ②쪽지는 mutable이라 건수 비교로는
    "건수가 같은 채 내용만 바뀐" 경우를 못 잡는다. 크기·수정시각 서명 하나가 네 경우를
    모두 덮으면서 더 엄격하다 — 판정이 그릇마다 갈라지면 이 작업이 없애려는 결함
    (그릇마다 다른 경로)이 판정 쪽에서 그대로 되살아난다.

    스키마 판(version)을 섞는 이유: 표 모양이 바뀌면 원본이 그대로여도 재색인해야 한다.
    """
    parts = [f"v{_INDEX_SCHEMA_VERSION}"]
    for path in _bowl_source_files(bowl, paths):
        try:
            st = path.stat()
            parts.append(f"{path}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            # 파일이 없는 것도 하나의 상태다 — 생기거나 사라지면 서명이 바뀐다.
            parts.append(f"{path}|missing")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _haystack(*values, tags=None) -> str:
    """검색이 훑을 건초더미 한 덩어리. 옛 파이썬 필터가 만들던 것과 같은 범위."""
    parts = [str(v) for v in values if v]
    parts += [str(t) for t in (tags or [])]
    return " ".join(parts)


def _bowl_rows(bowl: str, paths: "cfg.DataPaths") -> list[tuple]:
    """색인에 넣을 행을 **화면에 나갈 순서 그대로** 만든다.

    순서를 여기서 정해 두면 질의는 언제나 `ORDER BY rowid`면 되고, 옛 경로의 정렬
    (파이썬 sorted는 안정 정렬이라 동점은 읽은 순서 유지)과 결과가 글자 그대로 같다.
    정렬을 질의 쪽에 두면 동점 처리가 미묘하게 달라져 "대부분 같은데 가끔 다른"
    회귀가 생기는데, 그건 발견이 가장 늦는 종류의 결함이다.

    축 칸은 None을 빈 문자열로 바꿔 담는다 — 옛 코드가 `d.get("machine") == machine`
    로 걸러 None이 걸리지 않던 것과 SQL 비교 결과를 같게 맞추기 위해서다(SQL에서
    NULL 비교는 참도 거짓도 아닌 NULL이 되어 범위 필터의 포함/제외가 뒤집힌다).
    """
    rows: list[tuple] = []

    if bowl == "tasks":
        # 작업일지 그릇에는 두 종류가 들어간다 — log.md **한 줄**(진행 기록)과
        # task.md **한 장**(작업 설명서, 2026-08-08 사용자 결정). 단위가 다른 것을
        # 한 그릇에 섞는 이유는 찾는 사람 쪽 사정이다: "그 작업이 뭐였지"와 "그때
        # 무슨 일이 있었지"는 같은 질문의 앞뒤라, 그릇을 갈라 두면 둘 다 뒤져야 한다.
        # 구분은 tag 칸(`설명서`)이 지고, 반환 모양은 완전히 같다.
        #
        # 두 목록을 합친 뒤 journal()과 **같은 키로** 다시 세운다. 키가 같고 파이썬
        # 정렬이 안정 정렬이라 일지 줄끼리의 상대 순서는 합치기 전과 글자 그대로
        # 같다 — 설명서가 사이사이 끼어들 뿐 기존 결과가 재배열되지 않는다.
        merged = task_resolve.journal(project=None, limit=None) + task_resolve.task_docs()
        merged.sort(key=lambda e: (e["ts"], e["project"], e["task_slug"]), reverse=True)
        for e in merged:
            rows.append((
                None,
                e.get("ts") or "",
                e.get("machine") or "",
                e.get("via") or "",
                e.get("project") or "",
                e.get("task_slug") or "",
                # 옛 분기는 text/detail/tag/task_slug 네 칸을 각각 부분일치로 봤다.
                # 이어 붙여도 낱말 하나짜리 질의에는 결과가 같고, 여러 낱말은
                # 어차피 낱말별 AND로 바뀐다(설계서 7장 끝).
                _haystack(e.get("text"), e.get("detail"), e.get("tag"), e.get("task_slug")),
                json.dumps(e, ensure_ascii=False, default=str),
            ))
        return rows

    # 아래 셋은 yaml을 읽으므로 따옴표 없는 시각이 datetime으로 올 수 있다 — 정렬·
    # 비교·JSON 담기 전에 ISO 문자열로 맞춘다(`_iso_text`).
    if bowl == "memo":
        # 붙인 순서(오래된 것 먼저)가 스틱노트의 자연스러운 순서라 뒤집지 않는다.
        for m in map(_iso_doc, _memo.load_all(paths)):
            summary, reason, body = _memo.layers(m)
            rows.append((
                m.get("id"),
                m.get("timestamp") or "",
                m.get("machine") or "",
                m.get("via") or "",
                "",
                "",
                _haystack(summary, reason, body, tags=m.get("tags")),
                json.dumps(m, ensure_ascii=False, default=str),
            ))
        return rows

    if bowl == "profile":
        # active()는 정정된(supersede된) 옛 항목을 뺀 목록이다. 색인 대상도 그것이며,
        # 정정이 추가되면 profile.yaml이 바뀌므로 서명이 달라져 다시 만들어진다.
        docs = sorted(
            map(_iso_doc, _profile.active(paths=paths)),
            key=lambda d: d.get("timestamp") or "",
            reverse=True,
        )
        for d in docs:
            summary, reason, body = _profile.layers(d)
            rows.append((
                d.get("id"),
                d.get("timestamp") or "",
                d.get("machine") or "",
                d.get("via") or "",
                "",
                "",
                _haystack(d.get("subject"), summary, reason, body, tags=d.get("tags")),
                json.dumps(d, ensure_ascii=False, default=str),
            ))
        return rows

    if bowl == "attachments":
        # 색인 행의 단위는 파일이 아니라 **기록**이다(설계서 9.4 ②). 같은 파일에
        # 올림 → 새 판 → 지움이 여러 줄 쌓이는데, 최신 한 줄만 담으면 지운 파일의
        # 기록과 그 이유가 검색에서 사라져 "그 자료 어디 갔지"에 답할 수 없게 된다.
        items = sorted(
            map(_iso_doc, _attachments.load_all(paths)),
            key=lambda a: str(a.get("timestamp") or ""),
            reverse=True,
        )
        for a in items:
            summary, reason, body = _attachments.layers(a)
            rows.append((
                a.get("id"),
                a.get("timestamp") or "",
                a.get("machine") or "",
                a.get("via") or "",
                a.get("project") or "",
                # 파일에 적히는 칸 이름은 topic이 아니라 task다(설계서 9.2).
                a.get("task") or "",
                # 파일 이름(path)을 반드시 넣는다 — 첨부를 다시 찾을 때 사람이
                # 기억하는 것은 대개 내용 설명이 아니라 파일 이름이다(9.4 ①).
                _haystack(
                    a.get("path"), summary, reason, body,
                    a.get("task"), a.get("project"), tags=a.get("tags"),
                ),
                json.dumps(a, ensure_ascii=False, default=str),
            ))
        return rows

    raise ValueError(f"색인 대상 그릇이 아닙니다: {bowl!r}")


# ---------------------------------------------------------------------------
# 색인 3단계 — 낡았나 판정하고 다시 만든다
# ---------------------------------------------------------------------------
#
# 쓰기 계열이라 conn을 인자로 받지 않고 함수 안에서 열고 닫는다(CLAUDE.md의 의도된
# 분리 — 읽기는 conn을 받고 쓰기는 스스로 연다).


def rebuild_bowl_index(bowl: str, paths: "cfg.DataPaths | None" = None) -> int:
    """그 그릇의 색인을 통째로 다시 만들고 담은 행 수를 반환한다.

    증분이 아니라 전량이다. 지금 규모에서 전량 재색인은 작업일지 579줄 86ms(설계서
    7장 실측)이고 나머지 셋은 그보다 훨씬 작다 — 증분은 "어디까지 반영됐나"라는
    상태를 하나 더 만들고, 그 상태가 틀어지면 조용히 일부만 검색되는 결함이 된다.

    **서명을 원본보다 먼저 잰다**(2026-09-25 리뷰 B). 예전에는 행을 읽은 **뒤에**
    서명을 재서, 그 사이 다른 프로세스가 원본에 한 건을 붙이면 "새 파일의 서명 +
    옛 내용의 행"이 저장됐다 — 다음 판정은 서명이 같으니 "최신"이라 하고, 그 한 건은
    원본이 또 바뀔 때까지 검색에 영영 안 잡혔다. 먼저 재면 경합이 나도 최악이
    "옛 서명 + 새 내용"이라 다음 판정에서 한 번 더 다시 만들 뿐이다(틀리는 쪽이
    안전한 쪽으로 바뀐다).

    지우고 채우는 일은 트랜잭션 하나다(`_rebuild_in_one_transaction`) — 도중에 읽는
    쪽이 빈 표를 보지 않는다.
    """
    p = paths or cfg.data_paths_for()
    table = _bowl_table(bowl)
    signature = _bowl_signature(bowl, p)
    rows = _bowl_rows(bowl, p)

    p.db_path.parent.mkdir(parents=True, exist_ok=True)

    def fill(conn: sqlite3.Connection) -> None:
        conn.executemany(
            f"INSERT INTO {table}"
            " (id, timestamp, machine, via, project, task, text, doc)"
            " VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO index_meta (bowl, signature, indexed_at, n)"
            " VALUES (?,?,?,?)",
            (bowl, signature, cfg.now().isoformat(), len(rows)),
        )

    _rebuild_in_one_transaction(
        p.db_path,
        f"DROP TRIGGER IF EXISTS {table}_ai;"
        f"DROP TABLE IF EXISTS {table}_fts;"
        f"DROP TABLE IF EXISTS {table};"
        + _INDEX_META_SCHEMA
        + _bowl_schema_sql(bowl),
        fill,
    )
    return len(rows)


def bowl_index_is_stale(bowl: str, paths: "cfg.DataPaths | None" = None) -> bool:
    """그 그릇의 색인이 낡았으면 True. 표가 아직 없거나 서명이 다르면 낡은 것이다."""
    p = paths or cfg.data_paths_for()
    if not p.db_path.exists():
        return True
    try:
        with closing(sqlite3.connect(p.db_path)) as conn:
            row = conn.execute(
                "SELECT signature FROM index_meta WHERE bowl = ?", (bowl,)
            ).fetchone()
            if row is None:
                return True
            # 표가 실제로 있는지도 본다 — meta만 남고 표가 날아간 db를 그대로
            # 쓰면 질의가 `no such table`로 깨진다.
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (_bowl_table(bowl),),
            ).fetchone()
            if exists is None:
                return True
    except sqlite3.OperationalError:
        return True
    return row[0] != _bowl_signature(bowl, p)


def ensure_bowl_index(bowl: str, paths: "cfg.DataPaths | None" = None) -> bool:
    """낡았으면 다시 만든다. 다시 만들었으면 True.

    검색 진입점이 매번 이걸 부른다 — 방금 남긴 기록이 다음 검색에 안 잡히면
    "기록은 됐는데 검색은 안 되는" 구멍이 생기는데, 옛 경로는 질의마다 파일을 읽어
    그 구멍이 없었다. 판정 비용은 stat 몇 번이라 질의마다 불러도 부담이 없다.
    """
    if bowl not in _INDEXED_BOWLS:
        return False
    p = paths or cfg.data_paths_for()
    if not bowl_index_is_stale(bowl, p):
        return False
    rebuild_bowl_index(bowl, p)
    return True


def ensure_indexes(paths: "cfg.DataPaths | None" = None) -> dict:
    """다섯 그릇의 색인을 한 번에 맞춘다. 그릇마다 다시 만들었는지를 반환.

    세션 시작 훅·서버 부팅·pull 직후가 부르는 단일 진입점이다(설계서 6장 4단계) —
    부르는 쪽이 그릇 목록을 알 필요가 없어야 여섯 번째 그릇이 생겨도 배선이 안 샌다.
    """
    p = paths or cfg.data_paths_for()
    result: dict = {}

    # 교훈은 제 판정을 그대로 쓴다(스키마 컬럼 + 건수). 옛 db를 자동 재생성하는
    # 경로가 이미 실전에서 검증됐으므로 갈아엎지 않는다.
    if not p.db_path.exists() or cache_is_stale(p.learnings_yaml, p.db_path):
        rebuild_from_yaml(paths=p)
        result["learnings"] = True
    else:
        result["learnings"] = False

    for bowl in _INDEXED_BOWLS:
        result[bowl] = ensure_bowl_index(bowl, p)
    return result


# ---------------------------------------------------------------------------
# 색인 5단계 — 색인 표에 질의한다
# ---------------------------------------------------------------------------


def _like_escape(value: str) -> str:
    """LIKE 패턴에서 `%`와 `_`를 글자 그대로 찾게 막는다. `ESCAPE '\\'`와 짝으로 쓴다.

    안 막으면 `namu_49` 같은 이름의 밑줄이 "아무 글자 하나"를 가리켜 `namuX49`까지
    걸린다 — 결과가 늘어나는 쪽의 오탐이라 예외도 안 나고 눈에도 잘 안 띈다.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_index(
    conn: sqlite3.Connection,
    bowl: str,
    query: "str | None",
    conds: list[str],
    params: list,
    limit: "int | None",
) -> list[dict]:
    """색인 표 하나를 질의해 **원본 기록 dict 그대로**의 목록을 돌려준다.

    정렬은 언제나 rowid 오름차순이다 — 색인을 만들 때 이미 화면에 나갈 순서로
    담았기 때문이다(`_bowl_rows`).
    """
    table = _bowl_table(bowl)
    tokens = _query_tokens(query)

    if _use_index(tokens):
        base = (
            f"SELECT t.doc FROM {table}_fts"
            f" JOIN {table} t ON t.rowid = {table}_fts.rowid"
        )
        where = [f"{table}_fts MATCH ?"] + conds
        args = [_fts_match_expr(tokens)] + params
    else:
        base = f"SELECT t.doc FROM {table} t"
        where = [r"t.text LIKE ? ESCAPE '\'"] * len(tokens) + conds
        args = [f"%{_like_escape(t)}%" for t in tokens] + params

    sql = base + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY t.rowid"
    if limit is not None:
        sql += " LIMIT ?"
        args = args + [limit]
    return [json.loads(row[0]) for row in conn.execute(sql, args).fetchall()]


def _bowl_axis_conds(
    bowl: str,
    *,
    project: "str | None",
    task: "str | None",
    machine: "str | None",
    via: "str | None",
    since: "str | None",
    until: "str | None",
) -> tuple[list[str], list]:
    """축 필터를 색인 표의 SQL 조건으로 바꾼다. 옛 파이썬 필터와 같은 뜻이어야 한다.

    그릇마다 다른 곳(경계 해석과 task 매칭)만 갈라진다:
    - 작업일지의 since/until은 날짜만 주면 그날 00:00:00~23:59:59로 넓힌다
      (`task_resolve._normalize_bound`, log.md의 벽시계 문자열 `YYYY-MM-DD HH:MM:SS`
      기준 — `T` 구분·시간대 꼬리로 줘도 이 모양으로 맞춘다).
    - 나머지 셋은 ISO 타임스탬프(`YYYY-MM-DDTHH:MM:SS…+09:00`)라 경계값의 공백
      구분을 `T`로 맞추고(`_iso_bound`) `_until_bound`(다음날 미만) 규칙을 쓴다.
      예전에는 그릇마다 저장 구분자가 다른데 경계값을 그대로 비교해, 같은
      `since='2026-09-01 23:59:59'`가 쪽지에서는 그날 전부를 통과시키고 작업일지에서는
      `T` 형식이 그날 전부를 잘랐다(`T`(0x54) > 공백(0x20), 2026-09-25 리뷰 B).
    - 작업일지의 task는 폴더명 완전 일치 **또는 앞부분 지목**(`namu-49` →
      `namu-49-...`)이고, 첨부 기록의 task는 완전 일치다(옛 동작 그대로).
    """
    conds: list[str] = []
    params: list = []

    if machine is not None:
        conds.append("t.machine = ?")
        params.append(machine)
    if via is not None:
        conds.append("t.via = ?")
        params.append(via)

    if bowl == "tasks":
        if project is not None:
            # journal()은 project를 basename으로 해석한다(경로를 줘도 이름을 줘도 같음).
            conds.append("t.project = ?")
            params.append(task_resolve.tasks_root_for(project).name)
        if task is not None:
            conds.append(r"(t.task = ? OR t.task LIKE ? ESCAPE '\')")
            params.extend([task, f"{_like_escape(task)}-%"])
        if since is not None:
            conds.append("t.timestamp >= ?")
            params.append(task_resolve._normalize_bound(since, end=False))
        if until is not None:
            conds.append("t.timestamp <= ?")
            params.append(task_resolve._normalize_bound(until, end=True))
        return conds, params

    if bowl == "attachments":
        if project is not None:
            conds.append("t.project = ?")
            params.append(project)
        if task is not None:
            conds.append("t.task = ?")
            params.append(task)
    # 쪽지·개인 사실은 task 축을 받지 않는다(옛 분기도 무시했다).

    if since is not None:
        conds.append("t.timestamp >= ?")
        params.append(_iso_bound(since))
    if until is not None:
        op, bound = _until_bound(_iso_bound(until))
        conds.append(f"t.timestamp {op} ?")
        params.append(bound)
    return conds, params


def _iso_bound(value: str) -> str:
    """since/until 경계값을 ISO 저장 형식(교훈·사실·쪽지·첨부 기록)의 구분자로 맞춘다.

    날짜 뒤 11번째 글자가 공백이면(`2026-09-01 12:00:00`, 작업일지 형식) `T`로 바꾼다.
    날짜만 준 값은 그대로다. 작업일지 쪽 짝은 `task_resolve._normalize_bound`다.
    """
    value = value.strip()
    if len(value) > 10 and value[10] == " ":
        value = f"{value[:10]}T{value[11:]}"
    return value


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
    확장하고, 시각까지 주면 그 값 이하(`<=`)로 비교한다.

    시각까지 주되 시간대 꼬리가 없으면(`2026-09-01T23:59:59`) 경계 뒤에 `~`를 붙여
    **준 자리수까지 포함**한다. 저장값은 소수초·시간대 꼬리(`…:59.123456+09:00`)를
    달고 있어, 그대로 `<=`로 비교하면 바로 그 초(분)에 적힌 기록이 빠진다. `~`는
    ISO 문자열에 나오는 어떤 글자(숫자·`.`·`+`·`-`·`:`)보다 커서, 그 접두로 시작하는
    값은 전부 경계 안에 든다.
    """
    value = until.strip()
    if len(value) <= 10:
        d = date.fromisoformat(value)
        return ("<", (d + timedelta(days=1)).isoformat())
    time_part = value[11:]
    if not any(mark in time_part for mark in ("+", "-", "Z", "z")):
        return ("<=", value + "~")
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
    걸면 못 찾는다). since/until은 timestamp(ISO8601 문자열) 사전순 비교.

    ⚠️ timestamp는 기준 시간대(cfg.now) 저장값이다(db.record, namu-71) — tasks/memo
    그릇과 같은 벽시계다. 다만 **저장 형식은 그릇마다 다르다**: 교훈·사실·쪽지·첨부
    기록은 `2026-09-01T12:00:00.123456+09:00`(`T` 구분), 작업일지는
    `2026-09-01 12:00:00`(공백 구분, 시간대 없음)이다. 그래서 경계값은 비교 전에
    그릇의 형식으로 맞춘다(여기서는 `_iso_bound` — 공백을 `T`로). 날짜만 주거나
    어느 형식으로 줘도 같은 뜻이 되는 것은 이 정규화 덕이지 형식이 같아서가 아니다.
    namu-71 이전에 쌓인 항목은 UTC(+00:00)로 적혀 있어 사전순 비교가 그 구간에서만
    최대 9시간 어긋난다(과거 항목이라 최신순 정렬은 뒤집히지 않는다).
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
        # `%`·`_`를 글자 그대로 — 다른 네 그릇의 LIKE와 같은 규칙(`_like_escape`).
        conds.append(f"{prefix}task LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(task)}%")
    if since:
        conds.append(f"{prefix}timestamp >= ?")
        params.append(_iso_bound(since))
    if until:
        clause, val = _until_clause(f"{prefix}timestamp", _iso_bound(until))
        conds.append(clause)
        params.append(val)
    return conds, params


def query_tokens(query: "str | None") -> list[str]:
    """검색어를 낱말로 쪼갠다. 다섯 그릇이 같은 규칙을 쓰기 위한 단일 지점.

    **공개 함수인 이유**: 색인을 못 타는 조회 경로도 같은 규칙을 써야 하기 때문이다.
    클라우드 라우팅의 작업일지 조회가 그렇다 — 그쪽은 회원별 폴더를 훑느라 코어의
    `search_bowl`을 못 부르고, 그래서 거르는 규칙을 **자기 파일에 베껴 두었다가**
    낱말 AND 개선이 거기만 안 들어가는 일이 실제로 벌어졌다. 규칙을 부를 수 있게
    열어 두는 것이 베끼기를 막는 유일한 방법이다(`matches_all_tokens`와 짝).
    """
    return (query or "").strip().split()


# 옛 이름(내부 호출용). 이 모듈 안에서는 그대로 쓰던 이름이 많아 별칭으로 남긴다.
_query_tokens = query_tokens


def matches_all_tokens(query: "str | None", *fields) -> bool:
    """검색어의 낱말이 **전부** 주어진 칸 어딘가에 있으면 True(대소문자 무시).

    색인을 타는 경로(`_search_index`)의 AND 규칙과 같은 뜻을 파이썬 쪽에 그대로
    둔 것이다. 색인을 못 쓰는 조회가 이걸 부르면 두 경로가 갈라지지 않는다.
    검색어가 비면 True(=거르지 않음) — 축만으로 묻는 질의를 막지 않기 위해서다.
    """
    tokens = query_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(str(f) for f in fields if f).lower()
    return all(token.lower() in haystack for token in tokens)


def _use_index(tokens: list[str]) -> bool:
    """이 질의를 trigram 색인으로 던져도 되나 — 낱말이 **전부** 세 글자 이상일 때만.

    trigram 색인은 글을 세 글자씩 겹쳐 잘라 담으므로 두 글자 이하는 자를 조각이 없어
    원리상 0건이 된다(실측: '설계' 0건 / '인덱스' 1건). 우리말 기술용어는 두 글자가
    가장 흔해서(설계·검색·기억·작업·문서·배포·캐시) 우회 없이 색인으로 바꾸면
    검색 품질이 지금보다 나빠진다 — 설계서 5장이 "반드시 함께 들어갈 것"으로 못박은
    조건이다. 짧은 낱말이 하나라도 섞이면 질의 전체를 LIKE 전수 조회로 돌린다.
    """
    return bool(tokens) and all(len(t) >= 3 for t in tokens)


def _fts_match_expr(tokens: list[str]) -> str:
    """낱말별로 나눠 모두 포함(AND)하는 FTS5 식.

    옛 방식은 질의 전체를 큰따옴표로 묶어 구(phrase)로 던져서, 낱말 순서가 다르면
    0건이 됐다(실측: 교훈 '설계 문서' 3건인데 '문서 설계' 0건, 쪽지 'FTS5' 1건·
    '설계' 1건인데 'FTS5 설계' 0건 — 같은 문서에 둘 다 있는데도). 낱말 하나짜리
    질의는 종전과 글자 그대로 같은 식이 된다.
    """
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in tokens)


# 교훈 표에서 본문에 해당하는 칸들 — LIKE 폴백이 훑는 범위(색인 가상표의 칸과 같다).
_LEARNINGS_TEXT_COLS = ("task", "reason", "tags", "summary", "body")


def _learnings_match_clause(query: "str | None") -> tuple[bool, list[str], list]:
    """교훈 검색어 → (색인을 쓰나, 조건절, 파라미터).

    결과 목록과 추세 요약(summary)이 **같은 조건**을 봐야 하므로 한 곳에서 만든다 —
    두 곳에 따로 적혀 있던 탓에 한쪽만 고치면 "결과는 3건인데 집계는 5건"처럼
    조용히 어긋난다.
    """
    tokens = _query_tokens(query)
    if not tokens:
        return False, [], []
    if _use_index(tokens):
        return True, ["learnings_fts MATCH ?"], [_fts_match_expr(tokens)]
    # `%`·`_`는 글자 그대로 찾는다(`_like_escape`) — 다른 네 그릇의 LIKE는 이미 막고
    # 있었고 교훈만 빠져, `%` 한 글자 검색이 교훈 전부를 돌려줬다(2026-09-25 리뷰 B).
    like_group = (
        "(" + " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in _LEARNINGS_TEXT_COLS) + ")"
    )
    conds = [like_group] * len(tokens)
    params = [f"%{_like_escape(t)}%" for t in tokens for _ in _LEARNINGS_TEXT_COLS]
    return False, conds, params


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
    use_fts, match_conds, match_params = _learnings_match_clause(query)

    if use_fts:
        order_clause = "ORDER BY bm25(learnings_fts)" if order == "bm25" else "ORDER BY l.id DESC"
        extra_conds, extra_params = _axis_conds(
            "l.", outcome_filter=outcome_filter, task_type=task_type,
            machine=machine, via=via, task=task, since=since, until=until,
        )
        conds = match_conds + extra_conds
        params = match_params + extra_params
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
        # 검색어가 없으면 match_conds가 비어 필터만 적용된다(없으면 전체) —
        # "어제 hp에서 뭐 했지"처럼 축만으로 묻는 질문에 답하기 위함이다.
        conds = match_conds + extra_conds
        params = match_params + extra_params
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
      - since/until: timestamp(ISO8601 문자열, `T` 구분) 사전순 비교. 경계값은
        `YYYY-MM-DD`·`YYYY-MM-DDTHH:MM:SS`·`YYYY-MM-DD HH:MM:SS` 어느 것이든 받고
        비교 전에 `T` 구분으로 맞춘다(`_iso_bound`). since는 `timestamp >= ?`.
        until은 날짜만 주면(길이<=10) 그날을 포함해야 하므로 다음날 날짜로
        `timestamp < ?`, 시각까지 주면 준 자리수까지 포함한다(`_until_bound`).
        ⚠️ 이 timestamp는 기준 시간대(cfg.now) 저장값이다(db.record, namu-71) —
        tasks(log.md)·memo와 같은 벽시계다(형식은 다르다 — `_axis_conds` 참고).
        namu-71 이전 항목만 UTC로 남아 있어 그 구간의 날짜 경계가 9시간 어긋난다.

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
    use_fts, match_conds, match_params = _learnings_match_clause(query)
    if use_fts:
        extra_conds, extra_params = _axis_conds(
            "l.", task_type=task_type, machine=machine, via=via,
            task=task, since=since, until=until,
        )
        conds = match_conds + extra_conds
        params = match_params + extra_params
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
        conds = match_conds + extra_conds
        params = match_params + extra_params
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


_VALID_BOWLS = ("learnings", "tasks", "profile", "memo", "attachments")


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
    paths: "cfg.DataPaths | None" = None,
) -> dict:
    """다섯 그릇을 같은 축 집합(query/project/task/machine/via/since/until/…)으로
    조회하는 단일 분기 진입점(namu-57 2단계 1단위 · fts5-memo-tasks-index로 색인 통일).

    **다섯 그릇 전부 SQLite 색인을 탄다.** 원본 파일(learnings.yaml / log.md /
    profile.yaml / memo.yaml / attachments.yaml)은 그대로 두고, 색인은 지워도 다시
    만들어지는 사본이다 — 파일 읽기가 없어진 게 아니라 질의 시점에서 동기화 시점으로
    옮겨갔다. 질의 직전에 원본이 바뀌었는지 보고 바뀌었으면 그 그릇만 다시 만든다.

    - `learnings` → `search()` 그대로 위임. 반환 `{"bowl","results","count","summary"}`.
    - 나머지 넷 → 그릇별 색인 표 질의. 반환 `{"bowl","results","count"}`이며
      results의 각 항목은 **원본 기록 dict 그대로**다(색인이 그 dict를 통째로
      담아 두었다가 돌려준다 — 그릇에 칸이 늘어도 색인이 조용히 빠뜨리지 않는다).

    검색어 처리는 다섯 그릇이 같다: 낱말별로 나눠 **모두 포함(AND)**하며, 세 글자
    미만이 섞이면 색인을 건너뛰고 LIKE 전수 조회로 돌린다(설계서 5장 — 두 글자 우회).
    첨부 기록에서는 파일 이름(path)도 검색 대상이고, 크기는 기록의 `bytes` 칸에서만
    읽는다 — 저장소에 물으면 첨부 격리가 뚫린다(설계서 9.3).

    since/until은 `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SS`, `YYYY-MM-DD HH:MM:SS` 어느
    형식으로 줘도 다섯 그릇에서 같은 뜻이다 — 그릇마다 저장 형식이 달라(작업일지만
    공백 구분·시간대 없음) 경계값을 그 그릇의 형식으로 맞춘 뒤 비교한다.

    ⚠️ `paths`는 작업일지(tasks)에는 효과가 없다 — 작업일지 색인은 늘 이 프로세스
    HOME의 개인 풀(`~/.namu/tasks`)을 담는다(`_bowl_source_files` 참고). 색인
    표 자체는 `paths.db_path`에 만들어진다.

    `project`는 tasks·attachments 전용 축이다 — learnings/profile에 project를 주면
    조용히 무시하지 않고 ValueError로 명시 거절한다(조용히 무시하면 웹 AI가 필터가
    걸린 줄 알고 잘못된 결론을 낸다). `task`는 작업일지에서만 앞부분 지목
    (`namu-49` → `namu-49-...`)이 되고, 첨부 기록에서는 완전 일치다(옛 동작 유지).
    """
    if bowl not in _VALID_BOWLS:
        raise ValueError(f"bowl은 {list(_VALID_BOWLS)} 중 하나여야 합니다: {bowl!r}")

    if bowl not in ("tasks", "attachments") and project is not None:
        raise ValueError(
            f"project는 tasks·attachments 전용 축입니다 (bowl={bowl!r}에는 쓸 수 없습니다)"
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

    # 나머지 넷은 색인을 탄다. 질의 직전에 원본이 바뀌었는지 보고 바뀌었으면 그
    # 그릇만 다시 만든다 — 방금 남긴 기록이 다음 검색에 안 잡히는 구멍을 막기
    # 위해서다(옛 경로는 질의마다 파일을 읽어 그 구멍이 없었다). 판정은 stat 몇 번이다.
    p = paths or cfg.data_paths_for()
    ensure_bowl_index(bowl, p)

    conds, params = _bowl_axis_conds(
        bowl, project=project, task=task, machine=machine,
        via=via, since=since, until=until,
    )
    results = _search_index(conn, bowl, query, conds, params, limit)
    return {"bowl": bowl, "results": results, "count": len(results)}
