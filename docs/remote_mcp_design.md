# NAMU 원격 MCP 서버 설계 (v4 — 실코드·실측 대조 확정본)

> 작성일: 2026-07-16 (namu-44 예정)
> 선행 문서: `namu_agent_원격MCP_전환_계획_v3.md` (2026-07-13, 코드 미확인 초안)
> 이 문서는 v3를 실제 코드베이스·mcp SDK 실측·claude.ai 공식 문서와 대조해 확정한 **작업 기준 문서**다.
> **사용자 확정(2026-07-16)**: ① v3 재구조화 결정 개정 → 최소 변경안(§3·§4) 채택, ② 인증 이중 지원(§5), ③ 1차 검증은 hp PC + 터널(§7-1) — 클라우드(§7-2)는 후속 단계.

---

## 1. 목표

웹 Claude(claude.ai)에서 Custom Connector로 NAMU 메모리(`namu_recall`/`namu_record`/`namu_search`)를 사용할 수 있게, 기존 stdio 전용 MCP 서버를 **원격 Streamable HTTP 서버로도** 구동 가능하게 한다.

- 스코프: **경로 B(셀프호스팅, 단일 사용자)만.** 경로 A(중앙 호스팅 + GitHub App)와 멀티유저 격리는 이번 스코프에서 제외 (v3 결정 유지).
- 원격화 대상은 **레이어 C(메모리 코어)뿐** (v3 §1.1 유지). 웹에서는 자동 세션 브리핑·`/namu-task` 등 레이어 B가 동작하지 않음을 문서에 명시한다.

## 2. 외부 제약 — claude.ai Custom Connector 실측 (2026-07 기준)

공식 문서(support.claude.com 11175166, claude.com/docs/connectors/custom/remote-mcp) 확인 결과:

| 항목 | 확인된 사실 |
|---|---|
| 플랜 | Free/Pro/Max/Team/Enterprise 전부 가능 (Free는 1개 제한) |
| 네트워크 | **공개 인터넷에서 접근 가능한 URL 필수** (Anthropic 클라우드가 접속). 사설망/VPN 뒤는 불가 |
| 전송 | Streamable HTTP, SSE 둘 다 지원 → **Streamable HTTP 채택** (MCP 표준 현행) |
| 인증 ① | OAuth 2.1 (DCR) — 구현 부담 큼, 개인용에 과함 |
| 인증 ② | **Request headers (고정 API 키/Bearer)** — 커넥터 추가 대화상자에서 헤더 설정. 단 **베타, 점진 롤아웃 중**이라 계정에 안 보일 수 있음. 헤더명은 allowlist(`authorization`, `x-api-key`, `x-auth-token` 등), 최대 4개 |
| 인증 ③ | 무인증 서버도 등록 자체는 가능 |

**설계 귀결**: OAuth는 구현하지 않는다. 토큰 헤더 검증 + 시크릿 URL 경로의 **이중 방식**을 서버에 넣어, 사용자 계정에 Request headers UI가 있으면 헤더로, 없으면 시크릿 경로로 연결한다 (§5).

## 3. v3 가정 vs 실코드·실측 대조 — 핵심 정정

| # | v3의 계획 | 실측 결과 | 귀결 |
|---|---|---|---|
| 1 | `core/memory_ops.py`·`core/schema.py`로 순수 로직 추출, `transports/`·`storage/`·`sync/`·`auth/` 디렉토리 재구조화 | **이미 그렇게 분리돼 있다.** `db.py`가 곧 core(레코드 검증·recall/search·rebuild, transport 무지), `memory_sync.py`가 곧 sync(push-on-record·pull-on-session·재시도), `config.py`가 곧 config. `mcp_server.py`는 얇은 도구 노출 계층 | **재구조화 불필요.** 대규모 파일 이동은 위험(설치본 경로·테스트 26종·플러그인 패키징 전부 영향)만 있고 얻는 게 없다 → **신규 진입점 1파일 추가**로 대체 (개정 제안 §4) |
| 2 | `transports/http_server.py` 신규 작성 | `mcp 1.28.1`(현행 고정 버전) FastMCP가 `run(transport="streamable-http")`, `host`/`port`/`stateless_http` 설정, `streamable_http_app()`(Starlette 앱 반환), uvicorn 동봉까지 **전부 내장** — 실측 확인 | HTTP 서버는 기존 `mcp_server.mcp` 인스턴스를 import해 감싸는 **~100줄 래퍼**로 충분 |
| 3 | `storage/remote_store.py` — 사용자별 워킹 디렉토리 격리 | 단일 사용자 셀프호스팅에선 서버 머신의 `~/.namu`가 곧 저장소. namu-35의 `NAMU_DATA_ROOT` 고정 상수 원칙과 정확히 합치 | **remote_store 불필요.** 클라우드 컨테이너 배포 시에도 "부팅 시 `~/.namu`를 사용자 repo에서 clone"하는 entrypoint 스크립트로 해결 — 저장 계층 코드는 무변경 |
| 4 | `sync/remote_git_sync.py` — push 실패 시 rebase 재시도 신규 구현 | `memory_sync._push()`에 이미 push 실패→pull(union merge)→재push 로직이 있고 라이브 검증됨 | **신규 구현 불필요.** 그대로 재사용 |
| 5 | `auth/selfhost_env_auth.py` | git 인증은 셀프호스팅 머신의 기존 git 자격증명(자기 PC) 또는 토큰 내장 remote URL(클라우드)로 충분. 새로 필요한 건 **HTTP 요청 인증**뿐 | git auth 모듈 불필요. HTTP 토큰 검증은 http_server 안의 ASGI 미들웨어 (§5) |
| 6 | 세션 시작 시 pull | HTTP에는 "세션 시작 훅"이 없다 (claude.ai가 대화마다 접속) | **디바운스 pull**로 대체: 도구 호출 시 마지막 pull에서 N초 경과 시에만 `sync_pull()` (§6) |

> v3의 "기존 CLI 경로는 한 줄도 바꾸지 않는다" 원칙은 그대로 유지된다 — 오히려 최소 변경안이 이 원칙을 더 강하게 지킨다.

## 4. 목표 아키텍처 (확정안)

```
namu-plugin/
├── mcp_server.py        ← 무변경. 도구 4종 + FastMCP 인스턴스 (stdio 진입점)
├── db.py                ← 무변경 (코어)
├── memory_sync.py       ← 무변경 (git sync)
├── config.py            ← 소폭 추가: NAMU_HTTP_* 환경변수 해석
└── http_server.py       ← 신규: 원격 HTTP 진입점 (PEP 723, ~100여 줄)
      ├─ mcp_server.mcp 를 import (도구 정의 재사용, 이중 구현 0)
      ├─ ASGI 미들웨어: 토큰 검증 + 시크릿 경로 검증 (§5)
      ├─ 디바운스 pull 훅 (§6)
      └─ uvicorn 구동 (host/port 환경변수)

scripts/ (또는 deploy/)
├── Dockerfile           ← 신규: 클라우드 셀프호스팅용 (python3.12 + git + uv)
└── entrypoint.sh        ← 신규: 부팅 시 ~/.namu clone/pull + git 자격 wiring → http_server 실행
```

- `http_server.py`가 `mcp_server`를 import하는 순간 기존 부팅 로직(`_ensure_db`, gitattributes 보정)이 그대로 실행된다 — 별도 초기화 코드 불필요.
- `NAMU_MACHINE`은 서버 배포 시 `web`(또는 `cloud-hp` 등)으로 지정해, 웹에서 기록된 교훈이 어느 경로로 들어왔는지 machine 필드로 식별되게 한다.

## 5. HTTP 인증 설계 (경로 B)

단일 사용자 전제. 두 방식을 **동시 지원**하고 환경변수로 켠다:

| 방식 | 환경변수 | 동작 | 사용 조건 |
|---|---|---|---|
| ① 토큰 헤더 | `NAMU_HTTP_TOKEN` | 요청의 `x-api-key` 또는 `Authorization: Bearer <t>`가 토큰과 불일치하면 401 | claude.ai 계정에 Request headers(베타) UI가 열려 있을 때 |
| ② 시크릿 경로 | `NAMU_HTTP_PATH_SECRET` | MCP 엔드포인트를 `/mcp/<secret>`로 노출. 경로 불일치 404 | 헤더 UI가 없어도 URL만으로 연결 가능 (HTTPS 전제라 경로는 암호화됨) |

- 둘 다 설정 시 둘 다 검사(AND 아님 — 경로가 맞으면 헤더 검사, 각자 켠 것만).
- 둘 다 미설정이면 **서버가 기동 거부** (무인증 공개 노출 방지). 로컬 테스트용 `NAMU_HTTP_ALLOW_NOAUTH=1` 탈출구만 둔다.
- 토큰 비교는 `hmac.compare_digest` (타이밍 공격 방지).
- HTTPS는 서버가 직접 하지 않고 터널/플랫폼(cloudflared, Railway 등)이 종단한다.

## 6. 동기화 설계

| 시점 | 동작 | 구현 |
|---|---|---|
| `namu_record` 직후 | push (커밋 메시지에 machine 포함) | **기존 그대로** — `memory_sync.sync_push()`가 이미 호출됨. sync_enabled 게이트(마커+.git)도 그대로 적용 |
| 읽기·쓰기 도구 호출 전 | **디바운스 pull** — 마지막 pull에서 `NAMU_HTTP_PULL_INTERVAL`(기본 60초) 경과 시에만 `sync_pull()` | http_server의 미들웨어 계층에서 처리. pull 후 yaml↔db 불일치는 기존 `_ensure_db()`(cache_is_stale)가 자동 재생성 |
| 동시 쓰기 충돌 (로컬 CC ↔ 웹) | push 실패 → pull(--no-rebase, union merge) → 재push 1회 | **기존 `_push()` 재시도 로직 그대로.** `.gitattributes`의 `merge=union` + ULID 키 덕에 learnings.yaml 충돌은 구조적으로 해소됨 |

pull을 매 요청마다 하지 않는 이유: git pull은 네트워크 왕복(0.5~2초)이라 도구 응답 지연이 체감된다. 교훈 데이터 특성상 60초 지연은 무해하다.

## 7. 배포 시나리오 (경로 B의 두 형태)

### 7-1. 자기 PC 상시구동 + 터널 — **1차 검증 대상 (권장 시작점)**

- hp(WSL)에서 `http_server.py` 기동 → cloudflared(또는 유사 터널)로 공개 HTTPS URL 확보 → claude.ai에 등록.
- 서버의 `~/.namu`는 **지금 쓰는 바로 그 데이터** — clone/bootstrap이 아예 필요 없고, 기존 git 자격증명 그대로 push/pull. 추가 배포물 0으로 전 구간(웹 연결→기록→PC 간 동기화)을 검증할 수 있다.
- 제약: PC가 꺼지면 웹에서 접속 불가. 상시성은 7-2로 해결.

### 7-2. 클라우드 컨테이너 (Railway/Fly.io/VPS)

- Dockerfile: python3.12-slim + git + uv, `namu-plugin/` 복사.
- entrypoint.sh: `NAMU_SYNC_REMOTE`(토큰 내장 HTTPS remote URL, 예: `https://x-access-token:<PAT>@github.com/user/repo.git`)로 `~/.namu` clone(이미 있으면 pull) → `.namu_sync` 마커·`.gitattributes` wiring(기존 `sync_setup` 함수 호출로 처리) → `http_server.py` 실행.
- 토큰은 배포 플랫폼의 환경변수(사용자 본인 인프라)에만 존재 — v3의 신뢰 모델 그대로.
- 컨테이너 재시작 시 로컬 상태가 날아가도 무해: 진실의 원천은 GitHub, SQLite는 재생성 캐시 (기존 원칙이 클라우드 무상태성과 정확히 맞물림).

## 8. 웹 사용 시 한계 고지 (문서화 필수)

- 레이어 B 부재: 자동 세션 브리핑·`/namu-task`·서브에이전트 없음. 웹 Claude가 recall을 스스로 부르게 하려면 **도구 description이 유일한 유도 수단** — 기존 docstring이 이미 "BEFORE starting a task" 등으로 작성돼 있어 그대로 노출된다.
- tasks(작업 상태) 도구는 노출하지 않는다 — tasks는 프로젝트 cwd 귀속 개념이라 웹 대화에는 대응 개념이 없다. 이번 스코프는 learnings 3종 + `namu_sync_setup` 제외(원격 서버에서 sync_setup은 entrypoint가 대신함) → **웹 노출 도구는 recall/record/search 3종**.

## 9. 구현 순서 (마이그레이션 계획)

1. **http_server.py + config 확장** — 무인증 로컬 모드로 기동, MCP Inspector·curl로 3종 도구 동작 확인. 기존 stdio 회귀 테스트 전체 통과 확인.
2. **인증 미들웨어** — 토큰 헤더·시크릿 경로·기동 거부 로직 + 단위 테스트.
3. **디바운스 pull** — 단위 테스트(시간 mock).
4. **hp 라이브 검증(7-1)** — 터널로 claude.ai 실제 연결, 웹에서 recall/record/search 호출 → `~/.namu` yaml에 기록·push까지 실측. 동시 쓰기(로컬 CC record ↔ 웹 record) 충돌 재시도 실측.
5. **Dockerfile + entrypoint(7-2)** — 로컬 docker로 빈 상태 부팅→clone→서빙 검증. (실 클라우드 배포는 사용자가 플랫폼 선택 후.)
6. **문서화** — README·가이드에 "설치형 / clone 개발형 / 셀프호스팅형" 3분류, 웹 한계(§8), 연결 절차(헤더 vs 시크릿 경로) 추가.

각 단계 완료 시 보고·게이트. 구현은 `/namu-task` 절차(recall→분할→코딩→검수→게이트→record)를 따른다.

## 10. 체크리스트

- [ ] `http_server.py` 신규 — 기존 FastMCP 인스턴스 재사용, stdio 경로 무변경
- [ ] 기동 거부(무인증 방지)·토큰 헤더·시크릿 경로 인증 + 테스트
- [ ] 디바운스 pull + 테스트
- [ ] 기존 테스트 전체 회귀 통과 (stdio 동작 불변 증명)
- [ ] MCP Inspector 로컬 검증
- [ ] claude.ai Custom Connector 실연동 (hp + 터널) — 3종 도구 호출 실측
- [ ] 로컬 CC ↔ 웹 동시 기록 충돌 재시도 실측
- [ ] Dockerfile/entrypoint — 빈 컨테이너 clone 부팅 검증
- [ ] 문서화 (3분류·웹 한계·연결 절차)

## 11. 스코프 제외 (이번에 하지 않는 것)

- 경로 A: 중앙 호스팅 + GitHub App (installation token) — 멀티유저 전제라 별도 태스크로.
- 멀티유저 격리·OAuth 2.1 서버 구현.
- tasks 도구의 웹 노출.

### 11-1. 경로 A 현재 구현 상태 (namu-54 시점)

위 "스코프 제외"는 이 문서(v4) 확정 시점의 결정이었지만, 그 이후 경로 A는 별도 태스크·별도 repo(`namu-cloud-routing`)로 **이미 라우팅까지는 구현·라이브**됐다.

- `?user=<키>` URL 쿼리로 사용자를 식별해 `STORE_ROOT/users/<키>/`로 라우팅하고, 개인용(경로 B)의 3도구(recall/record/search)를 그대로 미러링한다. `?client=`(via, 출처 태그)도 함께 이식됐다(v0.1.5~).
- 인증 방식은 개인용과 동일한 **공유 `path_secret`**이다 — 새 인증 체계를 도입한 게 아니라 기존 방식을 그대로 재사용한 것이다.
- **미완**은 '사용자별 인증'이다. 현재 `?user=`는 인증이 아니라 폴더 라벨(요청자가 임의로 지정할 수 있는 위조 가능한 쿼리 값)이다 — 그래서 공유 시크릿을 아는 사람이라면 남의 `user` 키를 그대로 지정해 그 서랍도 열 수 있다(협조적 격리). 이 상태로는 일반 공개에 부족하다. 사용자용 설명은 [`namu_cloud_guide.md`](https://github.com/onmiso-hash/namu-cloud-routing/blob/main/docs/namu_cloud_guide.md) 5절 참고(namu-54로 namu-cloud-routing repo로 이동).

### 11-2. 사용자별 인증(OAuth) 미래 설계 스케치

핵심 전환은 "신원이 어디에 담기는가"다. 지금은 신원이 URL 안에 있다 — 공유 `path_secret`(누구나 같은 값) + `?user=` 이름표(위조 가능한 쿼리 값이라 진짜 인증이 아니다). OAuth로 가면 신원이 URL에서 완전히 빠지고, **사용자별 토큰**(HTTP `Authorization: Bearer` 헤더)으로 옮겨간다.

- **접속 URL** — 모든 사용자가 같은 주소 하나(예: `https://namu-cloud.onnamu.kr/mcp`)를 쓴다. URL 안에는 비밀번호도, 누구인지도 들어가지 않는다. claude.ai에 이 주소를 등록하면 OAuth 로그인 창이 뜨고, 로그인하면 그 사람만의 토큰이 발급돼 claude.ai가 저장하며, 이후 매 요청에 자동으로 첨부된다.
- **라우팅** — 여전히 단일 컨테이너이고, 분기 방식만 바뀐다. 요청 도착(Bearer 토큰) → ① 토큰 검증(진위·만료) → ② 토큰에서 `user_id` 추출(지금의 `?user=` 자리를 대체) → ③ `users/<user_id>/`로 라우팅(지금과 동일한 폴더 분기, `_paths_for_user` 로직 그대로 재사용). 딱 하나 바뀌는 건 '누구'라는 정보의 출처다 — URL 쿼리(위조 가능) → 암호학적으로 검증된 토큰(위조 불가). 그래서 남의 서랍 접근이 구조적으로 차단된다.
- **토큰 발급 주체 2안**
  - (a) 서버(namu-cloud) 자신이 직접 authorization server 역할을 맡아 발급·검증.
  - (b) 외부 IdP(구글·GitHub 로그인 등)에 위임하고, 서버는 '외부 신원 → 서랍' 매핑만 관리.
  - 후자가 대체로 구현 부담이 작다(이 문서 §11에서 언급했던 GitHub App 방향이 이쪽에 가깝다). MCP는 streamable HTTP 전송에서 OAuth 2.1을 표준으로 지원한다 — 서버가 protected resource 역할을, `/.well-known` 메타데이터가 authorization server를 지정하는 구조다. claude.ai 커스텀 커넥터도 OAuth 플로우를 지원한다.
- **부수** — `?client=`(via, 출처 태그)는 보안 축이 아니라 '어느 AI가 남겼나'를 나타내는 별개 축이라, OAuth 도입 이후에도 쿼리로 그대로 남을 수 있다. 역할 분리는 그대로 유지된다: '누구'=토큰, '어느 AI'=`?client=`.

구현은 별도 태스크(사용자별 인증 계층 신설)로 유예된 상태다.
