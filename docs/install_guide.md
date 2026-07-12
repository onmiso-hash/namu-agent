# NAMU 설치형 사용설명서

> 📅 2026-07-08 · docs/deploy_design.md(#20) 실측 결과를 사용자 관점으로 정리한 문서.

이 문서는 NAMU repo를 clone해 개발하는 게 아니라, **자기 임의 프로젝트에 NAMU를 플러그인으로 설치해 쓰려는 사용자**를 위한 것이다. clone 기반 개발 환경을 원한다면 루트 [`README.ko.md`](../README.ko.md)의 셋업 가이드를 따를 것. 설치를 마쳤다면 다음 단계로 [사용설명서 — 설치 후 첫 하루](usage_guide.md)를 볼 것.

> 🚀 **복사·붙여넣기만으로 빠르게 끝내고 싶다면** — 단계별 [빠른 시작 가이드(초보자용, HTML)](namu_quickstart.html)를 먼저 보라. 이 문서는 그보다 상세한 배경·함정·선택 기능까지 다룬다.

> **독자 전제** — NAMU repo(`onmiso-hash/namu-agent`)는 공개(public) repo다. 누구나 별도의 초대나 특별한 git 자격증명 없이 이 문서를 따라 설치할 수 있다.

## 1. 개요 — 설치형 vs clone 개발형

NAMU는 두 가지 방식으로 쓸 수 있다.

- **clone 개발형** — NAMU repo를 그대로 clone해서 그 repo 안에서 실행한다. `namu-plugin/` 코드를 고치면 재설치 없이 바로 반영된다(단, agy는 워크스페이스로 이 repo를 열어야 함). 이 형태는 루트 [`README.ko.md`](../README.ko.md)의 셋업 가이드를 참고할 것.
- **설치형** — NAMU repo와 무관한 자기 프로젝트에서, `namu-plugin/`을 Claude Code나 agy에 **플러그인으로 설치**해 쓴다. 이 문서가 다루는 대상이다. 설치본은 원본의 **복사본**이라는 점이 clone형과의 핵심 차이다(아래 함정 참고).

두 형태 모두 같은 메모리 코어(`mcp_server.py`)·같은 워커 정의·같은 오케스트레이션 스킬을 공유한다("봉투 둘, 내용물 하나"). 다른 건 등록 형식(봉투)뿐이다 — **데이터(교훈·작업 상태)가 저장되는 위치는 두 형태가 완전히 동일하다**(namu-35: `NAMU_HOME` 환경변수·"개발 모드/설치 모드" 데이터 분기 자체가 폐지됐다. 상세는 3절 참고).

## 2. 사전 준비

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — `mcp_server.py`가 PEP 723 inline 메타데이터로 의존성을 자급자족하므로 별도 pip install이 필요 없다.
- (선택) **환경변수**
  - `NAMU_MACHINE` — 현재 기기를 식별하는 이름(예: `my-laptop`). 미설정 시 호스트명으로 자동 폴백되며(그마저 없으면 `unknown`), 여러 PC를 오가며 쓸 경우 `context.<machine>.md` 매칭이 어긋날 수 있어 명시 설정을 권장한다.

## 3. 메모리(기억)가 저장되는 위치

NAMU의 데이터 루트는 **`~/.namu` 고정**이다(`config.py`의 상수 `NAMU_DATA_ROOT = Path.home() / ".namu"`). 지정하거나 바꿀 수 있는 환경변수가 없다 — clone 개발형에서 이 repo 안에서 실행하든, 설치형으로 전혀 다른 프로젝트에서 실행하든 항상 이 한 경로다. 이 폴더는 미리 만들 필요 없이, 교훈을 처음 기록하는 시점에 자동으로 생성(스캐폴딩)된다.

**왜 이렇게 고정됐는가(namu-35)** — 예전에는 `NAMU_HOME` 환경변수 → repo `memory/` 실재 시 그 repo 경로 → `~/.namu` 순의 3분기 폴백이 있었다. 플러그인 캐시 폴더에는 `memory/`가 복사되지 않으므로, 이 분기 자체가 없으면 사용자가 실수로 캐시 폴더 안에 데이터를 쓰는 "유령 경로" 사고(#13·#16)가 날 위험이 있어 폴백 순서로 막아왔다. 그런데 "움직이는 포인터(환경변수)+안전장치(폴백·하드가드)" 구조 자체가 사고 원인이었다는 재검토 끝에, **포인터를 아예 없애 고정 상수로 만들면 안전장치도 필요 없어진다**는 결론에 이르렀다(tasks가 #34로 이미 같은 방식 `~/.namu` 고정으로 검증됨). 설치 시 데이터 위치를 사용자가 지정하는 기능도 의도적으로 만들지 않는다(옵션은 추가는 쉽지만 회수는 어렵다는 판단).

## 4. Claude Code에 설치

### 4-1. 로컬 경로(directory) 마켓플레이스 등록 — 실측 절차

지금 확정된 절차는 **로컬 디스크에 있는 `namu-plugin` 폴더 경로**를 마켓플레이스로 등록하는 방식이다.

```
/plugin marketplace add /path/to/namu-plugin
/plugin marketplace update
/reload-plugins
```

`namu-plugin` 폴더 자체가 필요하다는 뜻이다. 이 폴더를 손에 넣는 경로는 두 가지로 확정돼 있다.

- **(a) repo를 clone해서 그 안의 `namu-plugin/`을 쓴다** — 이 경우가 여기 4-1절 대상이다.
- **(b) 4-2절의 GitHub 원격 마켓플레이스 설치를 쓴다** — 이 경우 `namu-plugin` 폴더를 로컬에 미리 마련할 필요가 아예 없다(CC/`claude` CLI가 clone·설치를 대신 처리한다).

참고로 (a) 방식은 **소스를 라이브 참조**한다 — 설치 기록이 구버전이어도 실제로는 최신 소스가 로드된다. 따라서 소스 폴더를 최신화(예: `git pull`)하고 CC를 재시작하기만 해도 반영되며, 재설치는 필요 없다.

### 4-2. GitHub 원격 마켓플레이스 설치 — 실측 확정 절차

**전제** — repo 루트에 `.claude-plugin/marketplace.json`(namu-plugin을 가리키는 봉투)이 있어야 한다. NAMU repo는 커밋 `e2fba2e`부터 이 봉투를 포함한다. 이게 없으면 clone 자체는 성공해도 `Marketplace file not found at ...\.claude-plugin\marketplace.json` 에러로 등록이 실패한다.

```
claude plugin marketplace add onmiso-hash/namu-agent
claude plugin install namu@namu-marketplace
```

(또는 CC 대화 세션 안에서 `/plugin marketplace add onmiso-hash/namu-agent`도 동일하게 동작한다.) 설치 스코프는 기본 **user**. repo가 공개(public)이므로 별도 초대나 git 자격증명 없이 바로 clone·설치가 된다.

**실측 물증(2026-07-08, samsung, CC v2.1.204)** — `installed_plugins.json`에 `version 0.1.5`·`gitCommitSha=e2fba2e`가 기록돼 GitHub발 설치임이 확인됐고, repo 밖 폴더에서 `claude mcp list` → `plugin:namu:namu-memory ✔ Connected`, 새 세션에서 MCP 3도구·statusLine 정상 동작(라이브 스크린샷 물증)까지 확인됨.

원격 설치는 로컬 directory 소스와 달리 **캐시 복사** 방식이다(`~/.claude/plugins/cache/<marketplace>/<plugin>/<버전>/`에 플러그인 폴더만 복사돼 실행됨). 따라서 소스 갱신만으로는 반영되지 않고 별도 update 절차(7절 참고)가 필요하다.

## 5. agy(Antigravity)에 설치

```
agy plugin install <namu-plugin 경로>
```

설치가 끝나면 agy용 MCP 등록(`mcp_config.json`)은 워크스페이스 상대경로 기반이라, agy가 이 플러그인이 필요한 데이터 경로를 실행 시점에 절대경로로 자동 교정해준다(PreInvocation 훅). 다만 **재설치 직후 첫 세션**에는 이 교정이 아직 한 번도 돌지 않아 `/mcp`가 정상으로 안 보일 수 있다.

이 문제를 포함해 재설치·업데이트를 한 번에 안전하게 처리하는 스크립트가 `namu-plugin/scripts/agy_reinstall.ps1`이다.

```powershell
namu-plugin/scripts/agy_reinstall.ps1
```

내부적으로 다음 3단계를 순서대로 실행한다.

1. `agy plugin uninstall namu` — agy의 `plugin install`은 비파괴 병합이라, 소스에서 지운 파일이 설치본에 그대로 남는다. 완전히 청소하려면 반드시 먼저 지워야 한다.
2. `agy plugin install <경로>` — 재설치.
3. 설치본 훅을 `--heal` 모드로 즉시 실행 — `mcp_config.json`을 그 자리에서 절대경로로 교정해, 첫 세션부터 `/mcp`가 바로 동작하도록 만든다.

수동으로 하려면 `uninstall → install → --heal` 순서를 그대로 따르면 된다.

## 6. 교훈 원격 백업·멀티 PC 동기화 (선택, 0.1.11부터)

설치형 `~/.namu`는 기본적으로 그 기기의 로컬 폴더일 뿐이다 — 디스크가 죽으면 기억도 죽고, 여러 PC를 쓰면 기기마다 따로 쌓여 합쳐지지 않는다. 이 절은 그 한계를 없애는 선택 기능(MCP 도구 `namu_sync_setup`, 구현은 `namu-plugin/memory_sync.py`)을 설명한다. **명시적으로 켜지 않으면(마커 파일 없음) 이 절 이전과 동일하게 로컬 저장만 된다.**

### 켜는 법

1. GitHub 등에 **비공개 원격 저장소**를 하나 준비한다(사용자 몫). "준비"의 범위는 세 가지: ① 계정(GitHub 외 GitLab·사내 git 서버 등 git URL이 나오는 곳 전부 가능) ② 빈 비공개 저장소 생성(이름 자유, **Private**, README 등 초기화 없이 — 교훈에 프로젝트 내용이 그대로 담기므로 비공개 필수, GitHub은 비공개도 무료) ③ 그 기기의 git 인증(`gh auth login` 또는 SSH 키 — push 시 비밀번호를 묻지 않는 상태, `gh auth status`로 확인). 여기까지가 사용자 몫이고, NAMU는 로컬 쪽 git 연결만 대신한다.
2. AI에게 "`namu_sync_setup`을 `<원격 URL>`로 실행해줘"라고 부탁한다(MCP 도구 직접 호출). 한 번만 하면 된다.

`namu_sync_setup`이 하는 일: `~/.namu`에 `git init`(이미 있으면 스킵) → `.gitignore`에 `db/` 추가(검색 캐시는 동기화 대상이 아님) → `.gitattributes`에 `memory/learnings.yaml merge=union` 추가(여러 PC의 append-only 기록이 충돌 없이 합쳐지도록) → 원격 `origin` 등록 → 마커 파일(`.namu_sync`) 생성 → 초기 커밋·push 순으로 진행된다.

### 켠 뒤 동작

- `namu_record` 성공 직후 자동으로 `git add memory/` → (변경 있으면) `commit` → `push`한다. push 실패는 `namu_record`의 반환 결과에 영향을 주지 않는다(기록 자체는 항상 yaml/SQLite에 먼저 성공한다).
- Claude Code(`session_recall.py`)·agy(`session_inject.py`) 세션 시작 훅 공통으로 `_ensure_db` 직전에 자동 `git pull`한다. 받아온 yaml이 SQLite 캐시보다 최신이면(항목 수 불일치) 기존 `cache_is_stale` 로직이 자동으로 db를 재생성한다.
- 두 번째 이후 PC 온보딩: **클론이 아니라** 완전히 빈 `~/.namu`에서 같은 `namu_sync_setup`을 부르면, 로컬 초기 커밋과 원격의 기존 역사가 공통 조상이 없는 상태(unrelated histories)라도 `git fetch` 후 `merge --allow-unrelated-histories`(1회성 온보딩 전용 — 평상 운영의 `sync_pull`/`sync_push`에는 이 플래그를 쓰지 않는다)로 자동 흡수한 뒤 push한다. `merge=union` 덕에 `learnings.yaml` 내용이 충돌 없이 합쳐진다.
- 실패(오프라인·인증 만료·원격 미준비 등)는 세션 시작·`namu_record`를 절대 막지 않고 예외 없이 무음 처리된다. 사유 1줄이 `~/.namu/db/sync.log`에 남는다(`session_context.py`의 `git_check.log`와 같은 물증 로그 패턴).
- 끄기 스위치: 환경변수 `NAMU_SYNC=0`.
- namu-35로 데이터 루트가 `~/.namu` 고정 상수가 되면서 "clone 개발형 repo를 가리킬 수 있는 포인터" 자체가 사라졌다 — 그래서 예전에 있던 "clone 개발형이면 `namu_sync_setup`을 거부하는 하드가드"는 지킬 대상이 없어져 삭제됐다. clone 개발형에서 실행해도 설치형과 동일하게 `~/.namu`를 대상으로 동작한다.

**"완전 무인 백업"은 아니다** — 원격 저장소 준비·git 인증은 여전히 사용자 책임이고, 인증이 깨지면 무음으로 로컬에만 기억이 계속 쌓인다(위 `sync.log` 확인이 유일한 단서).

## 7. 업데이트

플러그인 코드가 바뀌었을 때 반영하는 절차는 **설치 방식에 따라 다르다.**

| | Claude Code | agy |
|---|---|---|
| **directory(로컬 경로) 소스** — 소스를 라이브 참조 | `git pull`(또는 소스 폴더 갱신) + CC 재시작만으로 반영. 재설치 불필요 | `namu-plugin/scripts/agy_reinstall.ps1` 실행(수동: `uninstall → install → --heal`) |
| **원격(GitHub) 설치** — 캐시 복사 | `claude plugin update namu@namu-marketplace` + CC 재시작. **반드시 `이름@마켓플레이스` 전체 식별자**로 — 짧은 이름(`update namu`)은 "not found"로 실패한다(실측: 0.1.5→0.1.6 버전·커밋 sha 반영 확인, 2026-07-08) | `namu-plugin/scripts/agy_reinstall.ps1` 실행(수동: `uninstall → install → --heal`) |

핵심 구분: directory 소스는 "라이브 참조"라서 소스만 최신화하면 끝나지만, 원격/캐시 기반 설치는 캐시가 낡은 채로 남으므로 명시적인 update 동작이 필요하다.

**update 후 statusLine 체크** — 캐시 경로에는 플러그인 버전이 박혀 있어, update로 버전 폴더가 바뀌는 순간 statusLine이 에러 표시 없이 조용히 사라진다. update 직후 대화창에서 `/namu:statusline-setup`을 다시 호출하면 새 버전 경로로 자동 갱신된다(namu-36부터 기본 절차, usage_guide 5절). 스킬을 못 쓰는 환경이라면 `settings.json`의 statusLine 경로 속 버전을 수동으로 갱신할 것(usage_guide 5절 폴백 참고).

## 8. 워커(서브에이전트)

NAMU는 `namu-coder`/`namu-reviewer` 같은 워커를 오케스트레이션 스킬(`/namu-task`)이 호출해 실제 구현·검수를 맡긴다.

- **`namu_workers.yaml`이 없으면** — `engine=native`로 간주하고, **현재 실행 중인 엔진의 네이티브 서브에이전트**를 그대로 쓴다. 추가 설정도, 추가 비용도 들지 않는다. 설치형 사용자 대부분은 이 기본 동작으로 충분하다.
- **파일이 있으면(repo 루트 `namu_workers.yaml`)** — 워커 이름별로 두 키를 갖는다.

  ```yaml
  coder:
    engine: native          # native | ollama | gemini_paid | claude_api (MVP는 native만 구현)
    agent: namu-coder       # native일 때 쓸 서브에이전트 이름
  reviewer:
    engine: native
    agent: namu-reviewer
  ```

  - `engine` — 워커를 어느 엔진에 맡길지. **현재 구현된 값은 `native`뿐**이며, `ollama`/`gemini_paid`/`claude_api`는 스키마상 예약된 값일 뿐 아직 동작하지 않는다. `engine`이 `native`가 아니면 오케스트레이션(`/namu-task`)이 이를 감지해 **사용자에게 알리고 진행을 멈춘다**(아직 대체 엔진 호출 로직이 없기 때문).
  - `agent` — `engine: native`일 때 호출할 서브에이전트 이름.
  - **워커가 실제로 쓰는 AI 모델**은 이 yaml이 아니라 서브에이전트 정의 파일의 frontmatter `model:` 값이 정한다. 개발 repo에서는 `.claude/agents/namu-coder.md`(`model: sonnet`)·`.claude/agents/namu-reviewer.md`(`model: haiku`)가, 플러그인 설치본에서는 `namu-plugin/cc-agents/`의 동일 파일이 이 역할을 한다. 모델을 바꾸고 싶으면 `namu_workers.yaml`이 아니라 이 frontmatter를 수정해야 한다.
- 호출명은 엔진에 따라 자동으로 갈린다 — Claude Code는 플러그인 에이전트에 `namu:` 네임스페이스가 붙고(예: `namu:namu-coder`), agy는 네임스페이스 없이 그대로(`namu-coder`) 불린다. 사용자가 직접 신경 쓸 부분은 아니다.

## 9. 함정·제한 사항

설치형 환경에서 실측으로 확인된 함정이다. 인코딩(cp949)·구식 conhost 터미널·agy 워크스페이스 상대경로·"설치본은 복사본" 같은 공통 함정은 루트 README의 [셋업 함정](../README.ko.md#셋업-함정) 4종과 겹치므로 그쪽을 참고하고, 여기서는 **설치형에서만 두드러지는 함정**만 적는다.

1. **agy `plugin install`은 비파괴 병합** — 소스에서 삭제한 파일이 설치본에 그대로 남는다. 반드시 `agy plugin uninstall namu` 후 `install`해야 완전히 청소된다(5절 `agy_reinstall.ps1` 참고).
2. **agy `-p`(비대화) 모드 + MCP = 세션 전체가 멈춘다** — MCP 서버가 설정돼 있으면 `-p` 비대화 모드 실행 시 세션이 응답 없이 멈춘다(자체 print-timeout도 무시됨). 경로 방식이나 `--dangerously-skip-permissions` 여부와 무관하게 재현된다. **agy에서 자동화 스크립트로 NAMU를 비대화 호출하는 것은 현재 불가능**하며, 대화형 세션에서만 정상 동작한다.
3. **agy MCP 경로는 실행 폴더(cwd) 기준 상대경로** — 봉투(`mcp_config.json`)가 `${extensionPath}` 같은 변수 치환을 지원하지 않아, agy 실행 폴더가 바뀌면 경로 해석이 조용히 실패(스킵)할 수 있다. PreInvocation 훅이 매 실행마다 절대경로로 자동 교정하지만, **재설치 직후 첫 세션**은 아직 교정 전이라 `/mcp`가 이상해 보일 수 있다(5절의 `--heal` 즉시 교정으로 해결).
4. **CC directory 소스는 라이브 참조, 원격 설치는 캐시 복사** — 둘을 혼동해 원격 설치인데 소스만 갱신하고 "왜 반영이 안 되지"라고 헷갈리지 않도록 7절 표를 참고할 것.
5. **agy MCP 도구 스키마 캐시** — MCP 도구 정의가 `~/.gemini/antigravity-cli/mcp/<server>/*.json`에 캐시된다. 도구 시그니처(예: `namu_record`의 파라미터)가 바뀌면 이 캐시가 갱신됐는지 확인이 필요할 수 있다.
6. **같은 이름으로 marketplace add하면 조용히 대체된다** — 이미 등록된 이름(`namu-marketplace`)으로 다시 `marketplace add`하면 충돌 에러 없이 기존 등록이 새 소스로 교체된다. 개발 기기에서 로컬 directory로 등록해 둔 `namu-marketplace`가 실수로 GitHub 원격 소스로 바뀔 수 있으므로, **개발 기기에서는 원격 add를 하지 말거나, 한 뒤 반드시 directory로 재등록**할 것.
7. **원격 캐시=repo 전체 clone이지만 실행본=플러그인 폴더만** — `~/.claude/plugins/marketplaces/<이름>/`에는 `memory/`를 포함한 repo 전체가 clone되지만, 실제 실행되는 코드는 `~/.claude/plugins/cache/<marketplace>/<plugin>/<버전>/`에 복사된 플러그인 폴더뿐이다. 즉 3절의 "유령 경로" 사고(캐시 폴더 안에 실수로 데이터를 씀)는 원격 설치에서도 나지 않는다(config.py 분기 3이 정상 발동, 실측 확인).
8. **Windows 훅 cp949 무음 실패** — 0.1.5 이하 설치본은 CC SessionStart 훅(`session_recall.py`)이 이모지 포함 JSON을 print할 때 Windows 파이프 stdout의 기본 cp949 인코딩과 충돌해 `UnicodeEncodeError`가 나고, 훅의 광범위 예외 처리가 이를 조용히 삼켜 **세션 자동주입이 티 없이 실패**한다. **0.1.6에서 해소**(`sys.stdout.reconfigure(encoding="utf-8")` 추가). 0.1.5 이하를 쓰고 있다면 세션 시작 시 작업 상태·교훈이 안 뜨는 게 이 버그일 수 있다.

## 뺀 것 (소재에 실측 근거가 없어 제외)

- `engine`이 `native` 이외의 값(`ollama`/`gemini_paid`/`claude_api`)일 때의 실제 동작 — 아직 구현되지 않아 오케스트레이션이 멈추는 것까지만 확인됐고, 그 이후 동작(설정 방법 등)은 다룰 근거가 없다.
