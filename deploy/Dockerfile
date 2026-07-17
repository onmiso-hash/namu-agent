# NAMU 원격 MCP 클라우드 셀프호스팅 이미지 (namu-45, docs/remote_mcp_design.md §7-2).
#
# 빌드 (repo 루트에서, 컨텍스트=repo 루트여야 namu-plugin/을 COPY할 수 있다):
#   docker build -f deploy/Dockerfile -t namu-remote-mcp .
#
# 실행 예:
#   docker run -p 8765:8765 \
#     -e NAMU_SYNC_REMOTE="https://x-access-token:<PAT>@github.com/<user>/<repo>.git" \
#     -e NAMU_HTTP_TOKEN="<임의의 강한 토큰>" \
#     namu-remote-mcp
FROM python:3.12-slim

# uv 공식 배포 이미지에서 바이너리만 복사한다(curl|sh 파이프보다 재현성/신뢰성이 높음).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# git: ~/.namu(교훈 저장소) clone/pull/push에 필요. ca-certificates: HTTPS(git/PyPI) 통신.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV HOME=/root
WORKDIR /app

# namu-plugin/*.py는 이 이미지에서도 무수정 원본 그대로 복사한다(namu-45 요구사항: 기존
# 코드 한 줄도 바꾸지 않음. http_server.py가 mcp_server.mcp를 재사용하므로 이 폴더
# 전체가 그대로 실행 단위다).
COPY namu-plugin/ ./namu-plugin/
COPY deploy/entrypoint.sh ./deploy/entrypoint.sh
COPY deploy/namu_cloud_sync_setup.py ./deploy/namu_cloud_sync_setup.py
RUN chmod +x ./deploy/entrypoint.sh

# 설계 §4: 컨테이너 배포 시 machine=web을 기본값으로 찍는다(NAMU_MACHINE 해석 규칙 —
# config.py _resolve_machine — 은 환경변수가 있으면 그 값을 그대로 쓰므로 배포 플랫폼
# 환경변수로 얼마든지 override 가능하다, 예: cloud-railway).
ENV NAMU_MACHINE=web

# 컨테이너는 0.0.0.0으로 바인드해야 플랫폼 리버스 프록시/로드밸런서가 도달할 수 있다
# (127.0.0.1 바인드는 컨테이너 내부 루프백만 수신 — 외부에서 절대 도달 불가).
ENV NAMU_HTTP_HOST=0.0.0.0
ENV NAMU_HTTP_PORT=8765

# --- DNS rebinding 실독 확정 결과 (namu-45, 소스 근거 포함) ---------------------------
# mcp SDK(mcp==1.28.1) 소스 실측:
#   mcp/server/fastmcp/server.py:161  FastMCP.__init__(..., host: str = "127.0.0.1", ...)
#   mcp/server/fastmcp/server.py:178  if transport_security is None and host in
#                                        ("127.0.0.1", "localhost", "::1"):
#   mcp/server/fastmcp/server.py:179-182  transport_security = TransportSecuritySettings(
#                                            enable_dns_rebinding_protection=True,
#                                            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"], ...)
# namu-plugin/mcp_server.py:18  `mcp = FastMCP("namu-memory")` — host 인자를 넘기지
#   않는다. 즉 위 178번 줄의 host는 항상 생성자 기본값 "127.0.0.1"이고, 이는 uvicorn이
#   실제로 바인드하는 주소(NAMU_HTTP_HOST=0.0.0.0, http_server.py의 uvicorn.run(host=...))
#   와 무관하다 — FastMCP 인스턴스 생성 시점에 이미 DNS rebinding 보호가 켜지고
#   allowed_hosts가 localhost 3종으로 고정된다.
# 결과: 컨테이너를 0.0.0.0으로 바인드해도 이 보호는 여전히 걸리며, 클라우드 플랫폼
#   도메인(예: Host: xxx.railway.app)의 요청은 421 Misdirected Request로 거부된다
#   (namu-44에서 터널 경유 요청에 실측된 것과 동일한 근본 원인).
# 결정: 플랫폼 도메인은 배포 시점(빌드 시점 아님)에야 발급되는 경우가 많아(Railway 등)
#   이미지 기본값으로는 특정 도메인을 미리 넣을 수 없다 — 따라서 기본값을 "*"로 두어
#   DNS rebinding 보호 자체를 비활성화한다(http_server.py의 _build_transport_security가
#   "*"를 이 의미로 이미 처리하도록 구현돼 있음, namu-44). 요청 인증은 이 보호와 무관하게
#   NAMU_HTTP_TOKEN/NAMU_HTTP_PATH_SECRET이 별도로 담당하므로 "*"로 둬도 무인증 공개
#   노출이 되지는 않는다(둘 다 비우면 http_server.py가 기동 자체를 거부 — validate_settings).
#   도메인을 미리 알고 있다면 배포 시 NAMU_HTTP_ALLOWED_HOSTS=your-domain.example.com
#   처럼 좁혀서 재정의하는 편이 더 방어적이다.
ENV NAMU_HTTP_ALLOWED_HOSTS=*

# NAMU_HTTP_TOKEN / NAMU_HTTP_PATH_SECRET / NAMU_SYNC_REMOTE는 의도적으로 기본값을
# 두지 않는다 — 시크릿이므로 이미지에 굽지 않고 배포 플랫폼 환경변수로만 주입한다.
# 미설정 시 http_server.py(NAMU_HTTP_TOKEN/PATH_SECRET)와 entrypoint.sh(NAMU_SYNC_REMOTE)
# 양쪽 다 조용히 넘어가지 않고 명확한 에러로 기동을 거부한다.

# NAMU_GIT_EMAIL / NAMU_GIT_NAME — 이미지 ENV 기본값을 의도적으로 두지 않는다(namu-45
# docker 실검증 갭 수정). 시크릿은 아니지만(git 커밋 author identity일 뿐), 기본값
# 계산이 런타임에만 확정되는 NAMU_MACHINE(예: `namu-${NAMU_MACHINE:-web}`)에 기대므로,
# 빌드 시점에 박히는 Dockerfile ENV로 넣으면 `docker run -e NAMU_MACHINE=...`로 override
# 해도 NAMU_GIT_NAME이 그 값을 못 따라간다(Docker ENV의 ${VAR} 치환은 빌드 시점 1회
# 뿐이라 런타임 override를 반영 못 함). 그래서 entrypoint.sh가 실행 시점에
# `${NAMU_GIT_EMAIL:-namu@container}` / `${NAMU_GIT_NAME:-namu-${NAMU_MACHINE:-web}}`로
# 직접 기본값을 채운다 — git identity가 이미 있으면(이미지 확장 등) 덮어쓰지 않는다.

EXPOSE 8765

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
