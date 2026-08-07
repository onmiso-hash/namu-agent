"""티켓 보관 시험 — 발급·상태·소진·정리.

여기서 지키는 것은 세 가지다.
1. **발급은 부작용이 없다.** 안 쓰고 버려진 티켓이 저장소에 흔적을 남기면 안 된다
   — 이 모듈은 저장소를 아예 만지지 않으므로, 그 사실을 "무엇을 부르지 않는가"가
   아니라 이 파일이 저장소 모듈을 import조차 하지 않는 것으로 지킨다.
2. **번호는 예측할 수 없다.** 번호가 곧 인증이라서다.
3. **쓴 티켓은 만료 시각이 지나도 '완료'다.** 회원이 두 시간 뒤에 "올라갔나?"라고
   물었을 때 '만료됨'이라고 답하면 안 올라간 것으로 읽힌다.
"""
from datetime import timedelta

import pytest

import config as cfg
import tickets


@pytest.fixture
def conn(tmp_path):
    c = tickets.connect(tmp_path / "tickets.db")
    yield c
    c.close()


def _make(conn, **kw):
    kw.setdefault("user_key", "gh-1")
    kw.setdefault("kind", tickets.KIND_UPLOAD)
    kw.setdefault("name", "attach_file/보고서.pdf")
    return tickets.create(conn, **kw)


# ---------------------------------------------------------------------------
# 발급과 되읽기
# ---------------------------------------------------------------------------
def test_create_then_get_round_trips_everything(conn):
    made = _make(conn, meta={"summary": "요약", "reason": "왜", "tags": ["가"]})

    got = tickets.get(conn, made["ticket_id"])

    assert got["user_key"] == "gh-1"
    assert got["kind"] == tickets.KIND_UPLOAD
    assert got["name"] == "attach_file/보고서.pdf"
    # 설명은 파일이 도착했을 때 첨부 기록에 적힌다 — 그때 발급한 AI는 그 자리에
    # 없을 수 있으므로 발급 시점의 값을 그대로 얼려 둔다.
    assert got["meta"] == {"summary": "요약", "reason": "왜", "tags": ["가"]}
    assert got["used_at"] is None
    assert got["result"] is None


def test_unknown_ticket_is_none_not_an_error(conn):
    assert tickets.get(conn, "없는번호") is None
    assert tickets.get(conn, "") is None
    assert tickets.get(conn, None) is None


def test_ticket_id_is_long_and_never_repeats(conn):
    ids = {_make(conn)["ticket_id"] for _ in range(20)}

    assert len(ids) == 20
    for ticket_id in ids:
        # token_urlsafe(32) = 256비트. 짧아지면 번호를 넣어 보는 쪽에 문이 열린다.
        assert len(ticket_id) >= 40


def test_ticket_id_does_not_start_with_a_timestamp(conn):
    """ULID를 쓰면 앞부분이 만든 시각이라 이웃한 번호를 좁힐 수 있다."""
    first = _make(conn)["ticket_id"]
    second = _make(conn)["ticket_id"]

    assert first[:10] != second[:10]


def test_short_shows_only_the_head(conn):
    made = _make(conn)

    assert tickets.short(made["ticket_id"]) == made["ticket_id"][:8]
    assert len(tickets.short(made["ticket_id"])) == 8


def test_create_rejects_an_unknown_kind(conn):
    with pytest.raises(ValueError, match="kind"):
        _make(conn, kind="옆길")


def test_upload_and_download_have_different_default_lifetimes():
    # 올리기가 넉넉한 이유: 회원이 링크를 받아 파일을 찾고 올리기까지의 시간이며,
    # AI가 curl로 시도했다가 막혀 회원에게 넘긴 경우까지 들어간다.
    assert tickets.UPLOAD_TTL_SEC > tickets.DOWNLOAD_TTL_SEC


# ---------------------------------------------------------------------------
# 상태
# ---------------------------------------------------------------------------
def test_a_fresh_ticket_is_waiting(conn):
    assert tickets.status_of(tickets.get(conn, _make(conn)["ticket_id"])) == "대기중"


def test_a_missing_ticket_is_none_status():
    assert tickets.status_of(None) == "없음"


def test_a_ticket_past_its_time_is_expired(conn):
    made = _make(conn, ttl_sec=1)
    ticket = tickets.get(conn, made["ticket_id"])

    later = cfg.now() + timedelta(seconds=5)

    assert tickets.status_of(ticket, now=later) == "만료됨"


def test_a_used_ticket_is_done_even_long_after_it_expired(conn):
    """회원이 올린 지 두 시간 뒤에 물어도 '완료'여야 한다 — '만료됨'이라고 답하면
    안 올라간 것으로 읽힌다."""
    made = _make(conn, ttl_sec=1)
    tickets.mark_used(conn, made["ticket_id"], {"path": "attach_file/보고서.pdf"})

    ticket = tickets.get(conn, made["ticket_id"])
    much_later = cfg.now() + timedelta(days=3)

    assert tickets.status_of(ticket, now=much_later) == "완료"


def test_an_unreadable_expiry_counts_as_expired(conn):
    # 닫히는 방향이 안전한 기본값이다.
    assert tickets.status_of({"expires_at": "언젠가"}) == "만료됨"


def test_mark_used_keeps_the_result_for_later_questions(conn):
    made = _make(conn)

    tickets.mark_used(conn, made["ticket_id"], {"path": "attach_file/a.pdf", "bytes": 7})

    ticket = tickets.get(conn, made["ticket_id"])
    assert ticket["used_at"]
    assert ticket["result"] == {"path": "attach_file/a.pdf", "bytes": 7}


# ---------------------------------------------------------------------------
# 정리
# ---------------------------------------------------------------------------
def test_purge_removes_expired_but_unused_tickets(conn):
    stale = _make(conn, ttl_sec=1)
    fresh = _make(conn, ttl_sec=3600)

    removed = tickets.purge_expired(conn, now=cfg.now() + timedelta(seconds=30))

    assert removed == 1
    assert tickets.get(conn, stale["ticket_id"]) is None
    assert tickets.get(conn, fresh["ticket_id"]) is not None


def test_purge_keeps_a_just_used_ticket_so_check_can_still_answer(conn):
    """쓴 티켓을 바로 지우면 '올라갔나?'에 '없음'이라고 답하게 되는데, 그건
    "안 올라갔다"로 읽힌다."""
    made = _make(conn, ttl_sec=1)
    tickets.mark_used(conn, made["ticket_id"], {"path": "attach_file/a.pdf"})

    tickets.purge_expired(conn, now=cfg.now() + timedelta(minutes=30))

    assert tickets.get(conn, made["ticket_id"]) is not None


def test_purge_eventually_removes_used_tickets_too(conn):
    made = _make(conn)
    tickets.mark_used(conn, made["ticket_id"], {"path": "attach_file/a.pdf"})

    tickets.purge_expired(conn, now=cfg.now() + timedelta(days=2))

    assert tickets.get(conn, made["ticket_id"]) is None


def test_tickets_do_not_live_in_the_memory_cache_file():
    """기억 캐시는 yaml에서 통째로 다시 만들어지는 파일이라, 다시 만드는 순간
    발급해 둔 티켓이 함께 날아간다."""
    assert tickets.db_path() != cfg.data_paths_for().db_path
