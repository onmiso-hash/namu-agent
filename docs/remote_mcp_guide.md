# NAMU 원격 MCP 셀프호스팅 가이드 (웹 Claude 커넥터용)

> 📅 2026-07-17(namu-45) · 선행: `docs/remote_mcp_design.md`(설계 원본, v4 확정본) · namu-44(인증·디바운스 pull·터널 실측)·namu-45(클라우드 컨테이너 이미지) 구현 결과를 사용자 관점으로 정리한 문서.
>
> **범위** — 경로 B(셀프호스팅, 단일 사용자)만 다룬다. 중앙 호스팅(경로 A)·멀티유저·OAuth는 스코프 밖이다(`remote_mcp_design.md` §11).

이 문서는 [설치형 사용설명서](install_guide.md)·[사용설명서](usage_guide.md)와 대상 독자가 다르다 — Claude Code/agy 없이 **웹 브라우저의 claude.ai에서 NAMU 기억(교훈)을 쓰고 싶은 사람**을 위한 것이다.

## 0. NAMU를 쓰는 3가지 형태

| 형태 | 무엇을 하는가 | 언제 쓰는가 | 실행 엔진 |
|---|---|---|---|
| **설치형** | 자기 프로젝트에 `namu-plugin`을 CC/agy 플러그인으로 설치(stdio 전송) | 평소 코딩 작업에서 NAMU 전체 기능(세션 브리핑·`/namu-task`·워커 오케스트레이션 등)을 쓰고 싶을 때 — 대부분의 사용자 | Claude Code / agy |
| **clone 개발형** | 이 repo(`namu-agent`)를 그대로 clone해 그 안에서 실행 | NAMU 자체를 개발·수정할 때 | Claude Code / agy |
| **셀프호스팅형 (이 문서)** | `namu-plugin/http_server.py`를 원격 HTTP 서버로 상시 구동해 claude.ai Custom Connector로 연결 | Claude Code/agy 없이 **웹 브라우저**에서만 NAMU 교훈을 recall/record/search 하고 싶을 때 | claude.ai(웹) |

앞 두 형태는 로컬에서 CC/agy가 `mcp_server.py`를 stdio로 직접 실행한다. 셀프호스팅형은 그 **레이어 C(메모리 코어)만** 네트워크 너머로 노출한다(설계 §1) — 아래 1절의 한계를 반드시 먼저 읽을 것.

## 1. 시작 전 알아둘 것 — 웹 사용의 한계

셀프호스팅형은 로컬 설치형과 겉보기엔 비슷해 보이지만 실제로 쓸 수 있는 기능이 훨씬 좁다.

- **레이어 B(자동화)가 전혀 없다** — 세션 시작 시 자동 브리핑, `/namu-task` 오케스트레이션, `namu-coder`/`namu-reviewer` 서브에이전트 호출이 전부 CC/agy 쪽 기능이라 웹에는 대응 개념이 없다. 웹 Claude가 스스로 recall을 부르게 하려면 **도구 description이 유일한 유도 수단**이다(기존 docstring이 "BEFORE starting a task" 식으로 이미 작성돼 있어 그대로 노출된다).
- **노출되는 도구는 3종뿐** — `namu_recall`/`namu_record`/`namu_search`. `namu_sync_setup`과 tasks 관련 기능은 노출되지 않는다.
  - `namu_sync_setup` 미노출 이유 — 이 도구는 서버의 git remote를 재배선한다. 원격 호출자에게 그대로 열어두면 remote 탈취로 이어질 수 있는 보안 사고라 웹에서는 원천 차단하고, 서버 쪽 sync 배선은 셀프호스팅 운영자(자기 PC의 기존 git 자격증명, 또는 클라우드는 `entrypoint.sh`)가 대신한다(3·4절).
  - tasks 미노출 이유 — tasks는 "프로젝트 cwd 귀속" 개념인데 웹 대화에는 대응하는 프로젝트 폴더 개념 자체가 없다.

즉 셀프호스팅형으로 얻는 것은 "웹 브라우저에서 교훈을 조회·검색·기록"뿐이며, NAMU의 작업 오케스트레이션 기능은 여전히 CC/agy(설치형·clone 개발형) 몫이다.

## 2. 인증 설계 — 실측 확정 의미론

`namu-plugin/http_server.py`는 두 인증 방식을 **동시 지원**하며, 설정한 조합에 따라 동작이 정확히 이렇게 갈린다(namu-44 코드·실측 확정, `remote_mcp_design.md` §5 원안을 이 문서가 실측 기준으로 정밀화):

| 조합 | 동작 |
|---|---|
| `NAMU_HTTP_TOKEN`만 설정 | 엔드포인트는 `/mcp`. 모든 요청에 헤더 검증(`x-api-key` 또는 `Authorization: Bearer <token>`)만 통과하면 됨 |
| `NAMU_HTTP_PATH_SECRET`만 설정 | 엔드포인트가 `/mcp/<secret>`로 바뀜. 그 경로로만 요청하면 헤더 없이 통과(`/mcp`로 오면 라우팅 자체가 없어 404) |
| **둘 다 설정** | **AND** — `/mcp/<secret>` 경로로 정확히 요청**하고**, 헤더도 토큰과 일치해야만 통과. 둘 중 하나만 맞으면 접속 실패(경로 불일치는 404, 경로는 맞는데 헤더가 틀리면 401) |
| 둘 다 미설정 + `NAMU_HTTP_ALLOW_NOAUTH=1` | 무인증. **로컬 테스트 전용** — 공개 인터넷에 노출하는 배포에서는 절대 쓰지 말 것 |
| 둘 다 미설정, `ALLOW_NOAUTH`도 아님 | **서버가 기동 자체를 거부**(`SystemExit(2)`) — 무인증 공개 노출 방지 |

두 조건이 코드상 "하나의 AND 조건문"으로 합쳐져 있는 건 아니다 — 경로 검증은 FastMCP 라우팅 레벨(`streamable_http_path` 자체가 바뀜)에서, 헤더 검증은 그 위를 감싸는 별도 ASGI 미들웨어에서 각자 독립적으로 이뤄진다. 하지만 **결과적으로는 둘 다 설정 시 둘 다 통과해야 접속되므로 AND로 동작한다** — 설계서 §5의 "AND 아님" 서술은 구현 메커니즘(각자 켠 것만 검사)에 대한 설명이었고, 사용자가 체감하는 접속 조건은 AND가 맞다(namu-44 실측 확정).

**권장: 시크릿 경로 단독 모드.** claude.ai의 Request headers 설정 UI는 2026-07 기준 **베타·점진 롤아웃 중**이라 계정에 아예 안 보일 수 있다. 헤더 UI가 없으면 `NAMU_HTTP_TOKEN`을 쓸 방법이 없으므로, **`NAMU_HTTP_PATH_SECRET`만 설정하고 URL 자체(`https://<host>/mcp/<secret>`)로 인증하는 방식을 기본으로 권장한다.** 헤더 UI가 계정에 있다면 `NAMU_HTTP_TOKEN`을 추가로 얹어 이중화해도 된다(위 표의 "둘 다 설정" 행).

헤더 인증을 쓸 경우 서버가 실제로 검사하는 헤더는 **`x-api-key`** 또는 **`Authorization: Bearer <token>`** 둘뿐이다(claude.ai UI 자체는 최대 4개 헤더명을 허용하지만, 그중 이 서버가 인식하는 건 이 두 가지뿐이므로 커넥터 등록 시 헤더 이름을 반드시 이 중 하나로 맞출 것).

## 3. 연결 절차 A — 자기 PC + 터널 (1차 검증, 실측 완료)

가장 간단하고 배포물이 필요 없는 경로다. 지금 쓰고 있는 PC의 `~/.namu`를 그대로 웹에 노출한다.

### 3-1. 서버 기동

clone 개발형이면 repo 루트에서, 설치형이면 설치된 `namu-plugin` 폴더 경로(예: `~/.claude/plugins/cache/namu-marketplace/namu/<버전>/`, install_guide.md 3절 참고)에서 실행한다.

```bash
# 시크릿 경로 단독 모드 (권장)
NAMU_HTTP_PATH_SECRET="<임의의 긴 문자열>" \
  uv run --script namu-plugin/http_server.py
```

```bash
# 로컬 무인증 스모크 테스트 전용(공개 노출 금지)
NAMU_HTTP_ALLOW_NOAUTH=1 NAMU_HTTP_PORT=18765 \
  uv run --script namu-plugin/http_server.py
```

기본 바인드는 `127.0.0.1:8765`(4절 환경변수 표 참고) — 터널 클라이언트가 같은 PC에서 이 포트에 접속하므로 이 기본값 그대로 충분하다.

### 3-2. 터널로 공개 HTTPS URL 확보 — 무료 터널 주의

claude.ai는 **공개 인터넷에서 접근 가능한 URL**이 필수다(사설망·VPN 뒤는 불가, `remote_mcp_design.md` §2). PC를 상시 공개 서버로 열 수 없다면 터널을 쓴다.

**namu-44에서 3개 무료 터널을 실측한 결과, "URL 발급 성공"과 "실제 포워딩 동작"은 별개였다:**

| 터널 | 실측 결과 |
|---|---|
| Cloudflare quick tunnel(`cloudflared tunnel --url ...`) | URL은 발급되나 **API가 간헐적으로 500**을 반환 — 불안정 |
| localhost.run(`ssh -R 80:localhost:PORT localhost.run`) | URL은 정상 발급되지만 **edge 포워딩 자체가 안 됨**(요청이 로컬까지 안 옴) — 실사용 불가 판정 |
| **pinggy**(`ssh -p 443 -R0:localhost:PORT free.pinggy.io`) | **실제로 동작 확인**됨 — 터널 경유 `initialize`·`tools/list`·`namu_recall` 실호출까지 성공 |

**그러니 어떤 터널을 쓰든, claude.ai에 등록하기 전에 반드시 curl로 실제 포워딩을 먼저 검증하라:**

```bash
curl -sS -X POST "https://<터널 URL>/mcp/<secret>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
```

정상 JSON-RPC 응답(에러 없이 `result` 포함)이 오면 그제서야 claude.ai에 등록한다. 타임아웃·연결거부·502류 응답이면 "URL은 있는데 안 뚫린 것"이므로 다른 터널로 바꾼다. 위 표는 2026-07 시점 실측이며 무료 터널 서비스 상태는 계속 바뀔 수 있으니, 특정 터널 하나에 배포를 고정하지 말고 매번 이 curl 검증을 거칠 것을 권장한다.

터널이 도메인을 발급하면 4절의 `NAMU_HTTP_ALLOWED_HOSTS`도 함께 설정해야 한다(안 하면 421 에러).

### 3-3. claude.ai에 Custom Connector 등록

1. claude.ai → 설정 → Connectors → **Add custom connector**.
2. Remote MCP server URL에 터널 URL + 엔드포인트 경로를 넣는다. 시크릿 경로 단독 모드면 `https://<터널 URL>/mcp/<secret>`, 헤더 인증을 함께 쓴다면 URL은 `/mcp`(또는 `/mcp/<secret>`)로 두고 Request headers 설정에 `x-api-key: <토큰>`(또는 `Authorization: Bearer <토큰>`)을 추가한다(헤더 UI가 안 보이면 시크릿 경로 단독 모드만 가능 — 2절 참고).
3. 등록 후 대화에서 "namu 메모리에서 recall 해봐"처럼 직접 도구 호출을 유도해 동작을 확인한다(1절 — 자동 브리핑이 없으므로 첫 호출은 사용자가 유도해야 함).

**제약** — PC가 꺼지거나 서버 프로세스가 죽으면 웹에서 접속이 끊긴다. 상시 가동이 필요하면 4절로 간다.

## 4. 연결 절차 B — 클라우드 컨테이너

`deploy/Dockerfile`·`deploy/entrypoint.sh`·`deploy/namu_cloud_sync_setup.py`(namu-45)로 준비된 배포물을 쓴다. **PC 상시구동 없이** 상시 가동 서버를 만들 수 있다.

> **검증 상태(정직 고지)** — 이 이미지는 아직 **로컬 docker 실행 검증이 진행 중**이며(namu-45, docker 설치 대기), 실제 클라우드 플랫폼(Railway/Fly.io/VPS 등) 배포는 **검증된 적이 없다**. 이 절은 "이미지를 어떻게 빌드·기동하는가"까지만 다루고, 특정 클라우드 플랫폼에 실제로 올리는 절차(사용자의 플랫폼 선택 이후)는 이 문서의 범위 밖이다.

### 4-1. 사전 준비

- 교훈 저장소로 쓸 **비공개 GitHub 저장소**(설치형 6절과 동일한 저장소를 재사용해도 되고, 새로 만들어도 된다) — 여기에 push 권한이 있는 PAT(개인 액세스 토큰).
- 이 저장소를 가리키는 토큰 내장 HTTPS remote URL을 만든다:
  ```
  https://x-access-token:<PAT>@github.com/<user>/<repo>.git
  ```

### 4-2. 이미지 빌드·기동

repo 루트에서(컨텍스트가 repo 루트여야 `namu-plugin/`을 COPY할 수 있다):

```bash
docker build -f deploy/Dockerfile -t namu-remote-mcp .

docker run -p 8765:8765 \
  -e NAMU_SYNC_REMOTE="https://x-access-token:<PAT>@github.com/<user>/<repo>.git" \
  -e NAMU_HTTP_PATH_SECRET="<임의의 긴 문자열>" \
  namu-remote-mcp
```

`entrypoint.sh`가 순서대로 처리한다: ① `NAMU_SYNC_REMOTE`가 없으면 즉시 에러로 기동 거부 ② `~/.namu`가 없으면 clone, 있으면 pull ③ git identity(`user.email`/`user.name`)가 비어 있으면 `NAMU_GIT_EMAIL`/`NAMU_GIT_NAME`(또는 기본값)으로 채움 — `python:3.12-slim`에는 identity가 없어 다음 단계의 초기 커밋이 "Author identity unknown"으로 실패하는 갭이 실측됐다(namu-45 docker 실검증) ④ `namu_cloud_sync_setup.py`(기존 `memory_sync.sync_setup()` 재사용)로 `.namu_sync` 마커·`.gitattributes` union 라인·git remote origin을 wiring ⑤ `http_server.py`를 exec로 기동. 각 단계는 실패 시 조용히 넘어가지 않고 stderr 메시지와 함께 즉시 종료한다.

이미지 기본값(직접 override하지 않는 한 그대로 적용됨):

- `NAMU_MACHINE=web` — 웹에서 기록된 교훈을 machine 필드로 구분하기 위한 기본값(원하면 배포 시 override, 예: `cloud-railway`).
- `NAMU_HTTP_HOST=0.0.0.0`, `NAMU_HTTP_PORT=8765` — 컨테이너는 반드시 `0.0.0.0`으로 바인드해야 플랫폼 리버스 프록시가 도달할 수 있다.
- `NAMU_HTTP_ALLOWED_HOSTS=*` — 클라우드 도메인은 대개 배포 시점에야 발급돼 이미지 빌드 시점엔 미리 넣을 수 없으므로, 기본값으로 DNS rebinding 보호 자체를 꺼둔다(5절 참고). 인증은 이 보호와 무관하게 `NAMU_HTTP_TOKEN`/`NAMU_HTTP_PATH_SECRET`이 별도로 담당하므로 `*`로 둬도 무인증 공개 노출이 되는 건 아니다. 배포 도메인을 미리 알고 있다면 `NAMU_HTTP_ALLOWED_HOSTS=your-domain.example.com`처럼 좁혀서 재정의하는 편이 더 방어적이다.

`NAMU_HTTP_TOKEN`/`NAMU_HTTP_PATH_SECRET`/`NAMU_SYNC_REMOTE`는 의도적으로 이미지에 기본값이 없다 — 시크릿이므로 이미지에 굽지 않고 **배포 플랫폼의 환경변수 설정으로만** 주입해야 한다. 둘 다(TOKEN/PATH_SECRET) 미설정이면 컨테이너 안의 `http_server.py`가 2절 표의 규칙대로 기동을 거부한다.

### 4-3. 알려진 캐비엇

- **`$PORT` 자동 브리징 없음** — Railway 등 일부 PaaS는 컨테이너가 플랫폼이 지정하는 `$PORT` 환경변수로 리슨하길 기대한다. 이 이미지는 `NAMU_HTTP_PORT` 고정 기본값(8765)이라 자동으로 `$PORT`를 따라가지 않는다. 그런 플랫폼에 배포한다면 `NAMU_HTTP_PORT`를 플랫폼이 주는 `$PORT` 값에 맞춰 직접 override해야 한다(namu-45 유닛 A 스펙 갭, 아직 미해결).
- 이 캐비엇을 포함해 실제 클라우드 배포 절차 자체는 아직 검증되지 않았다 — 로컬 docker 검증이 끝난 뒤에도 실 플랫폼 배포는 별도 확인이 필요하다.

## 5. `NAMU_HTTP_ALLOWED_HOSTS` — 421 Misdirected Request 해소

터널이나 리버스 프록시를 거쳐 접속하면 `421 Misdirected Request`가 날 수 있다. **원인**: mcp SDK(FastMCP)가 서버 생성 시점에 `host`가 `127.0.0.1`/`localhost`/`::1` 중 하나면(이 서버는 실제 바인드 주소와 무관하게 항상 이 조건에 해당) DNS rebinding 방지를 자동으로 켜고, 허용 `Host` 헤더를 로컬호스트 3종으로 고정한다. 터널·프록시 도메인의 `Host` 헤더는 이 목록에 없어 거부된다.

**해법** — `NAMU_HTTP_ALLOWED_HOSTS`에 터널/프록시 도메인을 쉼표로 구분해 추가한다(로컬호스트 3종 허용은 그대로 유지된 채 사용자 항목이 더해진다 — 대체가 아니라 확장이므로 로컬 curl 스모크는 계속 동작한다):

```bash
NAMU_HTTP_ALLOWED_HOSTS="my-tunnel-1.example.com,my-tunnel-2.example.com" \
  uv run --script namu-plugin/http_server.py
```

`*`를 주면 이 보호 자체를 비활성화한다(도메인이 배포마다 유동적일 때의 명시적 opt-out) — **컨테이너 이미지는 기본값이 이미 `*`**다(4절). 자기 PC + 터널 조합처럼 매번 도메인을 알 수 있는 환경이라면 `*` 대신 실제 도메인을 지정하는 편이 더 방어적이다.

## 6. 보안 주의

- **uvicorn 액세스 로그에 시크릿 경로가 평문으로 남는다.** `NAMU_HTTP_PATH_SECRET`을 URL 경로로 쓰는 방식의 구조적 특성이다 — 로그를 누구에게든 공유하거나 노출하면 그 즉시 시크릿이 유출된 것과 같다. 시크릿 유출이 의심되면 지체 없이 값을 교체(서버 재기동)할 것.
- **터널을 끝낼 때 시크릿도 함께 폐기(교체)할 것을 권장한다.** 터널 URL 자체는 만료돼도, 같은 시크릿 경로/토큰을 다음 터널 세션에도 재사용하면 과거 로그에 남은 값이 여전히 유효한 채로 남는다.
- 이 서버는 HTTPS를 직접 종단하지 않는다 — 터널(cloudflared/pinggy 등)이나 플랫폼(Railway 등)이 HTTPS를 담당한다는 전제다. HTTP 평문 구간이 남지 않도록 반드시 HTTPS를 종단하는 터널/플랫폼을 쓸 것.

## 7. 환경변수 레퍼런스

`namu-plugin/config.py`의 `http_settings()`와 `namu-plugin/http_server.py` 상단 docstring, `deploy/Dockerfile`을 실코드 기준으로 확정했다.

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `NAMU_HTTP_TOKEN` | `""`(미설정) | 헤더 인증 토큰. 요청의 `x-api-key` 또는 `Authorization: Bearer <token>`이 이 값과 `hmac.compare_digest`로 일치해야 통과 |
| `NAMU_HTTP_PATH_SECRET` | `""`(미설정) | 시크릿 URL 경로 세그먼트. 설정 시 엔드포인트가 `/mcp/<secret>`로 바뀜. `/`를 포함하면 기동 시 `ValueError` |
| `NAMU_HTTP_HOST` | `127.0.0.1` | uvicorn 바인드 호스트. 컨테이너 이미지는 `0.0.0.0`으로 override됨 |
| `NAMU_HTTP_PORT` | `8765` | uvicorn 바인드 포트. 정수 아니면 기동 시 `ValueError` |
| `NAMU_HTTP_PULL_INTERVAL` | `60.0`(초) | 디바운스 git pull 간격. 마지막 pull에서 이 시간이 지난 뒤 도구 호출이 들어오면 다시 pull. `0`이면 매 요청마다 pull |
| `NAMU_HTTP_ALLOW_NOAUTH` | 미설정(=off) | `"1"`이면 TOKEN/PATH_SECRET 둘 다 없어도 무인증 기동 허용. **로컬 테스트 전용, 공개 노출 금지** |
| `NAMU_HTTP_ALLOWED_HOSTS` | `""`(미설정 → FastMCP 기본값: `127.0.0.1`/`localhost`/`[::1]`만 허용) | 터널/프록시 경유 시 421 해소용 허용 `Host` 목록, 쉼표 구분. `*`는 DNS rebinding 보호 자체를 비활성화. 컨테이너 이미지 기본값은 `*` |
| `NAMU_SYNC_REMOTE` | (없음, 컨테이너 entrypoint 전용) | 클라우드 컨테이너 부팅 시 `~/.namu`를 clone/pull할 토큰 내장 HTTPS git remote URL. 미설정이면 `entrypoint.sh`가 기동을 거부 |
| `NAMU_MACHINE` | 호스트명(없으면 `unknown`) | 이 값으로 기록된 교훈의 machine 필드가 채워짐. 컨테이너 이미지 기본값은 `web` |
| `NAMU_GIT_EMAIL` | 미설정 시 `namu@container`(entrypoint 전용) | 컨테이너 안 git commit author의 email. `python:3.12-slim`에는 git identity가 없어 `entrypoint.sh`가 `~/.namu`의 `user.email`이 비어 있을 때만 이 값을 `git config --global`로 채운다(이미 설정돼 있으면 덮어쓰지 않음) |
| `NAMU_GIT_NAME` | 미설정 시 `namu-${NAMU_MACHINE:-web}`(entrypoint 전용) | 컨테이너 안 git commit author의 이름. 동작 방식은 `NAMU_GIT_EMAIL`과 동일(`user.name`이 비어 있을 때만 채움) |

## 8. 관련 문서

- 설계 원본·결정 이력: [`remote_mcp_design.md`](remote_mcp_design.md)
- 로컬 설치·`~/.namu` 데이터 위치 등 공통 배경: [`install_guide.md`](install_guide.md)
- 설치형 첫 사용법: [`usage_guide.md`](usage_guide.md)
