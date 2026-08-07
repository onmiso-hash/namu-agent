"""티켓 주소 세 개 시험 — 브라우저와 curl이 같은 문으로 들어온다.

파일을 실제로 저장하는 일은 대역(가짜 함수)으로 대신한다. 여기서 보는 것은 **문
자체**다 — 누구를 들여보내고, 언제 거절하고, 실패했을 때 링크를 태우는가.

가장 중요한 시험은 `test_a_failed_store_leaves_the_link_usable`이다. AI가 던진
전송이 막혔을 때 링크가 죽으면, 회원이 같은 링크로 이어 올리는 길(설계서 7절)이
함께 끊긴다 — 티켓 구조가 존재하는 이유의 절반이 그것이다.
"""
from datetime import timedelta

import pytest
from starlette.testclient import TestClient

import config as cfg
import ticket_web
import tickets

HTML = {"accept": "text/html,application/xhtml+xml"}
JSON = {"accept": "application/json"}


class _Spy:
    """무엇이 저장되러 왔는지 기억하는 대역."""

    def __init__(self, path):
        self.path = path
        self.saved = []
        self.fail_with = None
        self.body = "파일몸통".encode("utf-8")
        self.limit = 20 * 1024 * 1024
        self.session_key = None

    # ticket_web이 부르는 이음새들 -----------------------------------------
    def open_conn(self):
        return tickets.connect(self.path)

    def store_file(self, conn, user_key, name, content, meta, via):
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        self.saved.append(
            {"user_key": user_key, "name": name, "content": content,
             "meta": meta, "via": via}
        )
        return {"id": "01AAA", "path": name, "bytes": len(content), "status": "올림"}

    def fetch_file(self, conn, user_key, name):
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        return self.body

    def max_bytes(self):
        return self.limit

    def session_user_key(self, _request):
        return self.session_key


@pytest.fixture
def spy(tmp_path):
    return _Spy(tmp_path / "tickets.db")


@pytest.fixture
def client(spy):
    app = ticket_web.build_ticket_app(
        open_conn=spy.open_conn, store_file=spy.store_file,
        fetch_file=spy.fetch_file, max_bytes=spy.max_bytes,
        session_user_key=spy.session_user_key,
    )
    return TestClient(app)


def _ticket(spy, kind=tickets.KIND_UPLOAD, user="gh-1", name="attach_file/발표.pptx",
            meta=None, ttl_sec=3600):
    conn = spy.open_conn()
    try:
        return tickets.create(
            conn, user, kind, name,
            meta if meta is not None else {"summary": "발표 자료", "reason": "왜",
                                           "via": "claude"},
            ttl_sec=ttl_sec,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 올리기 화면
# ---------------------------------------------------------------------------
def test_the_upload_page_shows_the_name_and_the_note(spy, client):
    t = _ticket(spy)

    r = client.get(f"/u/{t['ticket_id']}", headers=HTML)

    assert r.status_code == 200
    assert "발표.pptx" in r.text
    assert "발표 자료" in r.text
    # 회원이 큰 파일을 던지는 화면이라 진행률 표시를 포기할 수 없다.
    assert "XMLHttpRequest" in r.text


def test_the_upload_page_never_prints_the_ticket_number(spy, client):
    """번호를 화면·오류에 남기면 그것을 본 사람이 그대로 들어올 수 있다."""
    t = _ticket(spy)

    r = client.get(f"/u/{t['ticket_id']}xxx", headers=HTML)

    assert r.status_code == 404
    assert t["ticket_id"] not in r.text


# ---------------------------------------------------------------------------
# 올리기 — 브라우저와 curl이 같은 문
# ---------------------------------------------------------------------------
def test_a_posted_file_is_stored_and_the_link_is_spent(spy, client):
    t = _ticket(spy)

    r = client.post(
        f"/u/{t['ticket_id']}", files={"file": ("발표.pptx", b"\x00\x01\x02")},
        headers=JSON,
    )

    assert r.status_code == 200
    assert r.json()["path"] == "attach_file/발표.pptx"
    assert spy.saved[0]["content"] == b"\x00\x01\x02"
    # 이름은 티켓에 적힌 것을 쓴다 — 보내는 쪽이 준 파일 이름이 아니다.
    assert spy.saved[0]["name"] == "attach_file/발표.pptx"

    conn = spy.open_conn()
    try:
        assert tickets.status_of(tickets.get(conn, t["ticket_id"])) == "완료"
    finally:
        conn.close()


def test_the_note_from_the_ticket_reaches_the_log(spy, client):
    """발급할 때 AI가 적어 둔 설명이 파일이 도착한 시점에 그대로 쓰여야 한다 —
    회원이 브라우저로 올릴 때 그 AI는 그 자리에 없다."""
    t = _ticket(spy, meta={"summary": "요약", "reason": "왜", "via": "claude"})

    client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON)

    saved = spy.saved[0]
    assert saved["meta"]["summary"] == "요약"
    assert saved["via"] == "claude"
    # via는 첨부 기록의 출처 칸으로 가지 설명 칸에 남지 않는다.
    assert "via" not in saved["meta"]


def test_the_same_link_cannot_be_used_twice(spy, client):
    t = _ticket(spy)
    client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON)

    again = client.post(
        f"/u/{t['ticket_id']}", files={"file": ("x", b"cd")}, headers=JSON
    )

    assert again.status_code == 409
    assert len(spy.saved) == 1


def test_an_expired_link_is_refused(spy, client):
    t = _ticket(spy, ttl_sec=-1)

    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON)

    assert r.status_code == 410
    assert spy.saved == []


def test_an_unknown_link_is_refused(spy, client):
    r = client.post("/u/그런것없음", files={"file": ("x", b"ab")}, headers=JSON)

    assert r.status_code == 404


def test_a_download_link_cannot_be_used_to_upload(spy, client):
    """종류가 다른 티켓도 '없음'으로 답한다 — 있고 없고를 알려 주면 번호를
    넣어 보는 쪽에 정보를 주게 된다."""
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD)

    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON)

    assert r.status_code == 404


def test_a_logged_in_stranger_is_refused(spy, client):
    """설계서 12절 — 다른 사용자의 링크로 브라우저 접근하면 거절된다."""
    t = _ticket(spy, user="gh-1")
    spy.session_key = "gh-2"

    r = client.get(f"/u/{t['ticket_id']}", headers=HTML)

    assert r.status_code == 403


def test_the_owner_gets_in(spy, client):
    t = _ticket(spy, user="gh-1")
    spy.session_key = "gh-1"

    assert client.get(f"/u/{t['ticket_id']}", headers=HTML).status_code == 200


def test_curl_without_a_session_gets_in(spy, client):
    """curl에는 쿠키가 없다 — 티켓 번호 자체를 인증으로 인정한다(설계서 5-4절)."""
    t = _ticket(spy)
    spy.session_key = None

    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON)

    assert r.status_code == 200


def test_a_file_over_the_limit_is_refused_before_it_is_stored(spy, client):
    spy.limit = 4
    t = _ticket(spy)

    r = client.post(
        f"/u/{t['ticket_id']}", files={"file": ("x", b"12345")}, headers=JSON
    )

    assert r.status_code == 413
    assert spy.saved == []


def test_an_empty_file_is_refused(spy, client):
    t = _ticket(spy)

    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"")}, headers=JSON)

    assert r.status_code == 400
    assert spy.saved == []


def test_a_post_with_no_file_says_so(spy, client):
    t = _ticket(spy)

    r = client.post(f"/u/{t['ticket_id']}", data={"note": "파일아님"}, headers=JSON)

    assert r.status_code == 400


def test_a_failed_store_leaves_the_link_usable(spy, client):
    """설계서 7절 — AI의 전송이 막혀도 링크는 살아 있어야 한다. 그래야 회원이
    같은 링크에 브라우저로 이어 올릴 수 있다(경로 D → 경로 A)."""
    t = _ticket(spy)
    spy.fail_with = "host_not_allowed"

    failed = client.post(
        f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON
    )
    assert failed.status_code == 502

    conn = spy.open_conn()
    try:
        assert tickets.status_of(tickets.get(conn, t["ticket_id"])) == "대기중"
    finally:
        conn.close()

    # 그리고 실제로 이어 올릴 수 있다.
    spy.fail_with = None
    again = client.post(
        f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")}, headers=JSON
    )
    assert again.status_code == 200


def test_a_browser_gets_a_page_and_curl_gets_json(spy, client):
    t = _ticket(spy, ttl_sec=-1)

    as_browser = client.get(f"/u/{t['ticket_id']}", headers=HTML)
    as_curl = client.get(f"/u/{t['ticket_id']}", headers=JSON)

    assert "<html" in as_browser.text
    assert as_curl.json()["error"]


# ---------------------------------------------------------------------------
# 받기
# ---------------------------------------------------------------------------
def test_a_download_link_sends_the_file_as_an_attachment(spy, client):
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD, name="attach_file/보고서.pdf")

    r = client.get(f"/d/{t['ticket_id']}")

    assert r.status_code == 200
    assert r.content == spy.body
    assert "attachment" in r.headers["content-disposition"]
    # 회원의 사적 파일이 중간 캐시에 남으면 안 된다.
    assert "no-store" in r.headers["cache-control"]


def test_a_korean_file_name_survives_the_header(spy, client):
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD, name="attach_file/보고서.pdf")

    r = client.get(f"/d/{t['ticket_id']}")

    # `filename=`은 ASCII만 실을 수 있어 한글이 깨진다 — RFC 5987 쪽이 함께 있어야 한다.
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert "%EB%B3%B4%EA%B3%A0%EC%84%9C" in r.headers["content-disposition"]


def test_a_download_link_still_works_the_second_time(spy, client):
    """첫 클릭에 링크를 닫으면 회원 눈에는 고장으로 보인다. 서버는 애초에 회원이
    파일을 실제로 손에 넣었는지 알 수 없어 '받았음' 표시가 반쪽이다."""
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD)

    assert client.get(f"/d/{t['ticket_id']}").status_code == 200
    assert client.get(f"/d/{t['ticket_id']}").status_code == 200


def test_an_expired_download_link_is_refused(spy, client):
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD, ttl_sec=-1)

    assert client.get(f"/d/{t['ticket_id']}").status_code == 410


def test_an_upload_link_cannot_be_used_to_download(spy, client):
    t = _ticket(spy, kind=tickets.KIND_UPLOAD)

    assert client.get(f"/d/{t['ticket_id']}").status_code == 404


def test_a_failed_fetch_is_reported_not_swallowed(spy, client):
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD)
    spy.fail_with = "저장소가 대답하지 않음"

    r = client.get(f"/d/{t['ticket_id']}", headers=JSON)

    assert r.status_code == 502


# ---------------------------------------------------------------------------
# 요청 가르기 — 티켓 주소는 인증 미들웨어 바깥에 선다
# ---------------------------------------------------------------------------
def _labelled(label):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": label.encode()})

    return app


def test_ticket_paths_bypass_the_rest_of_the_stack():
    client = TestClient(
        ticket_web.TicketOrAppDispatcher(_labelled("mcp"), _labelled("ticket"))
    )

    assert client.get("/u/abc").text == "ticket"
    assert client.get("/d/abc").text == "ticket"


def test_everything_else_still_goes_through_the_authenticated_side():
    client = TestClient(
        ticket_web.TicketOrAppDispatcher(_labelled("mcp"), _labelled("ticket"))
    )

    for path in ["/mcp", "/u", "/d", "/ux/abc", "/"]:
        assert client.get(path).text == "mcp", f"{path!r}가 티켓 쪽으로 샜다"


def test_lifespan_scope_is_never_treated_as_a_ticket_path():
    """lifespan scope에는 'path' 키가 없다 — 여기서 걸리면 서버가 뜨지 못한다."""
    assert ticket_web.is_ticket_path("") is False


# ---------------------------------------------------------------------------
# 저장·받기가 받는 커넥션 (2026-08-07 운영 502)
# ---------------------------------------------------------------------------
def _client_for(spy):
    """대역을 바꾼 뒤 앱을 만든다 — `client` 붙박이는 만들 때의 대역을 붙잡는다."""
    return TestClient(ticket_web.build_ticket_app(
        open_conn=spy.open_conn, store_file=spy.store_file,
        fetch_file=spy.fetch_file, max_bytes=spy.max_bytes,
        session_user_key=spy.session_user_key,
    ))


def test_the_stored_file_gets_a_connection_it_can_actually_use(spy):
    """저장 대역이 넘겨받은 커넥션을 **실제로 써도** 성공해야 한다.

    저장은 별도 실행 흐름에서 도는데 커넥션을 요청 쪽에서 열어 넘기면 sqlite3가
    거절한다. 클라우드의 저장 함수는 첫 줄에서 회원 장부를 읽기 때문에 이 결함이
    운영에서 파일 올리기 전부를 502로 만들었다. 대역이 커넥션을 안 건드리면
    시험은 통과하고 운영만 죽는다 — 그래서 여기서 일부러 건드린다.
    """
    used = []

    def _store(conn, user_key, name, content, meta, via):
        used.append(conn.execute("SELECT 1").fetchone()[0])
        return {"id": "01AAA", "path": name, "bytes": len(content), "status": "올림"}

    spy.store_file = _store
    client = _client_for(spy)
    t = _ticket(spy)

    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("x", b"ab")},
                    headers=JSON)

    assert r.status_code == 200, r.text
    assert used == [1]


def test_the_fetched_file_gets_a_connection_it_can_actually_use(spy):
    """받기도 같은 자리·같은 이유다."""
    used = []

    def _fetch(conn, user_key, name):
        used.append(conn.execute("SELECT 1").fetchone()[0])
        return b"PDFBYTES"

    spy.fetch_file = _fetch
    client = _client_for(spy)
    t = _ticket(spy, kind=tickets.KIND_DOWNLOAD)

    r = client.get(f"/d/{t['ticket_id']}")

    assert r.status_code == 200, r.text
    assert r.content == b"PDFBYTES"
    assert used == [1]
