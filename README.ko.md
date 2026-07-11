# NAMU Agent System

English: [README.md](README.md)

벤더 독립 에이전트 시스템. 특정 AI 벤더에 종속되지 않고, 이식 가능한 메모리 코어를 중심으로 작업 기록과 교훈을 누적해 스스로 학습한다.

## 정체성

NAMU의 차별점은 실행 엔진이 아니라 **메모리 레이어(MCP)**에 있다. 실행 엔진(Claude Code, agy)은 빌려 쓰고 언제든 교체할 수 있는 부품으로 취급한다.

이 원칙은 "봉투 둘, 내용물 하나" 구조로 구현된다 — 같은 메모리 코어(`mcp_server.py`), 같은 워커 정의(`namu-coder`/`namu-reviewer`), 같은 오케스트레이션 스킬(`/namu-task`)을 Claude Code와 agy 두 엔진이 그대로 공유한다. 다른 건 각 엔진이 요구하는 등록 형식(봉투)뿐이다 — 예를 들어 MCP 서버 등록도 내용은 같지만 Claude Code는 `${CLAUDE_PLUGIN_ROOT}` 절대경로 플러그인 봉투(`.mcp.json`)를, agy는 워크스페이스 상대경로 봉투(`mcp_config.json`)를 쓴다.

## 아키텍처 개요

- **learnings.yaml** — append-only 진실의 원천. `~/.namu/memory/learnings.yaml` 하나에 쌓이며(namu-35: 개발 repo에서 실행해도 예외 없이 같은 경로), `namu_sync_setup`으로 준비한 사용자 개인 원격 repo로 여러 PC에 동기화된다(선택 기능).
- **SQLite(FTS5) 검색 캐시** — `learnings.yaml`을 인덱싱한 재생성 가능한 로컬 캐시. gitignore 대상이며, `git pull` 후 yaml↔db 항목 수 불일치를 감지하면 서버 부팅 시 자동으로 재생성된다.
- **tasks/ 상태 3파일** — `task.md`(불변 목적) / `context.<machine>.md`(기기별 현재 스냅샷, 재생성 가능한 뷰) / `log.md`(append-only 원본, 권위 있는 기록).
- **MCP 도구 3종** — `namu_recall`(최근 교훈 조회), `namu_search`(FTS5 키워드 검색, 3자 미만은 LIKE 폴백), `namu_record`(교훈 기록, `reason` 필수). recall/record는 오케스트레이터만 호출하고 워커는 메모리에 직접 쓰지 않는다.
- **워커 층** — `namu-coder`/`namu-reviewer` 서브에이전트가 각 엔진 네이티브 형식(Claude Code `.claude/agents/*.md`, agy `.agents/agents/*/agent.md`)으로 이중 존재하되 시스템 프롬프트 내용은 동일하다. 오케스트레이션은 `/namu-task` 스킬(`namu-plugin/skills/namu-task/SKILL.md`)이 맡으며, 엔진별로 호출 방식만 분기한다(Claude Code=Agent 도구, agy=`invoke_subagent`/`send_message` 비동기 대기).
- **세션 표면** — 세 층이 공존한다.
  - **statusLine**: 세션 내내 하단에 상시 표시되는 한 줄(`[모델] namu-agent | 📌 task · 제목 | 컨텍스트%`). `scripts/namu_statusline.py` 공용 스크립트를 양 엔진 설정에 등록.
  - **`/namu`**: 사용자가 직접 호출하는 세션 브리핑 슬래시 명령. 활성 task의 진행 이력·다음 할 일·최근 교훈 4블록을 화면에 출력하는 읽기 전용 명령(Claude Code `.claude/commands/namu.md`, agy `.agents/skills/namu/SKILL.md`).
  - **자동 컨텍스트 주입**: Claude Code SessionStart 훅 / agy PreInvocation 훅이 세션 시작 시 교훈+활성 task를 모델 컨텍스트로 조용히 주입한다(Claude Code 2.1.0+ 사양상 화면에는 표시되지 않고 모델만 받는다 — 화면 가시성은 statusLine과 `/namu`가 담당).

## 폴더 구조

| 폴더 | 역할 |
|------|------|
| `namu-plugin/` | 현역 코드 — MCP 메모리 서버(`mcp_server.py`), 코어 로직(`db.py`), 설정(`config.py`), 활성 task 탐색(`task_resolve.py`), 세션 컨텍스트 빌더(`session_context.py`), 훅(`hooks/`), 오케스트레이션 스킬(`skills/namu-task/`). Claude Code·agy 양쪽에 설치되는 플러그인 봉투 본체 |
| `.claude/` | Claude Code 전용 글루 — 네이티브 서브에이전트(`agents/namu-coder.md`, `namu-reviewer.md`), 세션 브리핑 슬래시 명령(`commands/namu.md`), 로컬 설정(`settings.local.json`) |
| `.agents/` | agy 전용 글루 — 네이티브 서브에이전트(`agents/namu-coder/agent.md`, `namu-reviewer/agent.md`), 세션 브리핑 스킬(`skills/namu/SKILL.md`). PC별 등록 파일(`hooks.json`·`mcp_config.json`)은 gitignore 대상 |
| `scripts/` | 두 엔진이 공유하는 stdlib-only 스크립트 — `namu_statusline.py`(상태줄), `namu_active_task.py`(`/namu` 활성 task 선정) |

이 repo에는 `memory/`·`tasks/`·`db/` 폴더가 없다(namu-34·namu-35로 폐지). 교훈(learnings)·검색 캐시(db)는 항상 개인 풀 `~/.namu/memory/`·`~/.namu/db/`에, 작업 상태(tasks)는 `~/.namu/tasks/<basename(프로젝트 폴더)>/`에 쌓인다 — repo가 어디에 있든, 이 repo 자체를 개발 중이든 상관없다.

워커 정의(`.claude/agents/`, `.agents/agents/`)는 의도적으로 플러그인 봉투에 동봉하지 않는다. 이 repo 자체를 `git pull`만 하면 멀티 PC에 자동 배포되고, 세션 중 파일을 고쳐도 재시작 없이 다음 호출에 즉시 반영되는 핫 리로드가 실측됐기 때문이다(반면 플러그인 설치본은 복사본이라 재설치가 필요하다 — 아래 셋업 함정 참고).

## 셋업 가이드

> 아래는 이 repo를 clone해 개발하는 형태의 가이드다. 자기 프로젝트에 NAMU를 플러그인으로 설치해 쓰려면 [설치형 사용설명서](docs/install_guide.md)를, 설치를 마친 뒤 실제 사용법은 [사용설명서 — 설치 후 첫 하루](docs/usage_guide.md)를 참고할 것.

### 필요조건

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — PEP 723 inline 의존성으로 플러그인이 자급자족
- SQLite ≥3.34 (FTS5 지원)
- git

### 환경변수

데이터 루트(`~/.namu`)는 namu-35로 **고정 상수**(`NAMU_DATA_ROOT`)가 됐다 — 지정하거나 바꿀 환경변수가 없다. 남은 건 하나뿐이다.

- `NAMU_MACHINE` — 현재 PC 식별자. 미설정 시 호스트명으로 자동 폴백되며(그마저 없으면 `unknown`), 이 값이 여러 PC에서 어긋나면 `context.<machine>.md` 매칭이 깨질 수 있어 명시 설정을 권장한다.

**Linux/WSL** — 셸 프로파일(`~/.bashrc`, `~/.zshrc` 등)에 추가:

```bash
export NAMU_MACHINE="my-pc"
```

**Windows** — PowerShell은 `.bashrc`를 읽지 않으므로 사용자 환경변수로 영구 등록한다:

```powershell
[Environment]::SetEnvironmentVariable("NAMU_MACHINE", "my-pc", "User")
```

### Claude Code 설치

이 repo를 clone한 로컬 경로 기준으로 등록한다:

```
/plugin marketplace add /path/to/namu-agent/namu-plugin
/plugin marketplace update
/reload-plugins
```

이후 `namu-plugin/` 코드를 수정했다면 업데이트로 다시 반영한다(설치 스코프가 local이므로 `--scope local`을 맞춘다):

```
claude plugin update namu@namu-marketplace --scope local
```

### agy 설치

```
agy plugin install ./namu-plugin
```

### statusLine 등록 (양 엔진 공용)

Claude Code와 agy는 **서로 다른 설정 파일**을 쓴다. 한쪽만 등록하면 다른 쪽은 계속 비어 있으므로 양쪽 모두 `scripts/namu_statusline.py`를 등록해야 한다.

```json
"statusLine": {
  "type": "command",
  "command": "python -X utf8 /path/to/namu-agent/scripts/namu_statusline.py",
  "enabled": true
}
```

## 셋업 함정

실제로 부딪혔던 4가지 함정이다. 특히 비영어권 Windows 환경이라면 1·2번을 먼저 읽을 것.

**1. 한글(비영어권) Windows 네이티브: cp949 이모지 인코딩으로 statusLine이 죽는다**
한글 Windows의 기본 코드페이지는 cp949다. Claude Code가 statusLine 스크립트를 파이프로 호출하면 stdout이 cp949로 강제되는데, 스크립트가 출력하는 이모지(📌 등)를 cp949가 인코딩하지 못해 `UnicodeEncodeError`로 스크립트가 죽고 하단 바가 비어 보인다. 반면 같은 스크립트를 터미널에서 직접 실행하면 멀쩡히 잘 나온다 — 터미널은 stdout이 UTF-8이지만, 엔진이 부르는 파이프는 시스템 locale(cp949)을 따르기 때문이다. 처방은 `python -X utf8`(또는 `PYTHONIOENCODING=utf-8`)로 파이썬 UTF-8 모드를 강제하는 것이며, 위 설치 절차의 statusLine 등록 예시에 이미 반영돼 있다.

**2. 구식 conhost 터미널: 이모지가 `�`로 깨진다 (인코딩 문제 아님)**
statusLine이 뜨긴 뜨는데 이모지 자리가 깨진 글자(`�`)로 나온다면, 이건 인코딩이 아니라 **터미널 렌더링** 문제다. 구식 conhost 창은 컬러 이모지를 못 그린다. Windows Terminal이나 VS Code 통합 터미널을 쓰면 즉시 해결된다.

**3. agy 플러그인 봉투는 워크스페이스 상대경로 기반 — repo 밖에서 실행하면 한계가 있다**
agy 플러그인 봉투(`mcp_config.json`/`hooks.json`)는 `${extensionPath}` 같은 변수 치환이 정상 동작하지 않아 워크스페이스 상대경로(`namu-plugin/mcp_server.py` 등)로 등록돼 있다. 즉 agy가 이 repo를 워크스페이스로 열어야만 경로가 맞는다. repo를 워크스페이스로 열어서 실행할 것.

**4. 플러그인 설치본은 복사본 — `namu-plugin/` 수정 후 반드시 재설치/업데이트해야 반영된다**
Claude Code(`claude plugin update ...`)와 agy(`agy plugin install ./namu-plugin`) 모두 설치 시 파일을 별도 위치로 **복사**한다. 따라서 `namu-plugin/` 안의 코드를 고쳐도 재설치·업데이트 전까지는 옛 코드가 계속 실행된다. 반대로 워크스페이스 파일인 워커 정의(`.claude/agents/`, `.agents/agents/`)는 `git pull`만으로 자동 로드되고, 세션 중 수정도 재시작 없이 즉시 반영되는 핫 리로드를 지원한다 — 재설치가 필요 없다.

## 로드맵

- **1단계 (현재):** 개인용 시스템 완성
- **2단계:** 공개 배포 + 개인 메모리 연동
- **3단계:** 공개 메모리 풀 (커뮤니티 집단지성, 선택적 기여/구독)
