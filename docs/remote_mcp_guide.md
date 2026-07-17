# NAMU 원격 MCP 셀프호스팅 가이드 (웹 Claude 커넥터용)

> 📅 2026-07-17(namu-45) · 선행: `docs/remote_mcp_design.md`(설계 원본, v4 확정본) · namu-44(인증·디바운스 pull·터널 실측)·namu-45(클라우드 컨테이너 이미지) 구현 결과를 사용자 관점으로 정리한 문서. **2026-07-17 사용자 소유 상시 서버에 실제로 배포해 전 구간을 실측 검증한 뒤 이 개정판에 반영했다** — 자세한 내용은 4절 "검증 상태"를 볼 것.
>
> **범위** — 경로 B(셀프호스팅, 단일 사용자)만 다룬다. 중앙 호스팅(경로 A)·멀티유저·OAuth는 스코프 밖이다(`remote_mcp_design.md` §11).

이 문서는 [설치형 사용설명서](install_guide.md)·[사용설명서](usage_guide.md)와 대상 독자가 다르다 — Claude Code/agy 없이 **웹 브라우저의 claude.ai에서 NAMU 기억(교훈)을 쓰고 싶은 사람**을 위한 것이다.

**MCP가 뭔지 모르고 왔다면** — MCP(Model Context Protocol)는 AI가 외부 도구나 데이터에 연결할 때 쓰는 공통 규격이다. NAMU는 이 규격을 이용해 "교훈 저장소"를 하나의 도구 서버로 만들어 노출하고, 웹 Claude를 포함한 어떤 MCP 클라이언트든 같은 방식으로 연결할 수 있게 한다. 이 문서는 그 도구 서버를 **직접 인터넷에 상시로 띄워 운영하는(셀프호스팅)** 절차를 다룬다.

## 0. NAMU를 쓰는 3가지 형태

| 형태 | 무엇을 하는가 | 언제 쓰는가 | 실행 엔진 |
|---|---|---|---|
| **설치형** | 자기 프로젝트에 `namu-plugin`을 CC/agy 플러그인으로 설치(stdio 전송 — AI 프로그램과 도구 서버가 표준입출력으로 직접 대화하는 방식, 네트워크를 안 탄다) | 평소 코딩 작업에서 NAMU 전체 기능(세션 브리핑·`/namu-task`·워커 오케스트레이션 등)을 쓰고 싶을 때 — 대부분의 사용자 | Claude Code / agy |
| **clone 개발형** | 이 repo(`namu-agent`)를 그대로 clone해 그 안에서 실행 | NAMU 자체를 개발·수정할 때 | Claude Code / agy |
| **셀프호스팅형 (이 문서)** | `namu-plugin/http_server.py`를 원격 HTTP 서버로 상시 구동해 claude.ai Custom Connector(웹 Claude에 외부 도구를 연결하는 기능)로 연결 | Claude Code/agy 없이 **웹 브라우저**에서만 NAMU 교훈을 recall/record/search 하고 싶을 때 | claude.ai(웹) |

앞 두 형태는 로컬에서 CC/agy가 `mcp_server.py`를 stdio로 직접 실행한다. 셀프호스팅형은 그 **레이어 C(메모리 코어)만** 네트워크 너머로 노출한다(설계 §1) — 아래 1절의 한계를 반드시 먼저 읽을 것.

## 1. 시작 전 알아둘 것 — 웹 사용의 한계

셀프호스팅형은 로컬 설치형과 겉보기엔 비슷해 보이지만 실제로 쓸 수 있는 기능이 훨씬 좁다.

- **레이어 B(자동화)가 전혀 없다** — 세션 시작 시 자동 브리핑, `/namu-task` 오케스트레이션, `namu-coder`/`namu-reviewer` 서브에이전트 호출이 전부 CC/agy 쪽 기능이라 웹에는 대응 개념이 없다. 웹 Claude가 스스로 recall을 부르게 하려면 **도구 description이 유일한 유도 수단**이다(기존 docstring이 "BEFORE starting a task" 식으로 이미 작성돼 있어 그대로 노출된다).
- **노출되는 도구는 3종뿐** — `namu_recall`/`namu_record`/`namu_search`. `namu_sync_setup`과 tasks 관련 기능은 노출되지 않는다.
  - `namu_sync_setup` 미노출 이유 — 이 도구는 서버의 git remote(교훈이 동기화되는 원격 저장소 주소)를 재배선한다. 원격 호출자에게 그대로 열어두면 remote 탈취로 이어질 수 있는 보안 사고라 웹에서는 원천 차단하고, 서버 쪽 sync 배선은 셀프호스팅 운영자(자기 PC의 기존 git 자격증명, 또는 클라우드는 `entrypoint.sh`)가 대신한다(3·4절).
  - tasks 미노출 이유 — tasks는 "프로젝트 cwd 귀속" 개념인데 웹 대화에는 대응하는 프로젝트 폴더 개념 자체가 없다.

즉 셀프호스팅형으로 얻는 것은 "웹 브라우저에서 교훈을 조회·검색·기록"뿐이며, NAMU의 작업 오케스트레이션 기능은 여전히 CC/agy(설치형·clone 개발형) 몫이다.

## 2. 인증 설계 — 실측 확정 의미론

`namu-plugin/http_server.py`는 두 인증 방식을 **동시 지원**하며, 설정한 조합에 따라 동작이 정확히 이렇게 갈린다(namu-44 코드·실측 확정, `remote_mcp_design.md` §5 원안을 이 문서가 실측 기준으로 정밀화):

| 조합 | 동작 |
|---|---|
| `NAMU_HTTP_TOKEN`만 설정 | 엔드포인트(서버가 요청을 받는 구체적인 주소 경로)는 `/mcp`. 모든 요청에 헤더(HTTP 요청에 붙는 부가 정보) 검증(`x-api-key` 또는 `Authorization: Bearer <token>`)만 통과하면 됨 |
| `NAMU_HTTP_PATH_SECRET`만 설정 | 엔드포인트가 `/mcp/<secret>`로 바뀜. 그 경로로만 요청하면 헤더 없이 통과(`/mcp`로 오면 라우팅 자체가 없어 404) |
| **둘 다 설정** | **AND** — `/mcp/<secret>` 경로로 정확히 요청**하고**, 헤더도 토큰과 일치해야만 통과. 둘 중 하나만 맞으면 접속 실패(경로 불일치는 404, 경로는 맞는데 헤더가 틀리면 401) |
| 둘 다 미설정 + `NAMU_HTTP_ALLOW_NOAUTH=1` | 무인증. **로컬 테스트 전용** — 공개 인터넷에 노출하는 배포에서는 절대 쓰지 말 것 |
| 둘 다 미설정, `ALLOW_NOAUTH`도 아님 | **서버가 기동 자체를 거부**(`SystemExit(2)`) — 무인증 공개 노출 방지 |

두 조건이 코드상 "하나의 AND 조건문"으로 합쳐져 있는 건 아니다 — 경로 검증은 FastMCP 라우팅 레벨(`streamable_http_path` 자체가 바뀜)에서, 헤더 검증은 그 위를 감싸는 별도 ASGI 미들웨어(요청을 실제 처리 로직에 넘기기 전에 가로채 미리 검사하는 코드 계층)에서 각자 독립적으로 이뤄진다. 하지만 **결과적으로는 둘 다 설정 시 둘 다 통과해야 접속되므로 AND로 동작한다** — 설계서 §5의 "AND 아님" 서술은 구현 메커니즘(각자 켠 것만 검사)에 대한 설명이었고, 사용자가 체감하는 접속 조건은 AND가 맞다(namu-44 실측 확정).

**권장: 시크릿 경로 단독 모드.** claude.ai의 Request headers 설정 UI는 2026-07 기준 **베타·점진 롤아웃 중**이라 계정에 아예 안 보일 수 있다. 헤더 UI가 없으면 `NAMU_HTTP_TOKEN`을 쓸 방법이 없으므로, **`NAMU_HTTP_PATH_SECRET`만 설정하고 URL 자체(`https://<host>/mcp/<secret>`)로 인증하는 방식을 기본으로 권장한다.** 헤더 UI가 계정에 있다면 `NAMU_HTTP_TOKEN`을 추가로 얹어 이중화해도 된다(위 표의 "둘 다 설정" 행).

헤더 인증을 쓸 경우 서버가 실제로 검사하는 헤더는 **`x-api-key`** 또는 **`Authorization: Bearer <token>`** 둘뿐이다(claude.ai UI 자체는 최대 4개 헤더명을 허용하지만, 그중 이 서버가 인식하는 건 이 두 가지뿐이므로 커넥터 등록 시 헤더 이름을 반드시 이 중 하나로 맞출 것).

## 3. 연결 절차 A — 자기 PC + 터널 (1차 검증, 실측 완료)

가장 간단하고 배포물이 필요 없는 경로다. 지금 쓰고 있는 PC의 `~/.namu`를 그대로 웹에 노출한다.

이 방법은 "**지금 당장 체험해보고 싶다**"에 최적화돼 있다 — 자기 소유 도메인이나 상시 서버가 없어도 몇 분 안에 웹 연결까지 끝낼 수 있다. 대신 PC를 계속 켜둬야 하고, 터널 주소가 바뀔 때마다 claude.ai 커넥터를 다시 등록해야 한다. **자기 소유의 상시 서버(미니PC·VPS 등)와 고정 도메인이 있다면 터널 없이 곧장 4절로 가는 편이 낫다** — 주소가 고정이라 커넥터 재등록도 최초 1회뿐이다.

### 3-1. 서버 기동

clone 개발형이면 repo 루트에서, 설치형이면 설치된 `namu-plugin` 폴더 경로(예: `~/.claude/plugins/cache/namu-marketplace/namu/<버전>/`, install_guide.md 3절 참고)에서 실행한다. **아래 명령은 모두 지금 이 문서를 따라 하고 있는 그 PC(로컬 PC)의 터미널에서 실행한다.**

```bash
# 시크릿 경로 단독 모드 (권장) — 로컬 PC 터미널
NAMU_HTTP_PATH_SECRET="<임의의 긴 문자열>" \
  uv run --script namu-plugin/http_server.py
```

```bash
# 로컬 무인증 스모크 테스트 전용(공개 노출 금지) — 로컬 PC 터미널
NAMU_HTTP_ALLOW_NOAUTH=1 NAMU_HTTP_PORT=18765 \
  uv run --script namu-plugin/http_server.py
```

기본 바인드(서버가 어느 네트워크 주소로 요청을 받아들일지)는 `127.0.0.1:8765`(자기 PC 안에서만 접속 가능, 7절 환경변수 표 참고) — 터널 클라이언트가 같은 PC에서 이 포트에 접속하므로 이 기본값 그대로 충분하다.

### 3-2. 터널로 공개 HTTPS URL 확보 — 무료 터널 주의

claude.ai는 **공개 인터넷에서 접근 가능한 URL**이 필수다(사설망·VPN 뒤는 불가, `remote_mcp_design.md` §2). PC를 상시 공개 서버로 열 수 없다면 터널을 쓴다. 터널이란 지금 이 PC의 로컬 서버(`127.0.0.1:8765`)를 외부 인터넷에서도 접속할 수 있도록 임시로 뚫어주는 중계 통로다 — 자기 PC를 직접 공유기 설정 등으로 공개하지 않고도 임시 공개 URL을 받을 수 있다.

**namu-44에서 3개 무료 터널을 실측한 결과, "URL 발급 성공"과 "실제 포워딩 동작"은 별개였다:**

| 터널 | 실측 결과 |
|---|---|
| Cloudflare quick tunnel(`cloudflared tunnel --url ...`) | URL은 발급되나 **API가 간헐적으로 500**을 반환 — 불안정 |
| localhost.run(`ssh -R 80:localhost:PORT localhost.run`) | URL은 정상 발급되지만 **edge 포워딩 자체가 안 됨**(요청이 로컬까지 안 옴) — 실사용 불가 판정 |
| **pinggy**(`ssh -p 443 -R0:localhost:PORT free.pinggy.io`) | **실제로 동작 확인**됨 — 터널 경유 `initialize`·`tools/list`·`namu_recall` 실호출까지 성공 |

**그러니 어떤 터널을 쓰든, claude.ai에 등록하기 전에 반드시 curl로 실제 포워딩을 먼저 검증하라** (curl은 터미널에서 HTTP 요청을 직접 보내볼 수 있는 명령줄 도구다 — 브라우저 없이 서버가 살아있는지 확인할 때 쓴다):

```bash
# 로컬 PC 터미널 (터널 URL을 향해 요청을 보내지만, 명령 자체는 로컬 PC에서 실행)
curl -sS -X POST "https://<터널 URL>/mcp/<secret>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
```

정상 JSON-RPC(요청·응답을 JSON 형식으로 주고받는 원격 호출 규약) 응답(에러 없이 `result` 포함)이 오면 그제서야 claude.ai에 등록한다. 타임아웃·연결거부·502류 응답이면 "URL은 있는데 안 뚫린 것"이므로 다른 터널로 바꾼다. 위 표는 2026-07 시점 실측이며 무료 터널 서비스 상태는 계속 바뀔 수 있으니, 특정 터널 하나에 배포를 고정하지 말고 매번 이 curl 검증을 거칠 것을 권장한다.

터널이 도메인을 발급하면 5절의 `NAMU_HTTP_ALLOWED_HOSTS`도 함께 설정해야 한다(안 하면 421 에러).

### 3-3. claude.ai에 Custom Connector 등록

1. claude.ai → 설정 → Connectors → **Add custom connector**.
2. Remote MCP server URL에 터널 URL + 엔드포인트 경로를 넣는다. 시크릿 경로 단독 모드면 `https://<터널 URL>/mcp/<secret>`, 헤더 인증을 함께 쓴다면 URL은 `/mcp`(또는 `/mcp/<secret>`)로 두고 Request headers 설정에 `x-api-key: <토큰>`(또는 `Authorization: Bearer <토큰>`)을 추가한다(헤더 UI가 안 보이면 시크릿 경로 단독 모드만 가능 — 2절 참고).
3. 등록 후 대화에서 "namu 메모리에서 recall 해봐"처럼 직접 도구 호출을 유도해 동작을 확인한다(1절 — 자동 브리핑이 없으므로 첫 호출은 사용자가 유도해야 함).

**제약** — PC가 꺼지거나 서버 프로세스가 죽으면 웹에서 접속이 끊긴다. 상시 가동이 필요하면 4절로 간다.

## 4. 연결 절차 B — 상시 서버(클라우드 컨테이너)

`deploy/Dockerfile`·`deploy/entrypoint.sh`·`deploy/namu_cloud_sync_setup.py`(namu-45)로 준비된 배포물을 쓴다. **PC 상시구동 없이** 상시 가동 서버를 만들 수 있다.

이 절은 "**한 번 등록해두고 계속 쓰고 싶다**"에 최적화돼 있다 — PC를 껐다 켜도 죽지 않는 상시 서버(사용자 소유 미니PC, VPS 등)와 고정 도메인이 있다는 전제다. 이런 환경이 아직 없다면 3절 터널 방식으로 먼저 체험해보고, 상시 운영이 필요해지면 이 절로 넘어오는 것도 방법이다. 고정 도메인이 있으면 claude.ai 커넥터도 최초 1회 등록으로 끝난다(3절과 달리 재등록이 필요 없다).

> **검증 상태** — 2026-07-17, 사용자 소유 상시 서버(미니PC, onnamu.kr 인프라)에 이 이미지를 실제로 배포해 전 구간을 실측 검증했다: GitHub 참조 빌드(아래 4-3절) → Cloudflare named tunnel(고정 도메인으로 연결되는 상시 터널, 3절의 임시 quick tunnel과 달리 주소가 바뀌지 않는다)로 라우팅 → claude.ai Custom Connector 등록(고정 주소라 최초 1회만) → 웹에서 recall/search/record 3종 실호출 성공. record가 `machine: web`으로 기록되고 자동으로 원격 저장소에 push된 뒤 **다른 PC에서도 그 기록이 조회되는 것까지 확인**해, 여러 기기가 하나의 기억 풀을 실제로 공유한다는 설계 목표가 동작함을 검증했다. 시크릿 경로 `initialize` 200 응답, 오답 경로·시크릿 없는 `/mcp` 접근은 404, `tools/list`에 3종 도구만 노출, `NAMU_HTTP_ALLOWED_HOSTS`를 자기 도메인으로 지정해 421도 발생하지 않았다.
>
> **다만 Railway·Fly.io 같은 PaaS(서버를 직접 관리하지 않고 플랫폼이 대신 실행해주는 클라우드 서비스)로 배포하는 경로는 여전히 검증된 적이 없고, 4-4절의 `$PORT` 자동 브리징 갭도 그대로 남아 있다.** 이 절은 "이미지를 어떻게 빌드·기동하는가"와 "자기 소유 서버에 올리는 방법"까지는 검증 근거를 갖고 다루지만, 특정 PaaS 플랫폼에 실제로 올리는 절차(사용자의 플랫폼 선택 이후)는 이 문서의 범위 밖이다.

### 4-1. 사전 준비

- 교훈 저장소로 쓸 **비공개 GitHub 저장소**(설치형 6절과 동일한 저장소를 재사용해도 되고, 새로 만들어도 된다) — 여기에 push 권한이 있는 PAT(개인 액세스 토큰 — 비밀번호 대신 발급받아 쓰는, 특정 권한만 가진 인증 값. 비밀번호처럼 절대 남에게 보이거나 코드에 그대로 적어 넣으면 안 된다).
- 이 저장소를 가리키는 토큰 내장 HTTPS remote URL을 만든다:
  ```
  https://x-access-token:<PAT>@github.com/<user>/<repo>.git
  ```

### 4-2. 시크릿을 어디에 둘 것인가

이 컨테이너를 기동하려면 최소 두 가지 값(`NAMU_SYNC_REMOTE`, 그리고 `NAMU_HTTP_PATH_SECRET` 또는 `NAMU_HTTP_TOKEN`)이 필요한데, 이런 값을 **시크릿**이라 부른다 — 외부에 노출되면 안 되는 비밀 값(비밀번호·토큰 등)이라는 뜻이다. 시크릿을 어디에 보관하고 어떻게 서버에 주입하느냐에 따라 관리 방식이 갈린다.

**기본 경로(대부분의 사용자에게 권장) — 서버 로컬 `.env` 파일(compose 파일과 같은 폴더)을 쓰거나, 배포 플랫폼(Railway 등)의 환경변수 설정 화면에 직접 입력한다.**

이게 기본인 이유:
- 전제 조건이 가장 적다 — docker·compose(여러 컨테이너 설정을 파일 하나로 묶어 관리하는 도구)를 쓰는 시점에 이미 알고 있는 표준 관례이며, 별도 CI(코드를 push하면 자동으로 빌드·배포까지 이어지는 파이프라인) 구축이 필요 없다.
- 시크릿이 그 값이 필요한 서버 한 곳에만 존재한다 — GitHub·CI 러너 같은 중간 경유지가 없어 노출될 표면이 좁다.
- 6절 "시크릿은 이미지에 굽지 말고 배포 환경변수로만 주입한다" 원칙과 같은 이야기다.
- 문제가 생겼을 때 확인할 곳이 `.env` 파일 하나뿐이라 단순하다.

**compose 예시(2026-07-17 실배포 검증 구성을 반영, 서버의 아무 폴더에 `docker-compose.yml`로 저장):**

```yaml
# docker-compose.yml (서버, 아래 .env와 같은 폴더)
services:
  namu-remote-mcp:
    image: namu-remote-mcp:latest   # 빌드는 4-3절에서 별도로 미리 해둔다 — 여기서는 참조만
    env_file:
      - .env                        # 시크릿 2종은 여기서 읽어온다
    environment:
      # 시크릿이 아니라 이 서버의 공개 도메인일 뿐이므로 .env가 아니라 여기 둬도 된다
      NAMU_HTTP_ALLOWED_HOSTS: "mcp.example.com"
    ports:
      - "8765:8765"
    volumes:
      # 컨테이너를 지우거나 재시작해도 교훈 데이터(~/.namu)가 남도록 도커가 관리하는
      # 저장 공간(named volume)에 영속화한다. 컨테이너 안 HOME=/root이므로 ~/.namu는
      # /root/.namu다(deploy/entrypoint.sh 기준).
      - namu-data:/root/.namu
    restart: unless-stopped

volumes:
  namu-data:
```

```bash
# .env (서버, docker-compose.yml과 같은 폴더 — 반드시 git에 커밋하지 말 것. .gitignore에 추가)
NAMU_SYNC_REMOTE=https://x-access-token:<PAT>@github.com/<user>/<repo>.git
NAMU_HTTP_PATH_SECRET=<임의의 긴 문자열>
```

**`.env` 원본·사본이 조용히 사라지는 사고 — 일반 원칙으로 알아둘 것.** 만약 쓰고 있는 배포 스크립트나 자동화가 "원본 `.env` → 서비스별 폴더에 사본으로 복사"하는 구조로 돼 있다면, 사용자가 그 사본을 직접 고쳐도 다음 배포가 실행되는 순간 스크립트가 원본 내용으로 덮어써 수정 사항이 소리 없이 지워질 수 있다. 이건 특정 인프라에 국한된 얘기가 아니라 어떤 배포 자동화를 쓰든 적용되는 일반 원칙이다 — **`.env`를 고치기 전에 "이게 원본인지, 매 배포마다 재생성되는 사본인지"부터 확인할 것.** 어느 쪽인지 모르겠다면 배포 스크립트나 CI 설정에서 `.env`를 만들거나 복사하는 부분을 먼저 찾아보라.

**부록(고급) — CI 시크릿 저장소 패턴**

**전제** — push하면 자동으로 서버까지 배포되는 파이프라인(CI/CD)을 이미 운영 중인 사람에게만 해당한다. 그런 경우가 아니라면 이 부록은 건너뛰어도 된다.

이런 운영자는 시크릿을 GitHub Actions Secrets 같은 CI 시크릿 저장소에 등록해두고, 배포 워크플로가 그 값을 읽어 서버의 `.env` 파일을 생성(또는 갱신)하는 패턴을 쓸 수 있다. 장점은 CI 로그에 값이 자동으로 마스킹(가려짐)되고, 여러 서버에 배포할 때 시크릿을 한 곳에서 중앙 로테이션(주기적 교체)할 수 있다는 것이다 — 둘 다 이미 자동 배포 파이프라인이 있어야 의미가 있는 이점이다. 파이프라인이 없는 대부분의 개인 셀프호스팅 사용자에게는 위 기본 경로로 충분하다.

### 4-3. 이미지 빌드 · 기동

먼저 용어부터. **이미지**는 서버를 실행하는 데 필요한 모든 것(코드·의존성·설정)을 그대로 담아 굳혀둔 꾸러미이고, **컨테이너**는 그 이미지를 실제로 띄워 돌아가고 있는 상태를 말한다. 이 절은 이미지를 어떻게 만들고(빌드) 컨테이너로 띄우는지를 다룬다.

**권장 패턴: 빌드는 `docker build`로 따로 하고, compose는 완성된 이미지 태그만 참조한다** (위 4-2절 compose 예시가 이미 이 패턴이다). 이렇게 분리하는 이유가 하나 있다.

> **Windows 함정** — Windows용 Docker Desktop의 `docker compose`는 `build.context`(빌드에 쓸 소스 위치)에 GitHub URL을 직접 넣으면 이를 로컬 파일 경로로 잘못 해석해 빌드가 실패한다(에러 예: `failed to evaluate path ...\namu\https:: syntax is incorrect`). 반면 같은 URL을 `docker build`(BuildKit)에 직접 주면 정상 동작한다. 그래서 compose 파일 안에는 GitHub URL을 아예 넣지 않고, 빌드는 별도 `docker build` 명령으로 분리해 어떤 OS에서도 안전하게 동작하도록 하는 것이 이 문서의 기본 권장 패턴이다.

**GitHub 참조 빌드**란, 소스를 먼저 로컬에 `git clone`하지 않고 `docker build`가 GitHub URL을 곧바로 빌드 재료(컨텍스트)로 가져와 빌드하는 방식이다. 아래는 실제 검증에 쓰인 명령이다(태그 `v0.1.25`는 실배포 시점 기준이며, 최신 버전을 쓰려면 GitHub 릴리스 태그를 확인해 바꿔 넣으면 된다):

```bash
# 서버 터미널에서 실행 (compose가 이 이미지를 로컬 이미지로 참조하므로,
# compose를 실행할 바로 그 서버에서 빌드해야 한다)
docker build -f deploy/Dockerfile -t namu-remote-mcp:latest \
  'https://github.com/onmiso-hash/namu-agent.git#v0.1.25'
```

**PowerShell(Windows 서버)에서 실행한다면 반드시 URL을 작은따옴표로 감쌀 것** — 그대로 두면 URL 뒤의 `#v0.1.25`(태그 지정)가 PowerShell/bash 양쪽 모두에서 주석 시작 기호로 오인돼 잘려나간다. 위 명령처럼 작은따옴표(`'...'`)로 통째로 감싸면 bash·PowerShell 모두에서 안전하다.

빌드가 끝나면 4-2절의 `docker-compose.yml`이 있는 폴더에서 기동한다:

```bash
# 서버 터미널에서 실행 (docker-compose.yml·.env가 있는 폴더)
docker compose up -d
```

**compose 없이 한 번만 빠르게 띄워보고 싶다면** `docker run`으로도 가능하다(단발성 테스트에 적합, 상시 운영에는 위 compose+named volume 조합을 권장):

```bash
# 서버 터미널에서 실행 — 단발성 테스트용
docker run -p 8765:8765 \
  -e NAMU_SYNC_REMOTE="https://x-access-token:<PAT>@github.com/<user>/<repo>.git" \
  -e NAMU_HTTP_PATH_SECRET="<임의의 긴 문자열>" \
  namu-remote-mcp:latest
```

`entrypoint.sh`가 컨테이너 기동 시 순서대로 처리한다: ① `NAMU_SYNC_REMOTE`가 없으면 즉시 에러로 기동 거부 ② `~/.namu`가 없으면 clone, 있으면 pull ③ git identity(커밋을 남긴 사람 정보 — `user.email`/`user.name`)가 비어 있으면 `NAMU_GIT_EMAIL`/`NAMU_GIT_NAME`(또는 기본값)으로 채움 — `python:3.12-slim`(이 이미지가 바탕으로 삼는 최소 구성 파이썬 이미지)에는 identity가 없어 다음 단계의 초기 커밋이 "Author identity unknown"으로 실패하는 갭이 실측됐다(namu-45 docker 실검증) ④ `namu_cloud_sync_setup.py`(기존 `memory_sync.sync_setup()` 재사용)로 `.namu_sync` 마커·`.gitattributes` union 라인·git remote origin을 wiring ⑤ `http_server.py`를 exec로 기동. 각 단계는 실패 시 조용히 넘어가지 않고 stderr 메시지와 함께 즉시 종료한다.

이미지 기본값(직접 override하지 않는 한 그대로 적용됨):

- `NAMU_MACHINE=web` — 웹에서 기록된 교훈을 machine 필드로 구분하기 위한 기본값(원하면 배포 시 override, 예: `cloud-railway`).
- `NAMU_HTTP_HOST=0.0.0.0`, `NAMU_HTTP_PORT=8765` — 컨테이너는 반드시 `0.0.0.0`(모든 네트워크 인터페이스에서 요청을 받는다는 뜻)으로 바인드해야 플랫폼 리버스 프록시가 도달할 수 있다.
- `NAMU_HTTP_ALLOWED_HOSTS=*` — 클라우드 도메인은 대개 배포 시점에야 발급돼 이미지 빌드 시점엔 미리 넣을 수 없으므로, 기본값으로 DNS rebinding 보호 자체를 꺼둔다(5절 참고). 인증은 이 보호와 무관하게 `NAMU_HTTP_TOKEN`/`NAMU_HTTP_PATH_SECRET`이 별도로 담당하므로 `*`로 둬도 무인증 공개 노출이 되는 건 아니다. 배포 도메인을 미리 알고 있다면(4-2절 compose 예시처럼) `NAMU_HTTP_ALLOWED_HOSTS=your-domain.example.com`처럼 좁혀서 재정의하는 편이 더 방어적이다.

`NAMU_HTTP_TOKEN`/`NAMU_HTTP_PATH_SECRET`/`NAMU_SYNC_REMOTE`는 의도적으로 이미지에 기본값이 없다 — 시크릿이므로 이미지에 굽지 않고 **배포 시점의 환경변수 주입(4-2절)으로만** 넣어야 한다. 둘 다(TOKEN/PATH_SECRET) 미설정이면 컨테이너 안의 `http_server.py`가 2절 표의 규칙대로 기동을 거부한다.

### 4-4. 알려진 캐비엇

- **`$PORT` 자동 브리징 없음** — Railway 등 일부 PaaS는 컨테이너가 플랫폼이 지정하는 `$PORT` 환경변수로 리슨(수신 대기)하길 기대한다. 이 이미지는 `NAMU_HTTP_PORT` 고정 기본값(8765)이라 자동으로 `$PORT`를 따라가지 않는다. 그런 플랫폼에 배포한다면 `NAMU_HTTP_PORT`를 플랫폼이 주는 `$PORT` 값에 맞춰 직접 override해야 한다(namu-45 유닛 A 스펙 갭, 아직 미해결).
- **PaaS 배포 자체가 아직 검증 밖이다** — 4절 도입부의 검증 상태대로, 자기 소유 서버(직접 관리하는 미니PC/VPS)에 compose로 올리는 경로는 실측 완료됐지만, Railway·Fly.io처럼 플랫폼이 컨테이너를 대신 운영해주는 방식은 플랫폼마다 환경변수 주입 화면·네트워킹 방식이 달라 이 문서만으로 충분한지 확인된 바 없다. 그런 플랫폼에 배포한다면 위 `$PORT` 캐비엇을 포함해 해당 플랫폼의 공식 문서를 함께 참고할 것.

## 5. `NAMU_HTTP_ALLOWED_HOSTS` — 421 Misdirected Request 해소

터널이나 리버스 프록시(외부 요청을 대신 받아 내부의 실제 서버로 전달해주는 중계 서버 — 터널도 넓게 보면 이 역할의 일종이다)를 거쳐 접속하면 `421 Misdirected Request`가 날 수 있다. **원인**: mcp SDK(FastMCP)가 서버 생성 시점에 `host`가 `127.0.0.1`/`localhost`/`::1` 중 하나면(이 서버는 실제 바인드 주소와 무관하게 항상 이 조건에 해당) DNS rebinding(공격자가 도메인 이름을 악용해 브라우저가 사설 네트워크로 요청을 보내게 속이는 공격 기법) 방지를 자동으로 켜고, 허용 `Host` 헤더를 로컬호스트 3종으로 고정한다. 터널·프록시 도메인의 `Host` 헤더는 이 목록에 없어 거부된다.

**해법** — `NAMU_HTTP_ALLOWED_HOSTS`에 터널/프록시 도메인을 쉼표로 구분해 추가한다(로컬호스트 3종 허용은 그대로 유지된 채 사용자 항목이 더해진다 — 대체가 아니라 확장이므로 로컬 curl 스모크는 계속 동작한다):

```bash
NAMU_HTTP_ALLOWED_HOSTS="my-tunnel-1.example.com,my-tunnel-2.example.com" \
  uv run --script namu-plugin/http_server.py
```

`*`를 주면 이 보호 자체를 비활성화한다(도메인이 배포마다 유동적일 때의 명시적 opt-out) — **컨테이너 이미지는 기본값이 이미 `*`**다(4절). 자기 PC + 터널 조합이나 고정 도메인이 있는 상시 서버처럼 매번 도메인을 알 수 있는 환경이라면 `*` 대신 실제 도메인을 지정하는 편이 더 방어적이다.

## 6. 보안 주의

- **uvicorn(이 서버를 실제로 구동하는 내부 웹 서버 프로그램) 액세스 로그에 시크릿 경로가 평문으로 남는다.** `NAMU_HTTP_PATH_SECRET`을 URL 경로로 쓰는 방식의 구조적 특성이다 — 로그를 누구에게든 공유하거나 노출하면 그 즉시 시크릿이 유출된 것과 같다. 시크릿 유출이 의심되면 지체 없이 값을 교체(서버 재기동)할 것.
- **터널을 끝낼 때 시크릿도 함께 폐기(교체)할 것을 권장한다.** 터널 URL 자체는 만료돼도, 같은 시크릿 경로/토큰을 다음 터널 세션에도 재사용하면 과거 로그에 남은 값이 여전히 유효한 채로 남는다.
- 이 서버는 HTTPS(암호화된 HTTP 통신)를 직접 종단(암호화를 풀어 실제 요청을 처리하는 지점이 되는 것)하지 않는다 — 터널(cloudflared/pinggy 등)이나 플랫폼(Railway 등)이 HTTPS를 담당한다는 전제다. HTTP 평문 구간이 남지 않도록 반드시 HTTPS를 종단하는 터널/플랫폼을 쓸 것.

## 7. 환경변수 레퍼런스

아래 표의 환경변수(프로그램 코드를 고치지 않고 실행 시점에 외부에서 넣어주는 설정 값)는 `namu-plugin/config.py`의 `http_settings()`와 `namu-plugin/http_server.py` 상단 docstring, `deploy/Dockerfile`을 실코드 기준으로 확정했다.

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `NAMU_HTTP_TOKEN` | `""`(미설정) | 헤더 인증 토큰. 요청의 `x-api-key` 또는 `Authorization: Bearer <token>`이 이 값과 `hmac.compare_digest`(타이밍 공격에 안전한 비교 방식)로 일치해야 통과 |
| `NAMU_HTTP_PATH_SECRET` | `""`(미설정) | 시크릿 URL 경로 세그먼트. 설정 시 엔드포인트가 `/mcp/<secret>`로 바뀜. `/`를 포함하면 기동 시 `ValueError` |
| `NAMU_HTTP_HOST` | `127.0.0.1` | uvicorn 바인드 호스트. 컨테이너 이미지는 `0.0.0.0`으로 override됨 |
| `NAMU_HTTP_PORT` | `8765` | uvicorn 바인드 포트. 정수 아니면 기동 시 `ValueError` |
| `NAMU_HTTP_PULL_INTERVAL` | `60.0`(초) | 디바운스(짧은 시간 안의 중복 실행을 걸러 한 번만 실행) git pull 간격. 마지막 pull에서 이 시간이 지난 뒤 도구 호출이 들어오면 다시 pull. `0`이면 매 요청마다 pull |
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
