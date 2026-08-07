# NAMU Plugin

NAMU 메모리 서버 + 오케스트레이션 스킬 + 세션 훅을 Claude Code / agy 플러그인으로 패키징한 것.

> **설치하려는 분은 이 문서가 아닙니다** → [설치하기](https://onmiso-hash.github.io/namu-agent/docs/install_guide.html).
> 이 문서는 이 폴더의 코드를 고치는 사람을 위한 구성 설명이다.

## 구성물

| 파일 | 역할 |
|------|------|
| `mcp_server.py` | FastMCP 메모리 서버. MCP 도구 7종(`namu_recall`/`namu_search`/`namu_record`/`namu_memo_remove`/`namu_task_pin`/`namu_task_unpin`/`namu_sync_setup`) 노출, stdio 전송 |
| `http_server.py` | 셀프호스팅용 HTTP 서버. 같은 코어를 원격에 노출하되 도구를 3종(`recall`/`record`/`search`)으로 제한한다(`HTTP_EXPOSED_TOOLS`) |
| `db.py` | `~/.namu/memory/learnings.yaml` ↔ SQLite 코어. 읽기(recall/search)는 conn 인자를 받고, 쓰기(record/init_db/rebuild)는 함수 내부에서 conn을 열고 닫는다 |
| `config.py` | 경로·`NAMU_MACHINE`·그릇 레지스트리(`BOWLS`)·기록 칸 정의(`FIELDS`) 일원화. 데이터 루트는 고정 상수 `NAMU_DATA_ROOT`(`~/.namu`, namu-35로 환경변수 분기 폐지). 기록 시각은 반드시 `cfg.now()` |
| `memo.py` | 쪽지 그릇(namu-56). 유일한 mutable 저장소이며 SQLite 색인을 하지 않는다 |
| `profile.py` | 개인 사실 그릇. `상시` 태그가 붙은 항목은 매 입력마다 재주입된다 |
| `memory_sync.py` | `~/.namu`의 선택적 git 자동 동기화(record 직후 auto push, 세션 시작 시 auto pull). `namu_sync_setup`으로 명시 활성화해야 동작. `.gitattributes` union 라인은 `config.BOWLS`에서 파생된다 |
| `task_resolve.py` | stdlib-only 활성 task 탐색(`log.md` 타임스탬프 기준 단일 출처). statusLine과 `session_context.py`가 공용으로 import |
| `record_input.py` | `namu_record`의 입력 정규화·검증과 도구 설명문 생성(`tool_description()`) |
| `session_context.py` | 세션 브리핑 마크다운 빌더(쪽지 + 열린 작업 + 최근 교훈). SessionStart/PreInvocation 훅이 재사용 |
| `hooks/session_recall.py` | Claude Code SessionStart 훅 — 세션 브리핑 주입 |
| `hooks/closing_guard.py` | Stop 훅 — "마무리해"인데 이번 세션에 `[다음]` 줄이 없으면 한 번 막는다(namu-62) |
| `hooks/prompt_reminder.py` | UserPromptSubmit 훅 — `상시` 태그가 붙은 개인 사실을 매 입력에 재주입 |
| `hooks/session_inject.py` | agy PreInvocation 훅 — 같은 내용을 agy 방식(ephemeralMessage)으로 주입 |
| `hooks/hooks.json` · `hooks.json`(루트) | 훅 등록 봉투 (Claude Code용 / agy용) |
| `skills/` | `namu-task`(오케스트레이션) · `namu-update`(원클릭 업데이트) · `statusline-setup`(하단 한 줄 연결) |
| `.mcp.json` · `mcp_config.json` | MCP 서버 등록 봉투 (Claude Code 절대경로 / agy 워크스페이스 상대경로) |
| `plugin.json` · `.claude-plugin/marketplace.json` | 플러그인 메타데이터 · 마켓플레이스 매니페스트 |
| `test_*.py` | pytest 단위 테스트 |

**훅 3종은 기록하지 않는다** — 알리고 막을 뿐이며, 판단과 `namu_record` 호출은 AI 몫이다.

## 필요 조건

- [uv](https://docs.astral.sh/uv/) — PEP 723 inline 메타데이터로 `mcp_server.py`가 의존성을 자급자족한다
- 데이터 루트는 고정 상수(`~/.namu`, `config.NAMU_DATA_ROOT`)다 — 지정할 환경변수가 없다
- `NAMU_MACHINE` — 현재 PC 식별자(미설정 시 호스트명, 그마저 없으면 `unknown`). 여러 PC를 쓴다면 명시 설정을 권장

## 개발용 설치

이 폴더 자체를 수정·검증할 때 쓰는 절차다. 로컬 경로를 마켓플레이스로 등록한다.

```
claude plugin marketplace add /path/to/namu-agent/namu-plugin
claude plugin install namu@namu-marketplace
```

agy는 `agy plugin install ./namu-plugin`. 설치 로그의
`agents: skipped (not found)`는 정상이다 — 워커 정의는 플러그인 봉투가 아니라
워크스페이스(`.claude/agents/`·`.agents/agents/`)에 두기로 했기 때문이다.

**설치본은 복사본이다.** GitHub 원격으로 설치한 상태라면 이 폴더를 고쳐도 반영되지
않는다 — 로컬 경로로 등록했을 때만 즉시 반영된다.

MCP 서버 수동 실행(디버그용):

```bash
uv run --script mcp_server.py
```

## 함께 볼 것

- [기억 설계도](https://onmiso-hash.github.io/namu-agent/docs/memory_architecture.html) — 다섯 그릇·3층 기록·원격 두 경로
- [`docs/memory_schema_v2.md`](../docs/memory_schema_v2.md) — 현행 기록 구조 설명서. **기록 관련 작업 전 반드시 읽을 것**
- [루트 README](../README.ko.md) — 폴더 구조·개발용 셋업·버전 bump 규율
