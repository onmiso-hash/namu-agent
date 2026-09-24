"""티켓 주소의 보안·1회용 회귀 검사(2026-09 검수 C-4, C-5, C-6).

검수 재현(test_repro_ticket_web.py)을 뒤집었다.
- 올리기 화면이 응답 JSON의 path·detail을 HTML 문자열로 끼워 넣어(저장된 XSS) 파일
  이름에 든 태그가 실행될 수 있었다 → 이제 결과 칸은 textContent로만 그린다.
- 같은 링크로 동시에 두 번 보내면 둘 다 200이었다 → 조건부 UPDATE로 선점한다.
- 20MiB 상한을 몸통을 다 읽은 뒤에야 봤다 → Content-Length로 먼저 거절한다.
- 받기 헤더의 ASCII 대체 이름에 줄바꿈·따옴표가 그대로 실렸다 → `_`로 바꾼다.
"""
import threading
import time

from starlette.testclient import TestClient

import ticket_web
import tickets

JSON = {"accept": "application/json"}
HTML = {"accept": "text/html"}


def _app(db, store, *, limit=20 * 1024 * 1024, fetch=lambda c, u, n: b"x"):
    return ticket_web.build_ticket_app(
        open_conn=lambda: tickets.connect(db), store_file=store,
        fetch_file=fetch, max_bytes=lambda: limit,
    )


def _ok_store(c, u, n, content, meta, via):
    return {"id": "1", "path": n, "bytes": len(content), "status": "올림"}


def _upload_ticket(db, name="attach_file/a.txt"):
    with tickets.connect(db) as c:
        return tickets.create(c, "local", tickets.KIND_UPLOAD, name, {"summary": "s"})


def test_upload_page_never_builds_html_from_response_json(tmp_path):
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    page = TestClient(_app(db, _ok_store)).get(f"/u/{t['ticket_id']}", headers=HTML).text
    assert "innerHTML" not in page
    assert "insertAdjacentHTML" not in page and "outerHTML" not in page
    assert "textContent = line.text" in page
    # 응답에서 온 값이 문자열 이어 붙이기로 HTML에 끼어드는 옛 모양이 없다
    assert "'</b><br>' + (data.path" not in page
    assert "'</b><br>' + (data.detail" not in page


def test_concurrent_posts_on_one_link_only_one_wins(tmp_path):
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    calls = []

    def slow_store(c, u, n, content, meta, via):
        calls.append(content)
        time.sleep(0.4)
        return {"id": str(len(calls)), "path": n, "bytes": len(content), "status": "올림"}

    client = TestClient(_app(db, slow_store))
    codes = []

    def post(body):
        codes.append(client.post(
            f"/u/{t['ticket_id']}", files={"file": ("a", body)}, headers=JSON,
        ).status_code)

    ths = [threading.Thread(target=post, args=(b,)) for b in (b"one", b"two")]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    assert sorted(codes) == [200, 409], codes
    assert len(calls) == 1
    with tickets.connect(db) as c:
        assert tickets.status_of(tickets.get(c, t["ticket_id"])) == tickets.STATUS_DONE


def test_failed_store_releases_the_claim_so_the_link_still_works(tmp_path):
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    state = {"fail": True}

    def flaky(c, u, n, content, meta, via):
        if state["fail"]:
            raise RuntimeError("GitHub 불통")
        return _ok_store(c, u, n, content, meta, via)

    client = TestClient(_app(db, flaky))
    r1 = client.post(f"/u/{t['ticket_id']}", files={"file": ("a", b"hi")}, headers=JSON)
    assert r1.status_code == 502
    with tickets.connect(db) as c:
        assert tickets.status_of(tickets.get(c, t["ticket_id"])) == tickets.STATUS_WAITING
    state["fail"] = False
    r2 = client.post(f"/u/{t['ticket_id']}", files={"file": ("a", b"hi")}, headers=JSON)
    assert r2.status_code == 200


def test_claim_is_atomic_and_in_progress_is_not_reported_done(tmp_path):
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    with tickets.connect(db) as c:
        assert tickets.claim(c, t["ticket_id"]) is True
        assert tickets.claim(c, t["ticket_id"]) is False
        # 선점만 된 상태는 '완료'가 아니다(namu_check_ticket이 "올라갔다"로 읽으면 안 된다)
        assert tickets.status_of(tickets.get(c, t["ticket_id"])) == tickets.STATUS_WAITING
        tickets.mark_used(c, t["ticket_id"], {"path": "attach_file/a.txt"})
        tickets.release_claim(c, t["ticket_id"])  # 이미 쓴 티켓은 풀리지 않는다
        assert tickets.status_of(tickets.get(c, t["ticket_id"])) == tickets.STATUS_DONE
        # 내려받기 티켓은 선점 대상이 아니다
        d = tickets.create(c, "local", tickets.KIND_DOWNLOAD, "attach_file/a.txt", {})
        assert tickets.claim(c, d["ticket_id"]) is False


def test_oversized_upload_is_refused_from_content_length_before_reading(tmp_path):
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    stored = []

    def store(c, u, n, content, meta, via):
        stored.append(content)
        return _ok_store(c, u, n, content, meta, via)

    client = TestClient(_app(db, store, limit=1024))
    body = b"x" * (ticket_web._MULTIPART_SLACK_BYTES + 10 * 1024)
    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("a", body)}, headers=JSON)
    assert r.status_code == 413
    assert "보내려 했지만" in r.json()["detail"]  # 읽기 전 판정 쪽 문구
    assert stored == []
    # 링크는 타지 않는다
    with tickets.connect(db) as c:
        assert tickets.get(c, t["ticket_id"])["used_at"] is None


def test_small_file_just_over_limit_is_still_caught_after_reading(tmp_path):
    """Content-Length 여유(경계·머리글 몫) 안쪽에서 상한을 넘는 파일은 읽은 뒤 검사가 잡는다."""
    db = tmp_path / "t.db"
    t = _upload_ticket(db)
    client = TestClient(_app(db, _ok_store, limit=10))
    r = client.post(f"/u/{t['ticket_id']}", files={"file": ("a", b"x" * 100)}, headers=JSON)
    assert r.status_code == 413


def test_content_disposition_has_no_raw_control_chars_or_quotes():
    cd = ticket_web.content_disposition('attach_file/a\r\nX-Evil: 1"\\.txt')
    assert "\r" not in cd and "\n" not in cd
    fallback = cd.split('filename="', 1)[1].split('"; filename*=', 1)[0]
    assert '"' not in fallback and "\\" not in fallback
    assert "filename*=UTF-8''a%0D%0AX-Evil%3A%201%22%5C.txt" in cd


def test_download_with_legacy_newline_name_does_not_split_headers(tmp_path):
    """이름 검사 전에 저장소에 들어간 옛 이름도 헤더를 쪼개지 못한다."""
    db = tmp_path / "t.db"
    with tickets.connect(db) as c:
        t = tickets.create(c, "local", tickets.KIND_DOWNLOAD, "attach_file/a\r\nX-Evil: 1.txt", {})
    r = TestClient(_app(db, None)).get(f"/d/{t['ticket_id']}")
    assert r.status_code == 200
    assert "x-evil" not in {k.lower() for k in r.headers.keys()}
