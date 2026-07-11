# NAMU Plugin

NAMU 메모리 서버 + 오케스트레이션 스킬 + 세션 훅을 Claude Code / agy 플러그인으로 패키징한 것.

## 구성물

| 파일 | 역할 |
|------|------|
| `mcp_server.py` | FastMCP 메모리 서버. MCP 도구 `namu_recall`/`namu_search`/`namu_record`/`namu_sync_setup` 노출, stdio 전송 |
| `db.py` | `~/.namu/memory/learnings.yaml` ↔ SQLite 코어. 읽기(recall/search)는 conn 인자를 받고, 쓰기(record/init_db/rebuild)는 함수 내부에서 conn을 열고 닫는다 |
| `config.py` | 경로·`NAMU_MACHINE` 일원화. 데이터 루트는 고정 상수 `NAMU_DATA_ROOT`(`Path.home() / ".namu"`, namu-35로 환경변수 분기 폐지) 하나뿐이며 learnings/db/tasks 경로가 여기서 산출된다, `load_dotenv` 호출 |
| `memory_sync.py` | `~/.namu`의 선택적 git 자동 동기화(record 직후 auto push, 세션 시작 시 auto pull). `namu_sync_setup`으로 명시 활성화해야 동작 |
| `task_resolve.py` | stdlib-only 활성 task 탐색(`log.md` 타임스탬프 기준 단일 출처). `scripts/namu_statusline.py`와 `session_context.py`가 공용으로 import |
| `session_context.py` | 세션 컨텍스트 마크다운 빌더(교훈 + 활성 task). SessionStart/PreInvocation 훅이 재사용 |
| `hooks/session_recall.py` | Claude Code SessionStart 훅 — 세션 시작 시 교훈+활성 task를 모델 컨텍스트로 자동 주입 |
| `hooks/hooks.json` | Claude Code SessionStart 훅 등록(`${CLAUDE_PLUGIN_ROOT}` 절대경로) |
| `hooks.json` (루트) | agy PreInvocation 훅 등록 — `session_inject.py` 호출, `namu` 네임스페이스로 래핑 |
| `hooks/session_inject.py` | agy PreInvocation 훅 — Claude Code 쪽과 동일 내용을 agy 방식(ephemeralMessage)으로 주입 |
| `skills/namu-task/SKILL.md` | `/namu-task` 오케스트레이션 스킬. 엔진별 워커 호출 방식을 분기한다(Claude Code=Agent 도구, agy=`invoke_subagent`/`send_message` 비동기 대기) |
| `.mcp.json` | Claude Code용 MCP 서버 자동 등록(`${CLAUDE_PLUGIN_ROOT}` 절대경로 봉투) |
| `mcp_config.json` | agy용 MCP 서버 등록(워크스페이스 상대경로 봉투) |
| `plugin.json` | 플러그인 메타데이터(name/version/description/repository) |
| `.claude-plugin/marketplace.json` | Claude Code 마켓플레이스 매니페스트(name/owner/plugins 필수) |
| `test_cache_stale.py` / `test_session_context.py` / `test_task_resolve.py` | pytest 단위 테스트 |

## 필요 조건

- [uv](https://docs.astral.sh/uv/) — PEP 723 inline 메타데이터로 `mcp_server.py`가 의존성을 자급자족한다
- 데이터(learnings/db) 루트는 namu-35로 고정 상수(`~/.namu`, `config.NAMU_DATA_ROOT`)가 됐다 — 지정할 환경변수가 없다.
- `NAMU_MACHINE` 환경변수 — 현재 PC 식별자(미설정 시 호스트명, 그마저 없으면 `unknown` 폴백, 상태 파일 매칭이 깨질 수 있어 명시 설정 권장)

환경변수 설정 방법은 루트 [`README.md`](../README.md#환경변수)를 참고할 것.

## 설치 절차 (실측)

### Claude Code

repo를 clone한 로컬 경로 기준으로 등록한다:

```
/plugin marketplace add /path/to/namu-agent/namu-plugin
/plugin marketplace update
/reload-plugins
```

코드 수정 후 재적용(설치 스코프가 local이므로 `--scope local`을 맞춘다):

```
claude plugin update namu@namu-marketplace --scope local
```

### agy

```
agy plugin install ./namu-plugin
```

설치 로그에 `agents: skipped (not found)`가 뜨는 것은 정상이다 — 플러그인 봉투에 agents 카테고리를 넣지 않기로 결정했기 때문이다(워커 정의는 워크스페이스 `.claude/agents/`/`.agents/agents/`에 따로 둔다. 이유는 루트 README [폴더 구조](../README.md#폴더-구조) 참고).

### 설치본은 복사본 — 재설치 필요

Claude Code·agy 모두 설치 시 이 폴더의 파일을 **별도 위치로 복사**한다. `namu-plugin/` 안의 코드를 고쳐도 재설치·업데이트하기 전까지는 옛 코드가 계속 실행되니 주의할 것. 상세는 루트 README [셋업 함정](../README.md#셋업-함정) 4번 참고.

### MCP 서버 수동 실행 (디버그용)

```bash
uv run --script mcp_server.py
```

## 함께 볼 것

플랫폼별 인코딩(cp949)·터미널 렌더·agy 상대경로 등 실제로 부딪힌 함정은 루트 [`README.md`](../README.md#셋업-함정)의 셋업 함정 섹션에 정리돼 있다.
