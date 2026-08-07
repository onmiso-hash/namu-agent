"""티켓 — 파일 몸통이 AI의 출력을 거치지 않고 오가게 하는 일회용 주소.

## 왜 필요한가

`namu_upload_file`은 파일 내용을 base64 글자열로 받는다. 그 글자열은 붙은 AI가
**한 자씩 써야** 하므로 파일 크기에 정비례해 느려진다 — 6KB짜리 문서 하나가
8,100자였고, 서버가 7.4초 걸리는 동안 AI 쪽이 몇 분을 썼다(2026-08-07 실측).
발표자료·PDF·사진처럼 수 MB짜리는 이 방식으로는 사실상 못 다룬다.

티켓은 그 우회로다. AI는 "이 이름으로 파일 하나를 받겠다"는 약속만 만들고(이
모듈), 파일 몸통은 회원의 브라우저나 AI의 `curl`이 그 주소로 **직접** 던진다.
AI의 출력을 한 글자도 거치지 않는다.

## 이 모듈이 지키는 것

1. **티켓 발급은 부작용이 없다.** GitHub에 아무것도 쓰지 않는다 — 그래서 안 쓰고
   버려진 티켓이 쌓여도 저장소에는 흔적이 남지 않고, 실패한 전송 뒤에 티켓을
   살려 두는 것(설계서 7절)이 안전하다.
2. **티켓 번호는 예측할 수 없어야 한다.** 이 번호가 주소에 실리고 인증 수단도
   겸하기 때문이다. 이 저장소가 다른 곳에서 쓰는 ULID를 여기서는 쓰지 않는다 —
   ULID는 앞부분이 만든 시각이라 이웃한 번호를 좁힐 수 있다.
3. **번호 전체를 로그에 남기지 않는다**(`short`). 로그를 보는 사람이 남의 티켓에
   그대로 접근할 수 있게 되기 때문이다.
4. **메모리가 아니라 파일에 둔다.** 서버는 한 개의 프로세스로 뜨므로 메모리에
   둬도 동작은 하지만, 그러면 서버를 다시 띄우는 순간 발급해 둔 티켓이 전부
   사라진다 — 회원이 링크를 받아 두고 잠시 뒤에 여는 것이 정상 흐름이라 그
   사라짐이 곧 고장이다. 표 하나가 더 싸다.

## 두 경로가 같이 쓴다

개인 주소(이 PC의 나무 서버)와 나무 클라우드가 **이 모듈 하나를 같이 쓴다.**
그래서 어느 파일에 담을지를 스스로 정하지 않고 열린 커넥션을 받는다 — 개인
주소는 `~/.namu/db/tickets.db`, 클라우드는 자기 회원 장부에 담는다. 담기는 자리는
서로 달라도 규칙(만료·1회용·번호 굵기)은 한 벌이어야 한다.

기억 캐시(`namu.db`)에 같이 담지 않는 이유: 그 파일은 yaml에서 통째로 다시
만들어지는 캐시라, 다시 만드는 순간 발급해 둔 티켓이 함께 날아간다.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config as cfg

# 만료까지의 시간(설계서 6-2절).
# 올리기가 더 넉넉한 이유: 회원이 링크를 받아 파일을 찾고 올리기까지의 시간이며,
# 여기에는 "AI가 curl로 시도했다가 막혀서 회원에게 넘긴" 경우까지 들어간다.
UPLOAD_TTL_SEC = 2 * 60 * 60
DOWNLOAD_TTL_SEC = 60 * 60

KIND_UPLOAD = "upload"
KIND_DOWNLOAD = "download"

# 바깥에 알리는 상태말. 설계서 5-5절의 네 가지와 같다.
STATUS_DONE = "완료"
STATUS_WAITING = "대기중"
STATUS_EXPIRED = "만료됨"
STATUS_MISSING = "없음"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   TEXT PRIMARY KEY,
    user_key    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    meta_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    result_json TEXT
);
"""

# 만료 정리와 "이 회원의 티켓" 조회가 표를 통째로 훑지 않게 한다.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_tickets_expires ON tickets (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (user_key)",
)


def db_path() -> Path:
    """개인 주소가 티켓을 담는 파일. 기억 캐시와 **다른 파일**이다(위 설명 참고)."""
    return cfg.data_paths_for().db_path.parent / "tickets.db"


def connect(path: "str | Path | None" = None) -> sqlite3.Connection:
    """티켓 파일 커넥션을 연다(표가 없으면 만든다).

    클라우드는 이 함수를 쓰지 않는다 — 이미 열어 둔 회원 장부 커넥션을 그대로
    넘긴다. 이 함수는 담을 파일을 따로 정해야 하는 개인 주소용이다.
    """
    target = str(path) if path is not None else str(db_path())
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    ensure_table(conn)
    return conn


def ensure_table(conn: sqlite3.Connection) -> None:
    """표가 없으면 만든다(멱등).

    `identity.init_db`에 얹지 않고 이 모듈이 스스로 부르는 이유: 신원 장부는
    "누가 가입했나"라는 별개 관심사이고, 그쪽이 티켓을 알게 되면 티켓을 안 쓰는
    경로까지 티켓 표를 지고 다니게 된다. `CREATE TABLE IF NOT EXISTS`는 이미
    있으면 사실상 공짜라 매 호출 불러도 부담이 없다.
    """
    conn.executescript(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def new_ticket_id() -> str:
    """추측할 수 없는 티켓 번호. 256비트 난수이며 주소에 그대로 실린다.

    `identity.generate_mcp_secret`과 같은 굵기다 — 둘 다 "이 값을 아는 것이 곧
    권한"인 자리이므로 굵기를 다르게 둘 이유가 없다.
    """
    return secrets.token_urlsafe(32)


def short(ticket_id: str) -> str:
    """로그·오류 메시지에 적어도 되는 앞부분(8자)."""
    return (ticket_id or "")[:8]


def _now() -> datetime:
    """지금 시각. 코어(`config.now`)와 같은 시계를 쓴다 — 첨부 기록의 시각과
    티켓의 시각이 서로 다른 시계에서 나오면 나중에 대조가 안 된다."""
    return cfg.now()


def _row_to_dict(row: "sqlite3.Row | None") -> "dict | None":
    if row is None:
        return None
    out = dict(row)
    out["meta"] = json.loads(out.pop("meta_json") or "{}")
    raw_result = out.pop("result_json", None)
    out["result"] = json.loads(raw_result) if raw_result else None
    return out


def create(
    conn: sqlite3.Connection,
    user_key: str,
    kind: str,
    name: str,
    meta: "dict | None" = None,
    ttl_sec: "int | None" = None,
) -> dict:
    """티켓 한 장을 발급한다. GitHub에는 아무것도 쓰지 않는다(설계서 5-1절).

    `meta`에는 파일이 도착했을 때 첨부 기록에 적을 설명(summary·reason·body·
    topic·project·tags)과 출처(via)가 들어간다 — 발급한 AI가 알고 있던 것을
    그대로 얼려 둔다. 파일이 도착하는 시점에는 AI가 그 자리에 없을 수 있기
    때문이다(회원이 브라우저로 직접 올리는 경우가 그렇다).
    """
    if kind not in (KIND_UPLOAD, KIND_DOWNLOAD):
        raise ValueError(f"kind는 {KIND_UPLOAD}/{KIND_DOWNLOAD} 중 하나여야 합니다: {kind!r}")
    ensure_table(conn)
    if ttl_sec is None:
        ttl_sec = UPLOAD_TTL_SEC if kind == KIND_UPLOAD else DOWNLOAD_TTL_SEC
    now = _now()
    ticket_id = new_ticket_id()
    expires_at = now + timedelta(seconds=ttl_sec)
    conn.execute(
        "INSERT INTO tickets (ticket_id, user_key, kind, name, meta_json, "
        "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ticket_id, user_key, kind, name,
            json.dumps(meta or {}, ensure_ascii=False),
            now.isoformat(), expires_at.isoformat(),
        ),
    )
    conn.commit()
    return {
        "ticket_id": ticket_id,
        "user_key": user_key,
        "kind": kind,
        "name": name,
        "meta": dict(meta or {}),
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "used_at": None,
        "result": None,
    }


def get(conn: sqlite3.Connection, ticket_id: str) -> "dict | None":
    """티켓 한 장. 없으면 None. **만료 여부는 여기서 판정하지 않는다** —
    만료된 티켓도 "만료됐다"고 안내해야 하므로 호출부가 상태를 물어 쓴다."""
    if not isinstance(ticket_id, str) or not ticket_id:
        return None
    ensure_table(conn)
    row = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    return _row_to_dict(row)


def status_of(ticket: "dict | None", now: "datetime | None" = None) -> str:
    """티켓 한 장의 지금 상태 — 완료 / 대기중 / 만료됨 / 없음.

    쓴 티켓은 만료 시각이 지났어도 '완료'다. 회원이 파일을 올린 지 두 시간 뒤에
    "올라갔나?"라고 물었을 때 '만료됨'이라고 답하면 안 올라간 것으로 읽힌다.
    """
    if ticket is None:
        return STATUS_MISSING
    if ticket.get("used_at"):
        return STATUS_DONE
    moment = now or _now()
    try:
        expires = datetime.fromisoformat(str(ticket.get("expires_at")))
    except (TypeError, ValueError):
        # 시각을 못 읽으면 만료로 본다 — 닫히는 방향이 안전한 기본값이다.
        return STATUS_EXPIRED
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return STATUS_EXPIRED if moment >= expires else STATUS_WAITING


def mark_used(conn: sqlite3.Connection, ticket_id: str, result: dict) -> None:
    """파일이 실제로 도착해 저장까지 끝났음을 적는다.

    **저장이 성공한 뒤에만 부른다**(설계서 7절). 전송이 막히거나 실패한 티켓을
    여기서 닫아 버리면, 회원이 같은 링크에 브라우저로 다시 올리는 길(경로 A)이
    끊긴다 — 그 길을 열어 두는 것이 이 티켓 구조의 목적 절반이다.
    """
    ensure_table(conn)
    conn.execute(
        "UPDATE tickets SET used_at = ?, result_json = ? WHERE ticket_id = ?",
        (_now().isoformat(), json.dumps(result, ensure_ascii=False), ticket_id),
    )
    conn.commit()


def purge_expired(
    conn: sqlite3.Connection,
    now: "datetime | None" = None,
    keep_used_sec: int = 24 * 60 * 60,
) -> int:
    """만료된 티켓을 지운다. 지운 개수를 돌려준다.

    쓴 티켓을 곧바로 지우지 않고 하루 남기는 이유: 회원이 파일을 올린 뒤 붙은
    AI가 `namu_check_ticket`으로 결과를 물어보는 흐름이 있다. 만료 시각이 지났다고
    바로 지우면 그 물음에 '없음'이라고 답하게 되는데, 그건 "안 올라갔다"로 읽힌다.
    """
    ensure_table(conn)
    moment = (now or _now()).isoformat()
    cutoff = ((now or _now()) - timedelta(seconds=keep_used_sec)).isoformat()
    cur = conn.execute(
        "DELETE FROM tickets WHERE (used_at IS NULL AND expires_at < ?) "
        "OR (used_at IS NOT NULL AND used_at < ?)",
        (moment, cutoff),
    )
    conn.commit()
    return cur.rowcount or 0
