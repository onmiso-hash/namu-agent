# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp[cli]>=1.28,<2", "python-ulid>=3.0.0", "PyYAML>=6.0", "python-dotenv>=1.0.0"]
# ///
"""NAMU 원격 MCP HTTP 서버 (namu-44, docs/remote_mcp_design.md v4 확정안).

목적: claude.ai(웹) Custom Connector 등 원격 클라이언트가 Streamable HTTP로
namu_recall/namu_record/namu_search 3종 도구를 쓸 수 있게 한다. 기존 stdio 진입점
(mcp_server.py)은 절대 건드리지 않는다 — 이 파일은 mcp_server.mcp(FastMCP 인스턴스)를
그대로 재사용하는 얇은 래퍼일 뿐이다(도구 정의 이중 구현 0).

환경변수 (namu-plugin/config.py의 http_settings() 참조):
  NAMU_HTTP_TOKEN           헤더 인증 토큰 (x-api-key 또는 Authorization: Bearer)
  NAMU_HTTP_PATH_SECRET     시크릿 URL 경로 세그먼트 (/mcp/<secret>로 노출)
  NAMU_HTTP_HOST            바인드 호스트 (기본 127.0.0.1)
  NAMU_HTTP_PORT            바인드 포트 (기본 8765)
  NAMU_HTTP_PULL_INTERVAL   디바운스 pull 간격 초 (기본 60.0, 0=매 요청)
  NAMU_HTTP_ALLOW_NOAUTH    "1"이면 무인증 기동 허용 (로컬 테스트 전용, 공개 노출 금지)
  NAMU_HTTP_ALLOWED_HOSTS   터널 경유 Host 헤더 허용 목록, 쉼표 구분 (미설정 시 FastMCP
                            자동 기본값 그대로 — 127.0.0.1/localhost/[::1]만 허용, 터널
                            도메인은 421로 거부됨). "*"이면 DNS rebinding 보호 자체를
                            비활성화(공개 배포에서 도메인이 유동적일 때 opt-out — 인증은
                            토큰/시크릿 경로가 별도로 담당)

기동 예시 (로컬 무인증 테스트):
  NAMU_HTTP_ALLOW_NOAUTH=1 NAMU_HTTP_PORT=18765 uv run --script namu-plugin/http_server.py

기동 예시 (토큰 헤더 인증, 자기 PC + 터널):
  NAMU_HTTP_TOKEN=<임의의 강한 문자열> uv run --script namu-plugin/http_server.py

테스트 격리를 위해 mcp_server import는 build_app()/main() 내부로 지연한다 — mcp_server는
import 시점에 실제 ~/.namu를 만지므로(_ensure_db 등), 순수 로직(설정 검증·인증·디바운스
미들웨어) 테스트는 mcp_server를 import하지 않고도 동작해야 한다.
"""
import asyncio
import hmac
import json
import logging
import threading
import time

import anyio
from mcp.server.transport_security import TransportSecuritySettings

import config as cfg
import memory_sync

logger = logging.getLogger("namu.http_server")

# 설계 §8: 웹(원격 HTTP)에는 learnings 3종만 노출한다. namu_sync_setup은 서버의 git
# remote를 재배선하는 도구라 원격 호출자에게 주면 보안 사고(remote 탈취)로 직결된다
# — stdio(로컬 CC/agy)에서는 그대로 쓸 수 있어야 하므로 mcp_server.py 자체에서
# 빼지 않고, http_server가 import한 인스턴스에서만 build_app()이 제거한다.
HTTP_EXPOSED_TOOLS = frozenset({"namu_recall", "namu_record", "namu_search"})

# 디바운스 pull 상태 — 모듈 전역 1개(단일 프로세스 전제, 경로 B 셀프호스팅 스코프와 합치).
# threading.Lock으로 보호: uvicorn 워커 스레드/anyio 스레드 풀에서 동시에 갱신될 수 있음.
_last_pull_lock = threading.Lock()
_last_pull = 0.0  # time.monotonic() 기준. 0.0은 "아직 한 번도 안 당김"을 뜻하는 초기값.


def validate_settings(s: dict) -> None:
    """무인증 공개 노출을 막는다 (v4 §5). token·path_secret 둘 다 비어 있고
    allow_noauth도 아니면 기동 자체를 거부한다 — 값 자체는 절대 출력하지 않는다."""
    if s["allow_noauth"]:
        return
    if s["token"] or s["path_secret"]:
        return
    print(
        "[namu-http] 기동 거부: 인증 설정이 하나도 없습니다.\n"
        "  다음 중 하나 이상을 환경변수로 설정하세요:\n"
        "    NAMU_HTTP_TOKEN=<임의의 강한 토큰 문자열>   (헤더 인증, x-api-key / Authorization: Bearer)\n"
        "    NAMU_HTTP_PATH_SECRET=<임의의 경로 문자열>  (시크릿 URL 경로, /mcp/<secret>)\n"
        "  로컬 테스트 목적으로만 무인증 기동을 허용하려면 NAMU_HTTP_ALLOW_NOAUTH=1을 설정하세요\n"
        "  (공개 인터넷에 노출하는 배포에서는 절대 사용하지 마세요).",
    )
    raise SystemExit(2)


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthMiddleware:
    """토큰 헤더 검증 (v4 §5 ①). 순수 ASGI 3-인자 callable — starlette 미들웨어
    베이스클래스에 의존하지 않아 mcp_server import 없이도 단위 테스트 가능하다.

    token이 비어 있으면(시크릿 경로만 쓰는 구성) 무조건 통과시킨다 — 경로 검증은
    build_app()에서 streamable_http_path 자체를 바꿔 처리하므로 여기서는 하지 않는다.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        api_key = headers.get(b"x-api-key", b"").decode("latin-1")
        auth_header = headers.get(b"authorization", b"").decode("latin-1")
        token_bytes = self.token.encode("utf-8")

        authorized = False
        if api_key and hmac.compare_digest(api_key.encode("utf-8"), token_bytes):
            authorized = True
        elif auth_header.startswith("Bearer "):
            candidate = auth_header[len("Bearer ") :]
            if hmac.compare_digest(candidate.encode("utf-8"), token_bytes):
                authorized = True

        if not authorized:
            client = scope.get("client")
            addr = f"{client[0]}:{client[1]}" if client else "unknown"
            # 조용한 실패 금지(namu-43 교훈) — 단 헤더 값 자체(토큰 후보)는 로그에 남기지 않는다.
            logger.warning("NAMU HTTP 인증 실패 (client=%s)", addr)
            await _send_json(send, 401, {"error": "unauthorized"})
            return

        await self.app(scope, receive, send)


async def _maybe_pull(pull_interval: float) -> None:
    """마지막 pull에서 pull_interval초가 지났으면 sync_pull()을 스레드에서 실행한다.
    갱신은 성공/실패 무관 — sync 비활성 환경(sync_enabled False)에서 sync_pull이 즉시
    False를 반환해도 매 요청 재시도하지 않게 하기 위함(v4 §6)."""
    global _last_pull

    now = time.monotonic()
    with _last_pull_lock:
        due = (now - _last_pull) >= pull_interval
        if due:
            _last_pull = now
    if not due:
        return

    try:
        # sync_pull 내부에서 sync_enabled 게이트·실패 로그(sync.log)를 이미 처리한다.
        # 여기서는 그 호출 자체가 http 요청 흐름을 절대 막지 않게만 감싼다.
        await anyio.to_thread.run_sync(memory_sync.sync_pull)
    except Exception as exc:  # pragma: no cover - sync_pull 자체가 무예외 설계라 방어선일 뿐
        logging.debug("디바운스 pull 중 예외(무해 처리): %s", exc)


class PullDebounceMiddleware:
    """도구 호출 전 디바운스 git pull (v4 §6). ASGI 3-인자 callable."""

    def __init__(self, app, pull_interval: float):
        self.app = app
        self.pull_interval = pull_interval

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            await _maybe_pull(self.pull_interval)
        await self.app(scope, receive, send)


def restrict_tools(mcp_instance, allowed: frozenset[str]) -> None:
    """mcp_instance에 등록된 도구 중 allowed에 없는 것을 전부 제거한다.

    mcp 1.28.1 SDK 소스 확인 결과 `FastMCP.remove_tool(name)`이 공개 API로 존재하고
    (server.py:435, 내부적으로 ToolManager.remove_tool에 위임 — 없는 이름을 넘기면
    ToolError로 실패해 "조용히 안 지워짐"이 성립하지 않는다), 현재 등록된 도구 이름
    목록도 공개 async 메서드 `list_tools()`로 얻을 수 있어 사설(private) `_tool_manager`
    딕셔너리를 직접 건드릴 필요가 없었다 — 애초 계획했던 "사설 API 의존 + 존재
    검증/RuntimeError" 폴백은 쓰지 않는다.

    build_app()이 호출되는 시점(uvicorn 이벤트루프 시작 전)에는 실행 중인 async 루프가
    없으므로 asyncio.run으로 list_tools()를 동기 호출한다.

    stdio 경로(mcp_server.py를 `python mcp_server.py`로 직접 기동하는 stdio 진입점)에는
    영향이 없다 — 이 함수는 http_server가 build_app() 안에서 import한 *같은 프로세스
    내* mcp_server.mcp 인스턴스에서만 도구를 제거하고, stdio 진입점은 이 함수를 호출하지
    않는다(별도 프로세스로 기동되므로 애초에 공유 상태도 없다).
    """
    current_tools = asyncio.run(mcp_instance.list_tools())
    for tool in current_tools:
        if tool.name not in allowed:
            mcp_instance.remove_tool(tool.name)


# FastMCP가 host in (127.0.0.1/localhost/::1)일 때 자동 적용하는 기본값
# (mcp/server/fastmcp/server.py:178-183, mcp 1.28.1 실측). 터널 경유 요청 허용을 위해
# NAMU_HTTP_ALLOWED_HOSTS를 넣더라도 로컬 curl 스모크가 계속 동작해야 하므로, 이 기본값을
# "대체"가 아니라 사용자 항목에 "합쳐서" 쓴다.
_LOCALHOST_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCALHOST_ALLOWED_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _build_transport_security(allowed_hosts: list[str]) -> TransportSecuritySettings | None:
    """NAMU_HTTP_ALLOWED_HOSTS(터널 경유 421 Misdirected Request 수정, namu-44 연장)로부터
    TransportSecuritySettings를 만든다.

    FastMCP는 streamable_http_app() 호출 시점에 self.settings.transport_security를 읽으므로
    (server.py:834,962 실측) build_app()에서 앱을 만들기 *전에* mcp_server.mcp.settings에
    설정해야 반영된다.

    - allowed_hosts == ["*"]: DNS rebinding 보호 자체를 끈다 — 공개 배포에서 접속 도메인이
      유동적일 때의 명시적 opt-out. 요청 인증은 기존 토큰/시크릿 경로 미들웨어가 별도로
      담당하므로 이 보호를 꺼도 무인증 노출이 되는 건 아니다.
    - 그 외 비어있지 않은 값: 보호는 유지한 채 FastMCP localhost 기본 3종에 사용자 항목을
      더한다(대체 금지 — 로컬 curl 스모크가 계속 동작해야 한다). allowed_origins는 FastMCP
      localhost 기본값 그대로 둔다(Origin 헤더는 부재 시 통과 — 서버-투-서버 호출에는
      영향 없음).
    - 빈 리스트(미설정): None을 반환해 FastMCP 자동 기본값을 그대로 둔다 — 현행 동작
      완전 보존.
    """
    if not allowed_hosts:
        return None
    if allowed_hosts == ["*"]:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_LOCALHOST_ALLOWED_HOSTS + allowed_hosts,
        allowed_origins=_LOCALHOST_ALLOWED_ORIGINS,
    )


def build_app(settings: dict):
    """FastMCP 인스턴스를 재사용해 Starlette ASGI 앱을 만들고 미들웨어로 감싼다.

    streamable_http_path/stateless_http는 FastMCP.streamable_http_app() 호출 시점에
    self.settings에서 읽힌다(mcp 1.28.1 SDK 소스 확인 — server.py의
    streamable_http_app()이 라우트를 만들 때마다 self.settings.streamable_http_path를
    참조하므로, 호출 *전에* 값을 바꾸면 그대로 반영된다). 별도 경로 rewrite 미들웨어
    같은 대안은 필요 없었다.
    """
    import mcp_server  # 지연 import: 여기서 실제 ~/.namu 부팅 로직(_ensure_db 등)이 실행됨

    restrict_tools(mcp_server.mcp, HTTP_EXPOSED_TOOLS)  # 설계 §8: sync_setup 등 원격 미노출

    if settings["path_secret"]:
        mcp_server.mcp.settings.streamable_http_path = f"/mcp/{settings['path_secret']}"
    # 원격 클라이언트(claude.ai)는 요청마다 새 세션일 수 있어 세션 고정을 강제하지
    # 않는 stateless 모드가 안전하다(v4 §4 스코프 — 단일 사용자 셀프호스팅 전제).
    mcp_server.mcp.settings.stateless_http = True

    # 터널 경유 421 Misdirected Request 수정 (v4 연장): FastMCP는 host가
    # 127.0.0.1/localhost/::1이면 DNS rebinding 보호를 자동 켜고 allowed_hosts를 localhost
    # 3종으로 제한한다 — 터널 도메인의 Host 헤더가 이 목록에 없어 거부된다. 앱 빌드
    # *전에* settings.transport_security를 갈아끼워야 반영된다(streamable_http_app()
    # 호출 시점에 읽힘).
    transport_security = _build_transport_security(settings.get("allowed_hosts", []))
    if transport_security is not None:
        mcp_server.mcp.settings.transport_security = transport_security
        if transport_security.enable_dns_rebinding_protection:
            logger.info(
                "namu-http: allowed_hosts 확장 적용 (localhost 기본 3종 + 사용자 %d개)",
                len(settings.get("allowed_hosts", [])),
            )
        else:
            logger.info("namu-http: DNS rebinding 보호 비활성화 (NAMU_HTTP_ALLOWED_HOSTS=*)")

    app = mcp_server.mcp.streamable_http_app()
    app = PullDebounceMiddleware(app, settings["pull_interval"])
    app = AuthMiddleware(app, settings["token"])  # 인증 실패 시 pull까지 도달하지 않도록 가장 바깥
    return app


def _auth_description(settings: dict) -> str:
    modes = []
    if settings["token"]:
        modes.append("토큰 헤더")
    if settings["path_secret"]:
        modes.append("시크릿 경로")
    if modes:
        return "+".join(modes)
    return "무인증(NAMU_HTTP_ALLOW_NOAUTH=1, 로컬 테스트 전용)"


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = cfg.http_settings()
    validate_settings(settings)
    app = build_app(settings)

    mcp_path = "/mcp/***" if settings["path_secret"] else "/mcp"
    logger.info(
        "namu-http 기동: auth=%s path=%s bind=%s:%s machine=%s data_root=%s",
        _auth_description(settings),
        mcp_path,
        settings["host"],
        settings["port"],
        cfg.NAMU_MACHINE,
        cfg.NAMU_DATA_ROOT,
    )

    import uvicorn

    uvicorn.run(app, host=settings["host"], port=settings["port"])


if __name__ == "__main__":
    main()
