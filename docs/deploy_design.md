# NAMU 배포 형태 설계 — 플러그인 설치형 (2단계)

> 📅 2026-07-06~07 · #20 namu-20-deploy-design 결과물
> 설계(samsung)·실측(samsung+hp) 완료. 설치형 사용설명서(별건)의 토대.

NAMU가 "repo가 곧 NAMU_HOME"인 clone 기반을 벗어나, **임의 프로젝트에서 플러그인으로 설치해 쓰는 형태**의 3대 미결정 요소를 확정한다.

---

## 결정 ① 사용자 메모리 위치 — NAMU_HOME 3분기 폴백

`namu-plugin/config.py`가 데이터 루트(NAMU_HOME)를 다음 우선순위로 정한다:

1. **`NAMU_HOME` 환경변수** (.env 경유 포함) — 명시 지정, 항상 최우선
2. **`REPO_ROOT/memory`가 실재하면 `REPO_ROOT`** — repo를 클론해 직접 실행하는 하위호환(개발 기기)
3. **`~/.namu`** — 플러그인 설치형 기본값(분리 모드). 폴더는 첫 쓰기 시점에 자동 생성(스캐폴딩)

**근거** — 플러그인 캐시 폴더에는 `memory/`가 복사되지 않으므로, env 미설정 사용자가 캐시 안에 데이터를 쓰는 "유령 경로" 사고(#13·#16)를 분기 3이 방지한다. import 부수효과 0(스캐폴딩은 쓰기 함수의 `mkdir(parents=True)`가 담당).

**실측(hp, 2026-07-07)** — 플러그인을 repo 밖 가짜 캐시로 복사 + 가짜 HOME 환경에서:
- 분기 3 해석 확인 (`NAMU_HOME` → `$HOME/.namu`)
- 메모리 3층 전부 동작: `record`→`recall` 왕복(learnings.yaml append + FTS 히트), tasks 층(`find_active_task` + 세션 브리핑 생성), db 스캐폴딩

## 결정 ② 워커 정의 배포 — 플러그인 동봉 + 엔진별 폴더 분리

한 `agents/` 폴더를 양 엔진이 공용할 수 없음이 실측으로 판명(agy가 플랫 .md까지 통째 스캔해 깨진 정의 2벌 공존). 레이아웃을 분리한다:

| 경로 | 대상 엔진 | 형식 |
|------|----------|------|
| `namu-plugin/agents/<name>/agent.md` | agy 전용 | 하위폴더 + agent.md (YAML frontmatter) |
| `namu-plugin/cc-agents/<name>.md` + plugin.json `"agents"` 필드 | Claude Code 전용 | 플랫 .md, 필드가 자동 스캔을 **대체** (공식 문서 확답 + 라이브 확인: agy 전용 폴더가 CC에 안 뜸) |

**호출명 폴백 규칙 (namu-task 스킬, 2026-07-07 확정)** — CC는 플러그인 에이전트에 `namu:` 네임스페이스를 강제한다(`namu:namu-coder`). 스킬은 다음 규칙으로 호출한다:

- **Claude Code**: 에이전트 목록에 `namu-coder`(비네임스페이스)가 있으면 그대로(개발 repo — 프로젝트 `.claude/agents/`가 우선), 없으면 `namu:namu-coder`(설치형)
- **agy**: `namu-coder` 그대로 (네임스페이스 없음)

**namu_workers.yaml 부재 시(설치형)** — engine=`native` 간주하고 진행(기본 워커=현재 엔진 네이티브 서브에이전트, 추가 설정·비용 0). 파일이 있으면 override로 동작(기존 결정 유지).

**실측** — CC: hp 세션에서 `namu:namu-coder` 라이브 호출 성공(파일 생성 물증). agy: 설치 시 "agents: 2 processed", 하위폴더 정의만 인식.

## 결정 ③ agy repo 밖 실행 한계 — 실측 확정 목록

repo 밖 임시 워크스페이스 실측(hp, 2026-07-07, agy 1.0.16):

| 층 | 결과 |
|----|------|
| 스킬 (namu-task) | ✅ 로드 + 본문 접근 정상 |
| 훅 (세션 자동주입) | ✅ 정상, `NAMU_HOME` env 오버라이드 존중 |
| 워커 정의 | ✅ 설치 정상 ("agents: 2 processed") |
| MCP (대화형 세션) | ✅ `namu_recall`/`namu_search` 실호출 성공 (사용자 라이브 + 스크린샷 물증) |
| **MCP (`-p` 비대화 모드)** | ❌ **MCP 서버가 설정돼 있으면 세션 전체가 멈춤** (아래 함정 목록 참조) |

영향: NAMU 오케스트레이터는 대화형으로 돌므로 실사용 영향은 제한적. 단 `-p`를 쓰는 자동화(스크립트 경유 호출)는 불가 — 배포 문서에 명기할 것.

---

## ⚠️ 함정 목록 (배포 문서 기록 대상)

1. **agy `plugin install`은 비파괴 병합** — 소스에서 삭제한 파일이 설치본에 잔존한다. 정석 해법: **`agy plugin uninstall namu` → `agy plugin install <경로>`** (hp 실측으로 완전 청소 확인). 수동 잔재 삭제보다 안전.
2. **agy `-p`(비대화) 모드 + MCP = 멈춤** (1.0.16) — MCP 서버 기동을 시도만 하면 세션이 응답 없이 멈춘다(자체 print-timeout도 무시). 경로 방식(상대/절대)·권한 스킵(`--dangerously-skip-permissions`) 무관하게 재현. 서버 자체는 동일 조건 수동 부팅 1초 내 정상 → agy 쪽 문제. 대화형은 정상.
3. **agy MCP 경로는 cwd 상대** — 플러그인 동봉 `mcp_config.json`의 `namu-plugin/mcp_server.py`는 agy 실행 폴더 기준이라 repo 밖에선 해석 실패(조용히 스킵됨). `${extensionPath}`류 변수 미치환은 #16 실측과 동일. CC용 `.mcp.json`의 `${CLAUDE_PLUGIN_ROOT}`는 CC만 확장. → **해소(0.1.4)**: PreInvocation 훅(`session_inject.py`)이 매 실행마다 설치본 `mcp_config.json`을 기기 절대경로로 자동 교정한다(멱등, 개발 repo는 가드로 제외). 효과는 다음 세션부터 반영 — 재설치 후 수동 재주입 불필요.
4. **CC directory 소스 마켓플레이스는 소스 라이브 참조** — 설치 기록(installed_plugins.json)이 구버전이어도 최신 소스가 로드된다(hp 실측: 기록 0.1.1인데 0.1.2 에이전트 로드). 개발 기기는 **git pull + 재시작만으로 반영, 재설치 불필요**. 반면 원격(github) 마켓플레이스 설치는 캐시 복사라 update 필요 — 두 경우를 문서에서 구분할 것.
5. **agy 도구 스키마 캐시** — MCP 도구 정의가 `~/.gemini/antigravity-cli/mcp/<server>/*.json`에 캐시된다(대화형 실측서 관찰). 도구 시그니처 변경 시 갱신 여부 확인 필요.

## 설치·업데이트 절차 요약

| | Claude Code | agy |
|---|---|---|
| 설치 | marketplace 등록 후 plugin install (`namu@namu-marketplace`) | `agy plugin install <namu-plugin 경로>` |
| 업데이트 (개발 기기, directory 소스) | git pull + CC 재시작 | `uninstall → install` (비파괴 병합 함정, mcp_config 절대경로는 훅이 자동 교정) |
| 업데이트 (원격 설치) | plugin update | `uninstall → install` |
| 메모리 위치 | 기본 `~/.namu`, `NAMU_HOME` env로 변경 | 동일 (config.py 공용) |
| 기기 식별 | `NAMU_MACHINE` env (미설정 시 `unknown`) | 동일 |
