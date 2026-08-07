"""티켓 주소 세 개 — `GET /u/<티켓>` · `POST /u/<티켓>` · `GET /d/<티켓>`.

파일 몸통이 붙은 AI의 출력을 거치지 않고 오가는 길이다. 왜 그 길이 필요한지는
`tickets.py` 첫머리에 있다.

## 한 주소가 두 사람을 받는다

`POST /u/<티켓>`에는 두 종류가 들어온다 — 회원의 브라우저가 보내는 폼과, AI가
자기 작업공간에서 던지는 `curl -F file=@...`이다. **서버는 둘을 구분하지 않고
구분해서도 안 된다.** 같은 티켓, 같은 처리다. 구분하는 순간 "AI가 막혔을 때
회원이 같은 링크로 이어 올린다"는 흐름(설계서 7절)이 성립하지 않는다.

## 누구를 들여보내나

- 웹 로그인 세션이 **있는데 티켓 주인이 아니면 거절한다.**
- 세션이 **없으면 티켓 번호 자체를 인증으로 인정한다** — `curl`에는 쿠키가 없기
  때문이다(설계서 5-4절). 티켓 번호는 256비트 난수이고 올리기는 한 번 쓰면 닫히며
  두 시간이면 만료된다.

두 번째 줄은 완화이지 무결점이 아니다. 티켓 번호를 손에 넣은 사람은 쿠키를 빼고
보내면 들어올 수 있다 — 그래서 번호를 로그에 통째로 남기지 않고(`tickets.short`)
만료를 짧게 잡는다. 이 맞바꿈은 설계서 5-4절에서 명시적으로 받아들인 것이다.

개인 주소(이 PC의 나무 서버)에는 웹 로그인 자체가 없다. 그쪽은 세션 판정이 항상
"없음"이라 두 번째 줄만 남는다 — 애초에 회원 한 사람의 서버이므로 가릴 남이 없다.

## 이 서버에 파일을 남기지 않는다

받은 파일은 저장소로 보낸 뒤 그 요청 안에서 사라진다. Starlette의 multipart
해석기가 큰 파일을 잠시 임시 파일로 흘릴 수는 있는데, 그 임시 파일은 응답 전에
`form.close()`로 닫혀 지워진다 — 이 모듈이 **따로 사본을 쓰는 곳은 없다.**

## 왜 필요한 것을 전부 인자로 받나

이 파일은 개인 주소와 나무 클라우드가 **같이 쓴다.** 그런데 파일을 실제로 저장하는
방법은 둘이 다르다 — 개인 주소는 `~/.namu`의 git을 직접 쓰고, 클라우드는 GitHub
API로 남의 저장소에 쓴다. 화면 껍데기도, 로그인 여부를 아는 방법도 다르다.
그 다른 것들을 전부 인자로 받으면 **길(주소·검증·실패 처리)은 한 벌**로 남는다.
베껴 두 벌로 만들면 한쪽만 고쳐지는 날이 오고, 그 한쪽은 파일이 오가는 문이다.
"""
from __future__ import annotations

import html
import logging
from contextlib import closing
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

import tickets

logger = logging.getLogger("namu.ticket_web")

# 이 앱이 여는 주소의 앞자락. 요청을 가르는 쪽이 같은 값을 봐야 하므로 여기 한
# 곳에 둔다 — 두 벌로 늘리면 한쪽만 고쳐져 문이 안 열리거나, 반대로 인증이 걸린
# 쪽으로 새는 자리가 생긴다.
UPLOAD_PREFIX = "/u/"
DOWNLOAD_PREFIX = "/d/"

# 회원이 한 사람뿐인 개인 주소가 티켓 주인 자리에 적는 값. 클라우드는 실제 회원
# 키를 적는다.
LOCAL_USER = "local"


def _plain_page(title: str, body_html: str) -> str:
    """화면 껍데기 기본값 — 바깥에서 안 주면 이것을 쓴다.

    개인 주소에는 홈페이지가 없어 얹을 껍데기도 없다. 그래도 이 화면은 회원이
    눈으로 보는 자리이므로, 글자만 덜렁 내놓지 않고 읽을 수 있는 최소한을 갖춘다.
    바깥 CSS를 부르지 않는다(개인 서버가 인터넷 없이 뜰 수 있어야 한다).
    """
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{max-width:680px;margin:40px auto;padding:0 20px;"
        "font-family:system-ui,-apple-system,'Segoe UI',sans-serif;"
        "line-height:1.65;color:#1f2328;}"
        "h1{font-size:1.5rem;margin:0 0 16px;}"
        ".muted{color:#6b7280;}</style></head>"
        f"<body>{body_html}</body></html>"
    )


def _no_session(_request: Request) -> "str | None":
    """로그인 판정 기본값 — 개인 주소에는 웹 로그인이 없다."""
    return None


class _Hooks:
    """이 앱이 바깥에서 받아야 하는 것들(위 모듈 설명의 마지막 절 참고)."""

    def __init__(
        self, *, open_conn, store_file, fetch_file, max_bytes,
        session_user_key=None, render_page=None,
    ):
        self.open_conn = open_conn
        self.store_file = store_file
        self.fetch_file = fetch_file
        self.max_bytes = max_bytes
        self.session_user_key = session_user_key or _no_session
        self.render_page = render_page or _plain_page


# ---------------------------------------------------------------------------
# 들여보낼지 판정
# ---------------------------------------------------------------------------
def _owner_mismatch(hooks: _Hooks, request: Request, ticket: dict) -> bool:
    """로그인한 사람이 있는데 그 사람이 티켓 주인이 아니면 참.

    로그인 자체가 없으면 거짓이다(= 통과). 세션이 없다는 것은 `curl`이거나 이
    브라우저로는 아직 로그인하지 않은 회원이라는 뜻이고, 그 둘을 서버가 구분할
    방법이 없다 — 위 모듈 설명의 맞바꿈 그대로다.
    """
    session_key = hooks.session_user_key(request)
    return bool(session_key) and session_key != ticket.get("user_key")


def _wants_json(request: Request) -> bool:
    """`curl`처럼 화면이 필요 없는 쪽인지. 브라우저 주소창은 이 헤더를 달고 온다."""
    return "text/html" not in (request.headers.get("accept") or "").lower()


def _fail(
    hooks: _Hooks, request: Request, status: int, title: str, detail: str
) -> Response:
    """실패 한 건 — 부르는 쪽이 브라우저면 화면으로, curl이면 JSON으로.

    티켓 번호를 메시지에 싣지 않는다(위 모듈 설명 참고).
    """
    if _wants_json(request):
        return JSONResponse({"error": title, "detail": detail}, status_code=status)
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f'<p role="status" style="border-left:5px solid #b00020;'
        'background:rgba(176,0,32,0.12);padding:12px 14px;margin:16px 0;'
        f'border-radius:0 6px 6px 0;">{html.escape(detail)}</p>'
    )
    return HTMLResponse(hooks.render_page(title, body), status_code=status)


def _load_or_fail(
    hooks: _Hooks, request: Request, conn, ticket_id: str, kind: str
) -> "tuple[dict | None, Response | None]":
    """티켓을 꺼내 쓸 수 있는 상태인지까지 판정한다. (티켓, 실패응답) 중 하나만 찬다."""
    ticket = tickets.get(conn, ticket_id)
    if ticket is None or ticket.get("kind") != kind:
        # 종류가 다른 티켓도 "없음"으로 답한다 — 있고 없고를 알려 주면 번호를
        # 넣어 보는 쪽에 정보를 주게 된다.
        return None, _fail(
            hooks, request, 404, "없는 링크입니다",
            "이 주소에 해당하는 링크가 없습니다. 링크를 다시 받아 주세요.",
        )
    if _owner_mismatch(hooks, request, ticket):
        return None, _fail(
            hooks, request, 403, "다른 분의 링크입니다",
            "지금 로그인한 계정은 이 링크의 주인이 아닙니다.",
        )
    status = tickets.status_of(ticket)
    if status == tickets.STATUS_EXPIRED:
        return None, _fail(
            hooks, request, 410, "만료된 링크입니다",
            "이 링크는 유효 시간이 지났습니다. 새 링크를 받아 주세요.",
        )
    if kind == tickets.KIND_UPLOAD and status == tickets.STATUS_DONE:
        return None, _fail(
            hooks, request, 409, "이미 쓴 링크입니다",
            "이 링크로는 이미 파일이 올라갔습니다. 다시 올리려면 새 링크를 받아 주세요.",
        )
    return ticket, None


# ---------------------------------------------------------------------------
# 올리기 화면
# ---------------------------------------------------------------------------
def _upload_page_html(hooks: _Hooks, ticket: dict) -> str:
    """파일을 끌어다 놓는 화면.

    진행률을 위해 `fetch`가 아니라 `XMLHttpRequest`를 쓴다 — fetch는 **보내는**
    쪽 진행 상황을 알려주지 않아서, 큰 파일을 올릴 때 화면이 멈춘 것처럼 보인다.
    이 화면이 존재하는 이유가 바로 "큰 파일"이므로 그 표시를 포기할 수 없다.
    """
    name = html.escape(ticket.get("name") or "")
    meta = ticket.get("meta") or {}
    summary = html.escape((meta.get("summary") or "").strip())
    limit_mb = hooks.max_bytes() / (1024 * 1024)
    summary_html = f'<p class="muted">{summary}</p>' if summary else ""
    body = f"""
<h1>파일 올리기</h1>
<p>아래 이름으로 <b>내 저장소</b>에 보관됩니다.</p>
<p style="font-size:1.15rem;"><b>{name}</b></p>
{summary_html}
<div id="drop" tabindex="0" role="button"
     style="border:2px dashed #9aa4b2;border-radius:10px;padding:36px 18px;
            text-align:center;cursor:pointer;margin:20px 0;">
  <p style="margin:0 0 8px;font-size:1.05rem;"><b>여기에 파일을 끌어다 놓으세요</b></p>
  <p style="margin:0;" class="muted">또는 눌러서 고르기 · 한 번에 한 개 ·
     최대 {limit_mb:.0f}MB</p>
  <input id="pick" type="file" style="display:none">
</div>
<div id="bar-box" style="display:none;margin:16px 0;">
  <div style="background:#e5e7eb;border-radius:999px;height:12px;overflow:hidden;">
    <div id="bar" style="background:#2a6fdb;height:100%;width:0%;
                         transition:width .15s;"></div>
  </div>
  <p id="bar-text" class="muted" style="margin:8px 0 0;">보내는 중… 0%</p>
</div>
<div id="result"></div>
<script>
(function () {{
  var drop = document.getElementById('drop');
  var pick = document.getElementById('pick');
  var barBox = document.getElementById('bar-box');
  var bar = document.getElementById('bar');
  var barText = document.getElementById('bar-text');
  var result = document.getElementById('result');
  var busy = false;

  function say(htmlText, tone) {{
    var color = tone === 'bad' ? '#b00020' : '#1a7f37';
    var tint = tone === 'bad' ? 'rgba(176,0,32,0.12)' : 'rgba(26,127,55,0.12)';
    result.innerHTML = '<p role="status" style="border-left:5px solid ' + color +
      ';background:' + tint + ';padding:12px 14px;margin:16px 0;' +
      'border-radius:0 6px 6px 0;">' + htmlText + '</p>';
  }}

  function fmt(n) {{
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }}

  function send(file) {{
    if (busy || !file) return;
    busy = true;
    result.innerHTML = '';
    barBox.style.display = 'block';
    bar.style.width = '0%';
    barText.textContent = '보내는 중… 0%';

    var form = new FormData();
    form.append('file', file, file.name);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', window.location.pathname);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = function (e) {{
      if (!e.lengthComputable) return;
      var pct = Math.round((e.loaded / e.total) * 100);
      bar.style.width = pct + '%';
      barText.textContent = pct < 100
        ? '보내는 중… ' + pct + '%'
        : '저장소에 넣는 중… 잠시만요';
    }};
    xhr.onload = function () {{
      busy = false;
      var data = {{}};
      try {{ data = JSON.parse(xhr.responseText); }} catch (err) {{ }}
      if (xhr.status >= 200 && xhr.status < 300) {{
        bar.style.width = '100%';
        barText.textContent = '끝났습니다';
        var isNew = data.status === '새 판';
        say('<b>' + (isNew ? '새 판으로 저장했습니다.' : '저장했습니다.') +
            '</b><br>' + (data.path || '') + ' · ' + fmt(data.bytes || 0) +
            '<br><span style="color:#555">이 창은 닫으셔도 됩니다.</span>', 'good');
        drop.style.display = 'none';
      }} else {{
        barBox.style.display = 'none';
        say('<b>' + (data.error || '올리지 못했습니다') + '</b><br>' +
            (data.detail || ''), 'bad');
      }}
    }};
    xhr.onerror = function () {{
      busy = false;
      barBox.style.display = 'none';
      say('<b>연결이 끊겼습니다</b><br>잠시 뒤 다시 시도해 주세요.', 'bad');
    }};
    xhr.send(form);
  }}

  drop.addEventListener('click', function () {{ pick.click(); }});
  drop.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); pick.click(); }}
  }});
  pick.addEventListener('change', function () {{ send(pick.files[0]); }});
  ['dragenter', 'dragover'].forEach(function (name) {{
    drop.addEventListener(name, function (e) {{
      e.preventDefault();
      drop.style.borderColor = '#2a6fdb';
    }});
  }});
  ['dragleave', 'drop'].forEach(function (name) {{
    drop.addEventListener(name, function (e) {{
      e.preventDefault();
      drop.style.borderColor = '#9aa4b2';
    }});
  }});
  drop.addEventListener('drop', function (e) {{
    if (e.dataTransfer && e.dataTransfer.files.length) send(e.dataTransfer.files[0]);
  }});
}})();
</script>
"""
    return hooks.render_page("파일 올리기", body)


def _build_upload_get(hooks: _Hooks):
    async def upload_page(request: Request) -> Response:
        ticket_id = request.path_params["ticket_id"]
        with closing(hooks.open_conn()) as conn:
            ticket, failure = _load_or_fail(
                hooks, request, conn, ticket_id, tickets.KIND_UPLOAD
            )
        if failure is not None:
            return failure
        return HTMLResponse(_upload_page_html(hooks, ticket))

    return upload_page


def _build_upload_post(hooks: _Hooks):
    async def upload_receive(request: Request) -> Response:
        ticket_id = request.path_params["ticket_id"]
        with closing(hooks.open_conn()) as conn:
            ticket, failure = _load_or_fail(
                hooks, request, conn, ticket_id, tickets.KIND_UPLOAD
            )
            if failure is not None:
                return failure

            form = await request.form()
            try:
                upload = form.get("file")
                if upload is None or not hasattr(upload, "read"):
                    return _fail(
                        hooks, request, 400, "파일이 없습니다",
                        "보낼 파일 한 개를 'file' 칸에 담아 주세요.",
                    )
                content = await upload.read()
            finally:
                # 해석기가 임시로 흘려 둔 것을 여기서 지운다(위 모듈 설명 참고).
                await form.close()

            limit = hooks.max_bytes()
            if len(content) > limit:
                return _fail(
                    hooks, request, 413, "파일이 너무 큽니다",
                    f"{len(content):,}바이트를 받았지만 지금 상한은 "
                    f"{limit:,}바이트입니다.",
                )
            if not content:
                return _fail(
                    hooks, request, 400, "빈 파일입니다",
                    "내용이 없는 파일은 올리지 않습니다.",
                )

            meta = dict(ticket.get("meta") or {})
            via = meta.pop("via", None)
            try:
                # 저장은 git·네트워크를 쓰는 동기 작업이다. 그대로 부르면 그 몇
                # 초 동안 서버가 다른 요청을 하나도 못 받는다.
                result = await run_in_threadpool(
                    hooks.store_file, conn, ticket["user_key"], ticket["name"],
                    content, meta, via,
                )
            except Exception as exc:
                # **티켓을 닫지 않는다**(설계서 7절). 실패한 시도로 링크를 태우면
                # 회원이 브라우저로 이어 올릴 길이 함께 끊긴다.
                logger.warning(
                    "티켓(%s) 파일 저장 실패 — 티켓은 살려 둡니다: %s",
                    tickets.short(ticket_id), exc,
                )
                return _fail(hooks, request, 502, "저장하지 못했습니다", str(exc))

            tickets.mark_used(conn, ticket_id, result)

        logger.info(
            "티켓(%s)으로 파일을 받았습니다: %s (%s바이트)",
            tickets.short(ticket_id), result.get("path"), result.get("bytes"),
        )
        return JSONResponse(result)

    return upload_receive


# ---------------------------------------------------------------------------
# 받기
# ---------------------------------------------------------------------------
def content_disposition(name: str) -> str:
    """`Content-Disposition` 한 줄. 한글 이름 때문에 두 벌로 적는다.

    `filename=`은 ASCII만 실을 수 있어 한글이 깨진다. 그래서 옛 브라우저용
    ASCII 대체 이름과, RFC 5987 형식(`filename*=UTF-8''…`)을 함께 적는다 —
    둘 다 이해하는 브라우저는 뒤엣것을 쓴다.
    """
    tail = (name or "file").rsplit("/", 1)[-1]
    ascii_fallback = tail.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(tail, safe='')}"
    )


def _build_download_get(hooks: _Hooks):
    async def download_file(request: Request) -> Response:
        ticket_id = request.path_params["ticket_id"]
        with closing(hooks.open_conn()) as conn:
            ticket, failure = _load_or_fail(
                hooks, request, conn, ticket_id, tickets.KIND_DOWNLOAD
            )
            if failure is not None:
                return failure
            try:
                content = await run_in_threadpool(
                    hooks.fetch_file, conn, ticket["user_key"], ticket["name"]
                )
            except Exception as exc:
                logger.warning(
                    "티켓(%s) 파일 받기 실패: %s", tickets.short(ticket_id), exc
                )
                return _fail(
                    hooks, request, 502, "파일을 가져오지 못했습니다", str(exc)
                )

        # 받기는 **표시를 남기지 않는다.** 링크는 만료될 때까지 유효하다 —
        # 회원이 한 번 더 누르는 것이 정상이고, 첫 클릭에 링크를 닫으면 고장으로
        # 보인다. 서버는 애초에 회원이 실제로 파일을 손에 넣었는지 알 수 없으므로
        # '받았음' 표시는 어차피 반쪽이다(2026-08-07 방침 그대로).
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": content_disposition(ticket["name"]),
                "Content-Length": str(len(content)),
                # 회원의 사적 파일이 중간 캐시에 남지 않게 한다.
                "Cache-Control": "private, no-store",
            },
        )

    return download_file


# ---------------------------------------------------------------------------
# 앱 만들기 / 요청 가르기
# ---------------------------------------------------------------------------
def is_ticket_path(path: str) -> bool:
    """이 주소를 티켓 앱이 받아야 하는가.

    요청을 가르는 쪽(개인 주소의 `http_server`, 클라우드의 갈림길)이 **이 함수
    하나**를 본다 — 앞자락을 각자 적으면 한쪽만 고쳐지는 날이 온다.
    """
    return path.startswith(UPLOAD_PREFIX) or path.startswith(DOWNLOAD_PREFIX)


def build_ticket_app(
    *, open_conn, store_file, fetch_file, max_bytes,
    session_user_key=None, render_page=None,
) -> Starlette:
    """티켓 주소 세 개를 담은 Starlette 앱. 인자의 뜻은 모듈 설명 마지막 절 참고."""
    hooks = _Hooks(
        open_conn=open_conn, store_file=store_file, fetch_file=fetch_file,
        max_bytes=max_bytes, session_user_key=session_user_key,
        render_page=render_page,
    )
    return Starlette(routes=[
        Route(UPLOAD_PREFIX + "{ticket_id}", _build_upload_get(hooks),
              methods=["GET"]),
        Route(UPLOAD_PREFIX + "{ticket_id}", _build_upload_post(hooks),
              methods=["POST"]),
        Route(DOWNLOAD_PREFIX + "{ticket_id}", _build_download_get(hooks),
              methods=["GET"]),
    ])


class TicketOrAppDispatcher:
    """티켓 주소는 티켓 앱으로, 나머지는 원래 앱으로 보내는 순수 ASGI 콜러블.

    티켓 앱이 **인증 미들웨어 바깥**에 서야 한다 — 브라우저에는 토큰이 없고,
    티켓 번호 자체가 그 자리의 인증이기 때문이다(모듈 설명 참고).

    잘못 분류돼도 인증이 걸린 쪽으로는 새지 않는다: `/u/…`로 시작하지 않는 모든
    요청은 종전대로 원래 앱(=인증 미들웨어)으로 가고, 반대로 티켓 앱에는 MCP
    라우트가 애초에 없어 그리로 잘못 간 요청은 404가 될 뿐이다.
    """

    def __init__(self, app, ticket_app):
        self.app = app
        self.ticket_app = ticket_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and is_ticket_path(scope.get("path", "")):
            await self.ticket_app(scope, receive, send)
            return
        await self.app(scope, receive, send)
