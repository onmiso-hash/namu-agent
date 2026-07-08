# NAMU 설치형 사용설명서

> 📅 2026-07-08 · docs/deploy_design.md(#20) 실측 결과를 사용자 관점으로 정리한 문서.

이 문서는 NAMU repo를 clone해 개발하는 게 아니라, **자기 임의 프로젝트에 NAMU를 플러그인으로 설치해 쓰려는 사용자**를 위한 것이다. clone 기반 개발 환경(repo 자체가 NAMU_HOME)을 원한다면 루트 [`README.md`](../README.md)의 셋업 가이드를 따를 것.

## 1. 개요 — 설치형 vs clone 개발형

NAMU는 두 가지 방식으로 쓸 수 있다.

- **clone 개발형** — NAMU repo를 그대로 clone해서 그 repo 안에서 실행한다. repo 자체가 `NAMU_HOME`이 되고, `namu-plugin/` 코드를 고치면 재설치 없이 바로 반영된다(단, agy는 워크스페이스로 이 repo를 열어야 함). 이 형태는 루트 [`README.md`](../README.md)의 셋업 가이드를 참고할 것.
- **설치형** — NAMU repo와 무관한 자기 프로젝트에서, `namu-plugin/`을 Claude Code나 agy에 **플러그인으로 설치**해 쓴다. 이 문서가 다루는 대상이다. 설치본은 원본의 **복사본**이라는 점이 clone형과의 핵심 차이다(아래 함정 참고).

두 형태 모두 같은 메모리 코어(`mcp_server.py`)·같은 워커 정의·같은 오케스트레이션 스킬을 공유한다("봉투 둘, 내용물 하나"). 다른 건 등록 형식(봉투)과 데이터가 저장되는 위치뿐이다.

## 2. 사전 준비

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — `mcp_server.py`가 PEP 723 inline 메타데이터로 의존성을 자급자족하므로 별도 pip install이 필요 없다.
- (선택) **환경변수**
  - `NAMU_MACHINE` — 현재 기기를 식별하는 이름(예: `my-laptop`). 미설정 시 `unknown`으로 폴백되며, 여러 PC를 오가며 쓸 경우 `context.<machine>.md` 매칭이 어긋날 수 있다.
  - `NAMU_HOME` — 메모리(교훈·작업 기록)가 저장될 위치를 바꾸고 싶을 때만 지정한다. 기본값 동작은 아래 3절 참고.

## 3. 메모리(기억)가 저장되는 위치

설치형에서 가장 먼저 헷갈리는 부분이다. NAMU는 데이터 루트(`NAMU_HOME`)를 다음 우선순위 3분기로 정한다.

1. **`NAMU_HOME` 환경변수가 설정돼 있으면 그 경로** — 항상 최우선. `.env` 파일로 지정해도 동일하게 인식된다.
2. **현재 실행 위치가 NAMU repo를 clone한 폴더(`memory/`가 실재)라면 그 repo 경로** — clone 개발형과의 하위호환용이며, 설치형 사용자는 보통 해당하지 않는다.
3. **`~/.namu`** — 위 두 조건에 모두 해당하지 않는 설치형 사용자의 기본값(분리 모드). 이 폴더는 미리 만들 필요 없이, 교훈을 처음 기록하는 시점에 자동으로 생성(스캐폴딩)된다.

**왜 이렇게 나뉘는가** — 플러그인을 설치하면 설치본(캐시 폴더)에는 `memory/`가 복사되지 않는다. 만약 이 분기가 없다면 사용자가 실수로 캐시 폴더 안에 데이터를 쓰는 "유령 경로" 사고가 날 수 있다. 3분기는 이를 원천 차단하도록 설계됐다(실측: hp 기기에서 repo 밖 가짜 캐시 + 가짜 HOME 환경으로 분기 3 동작과 메모리 3층 — learnings 왕복, tasks 층, db 스캐폴딩 — 전부 확인됨).

## 4. Claude Code에 설치

### 4-1. 로컬 경로(directory) 마켓플레이스 등록 — 실측 절차

지금 확정된 절차는 **로컬 디스크에 있는 `namu-plugin` 폴더 경로**를 마켓플레이스로 등록하는 방식이다.

```
/plugin marketplace add /path/to/namu-plugin
/plugin marketplace update
/reload-plugins
```

`namu-plugin` 폴더 자체가 필요하다는 뜻이므로, 아직 이 폴더를 어떻게 손에 넣는지(NAMU repo를 clone할지, 다른 방식으로 받을지)는 사용자 선택에 달려 있다. 참고로 이 방식은 **소스를 라이브 참조**한다 — 설치 기록이 구버전이어도 실제로는 최신 소스가 로드된다. 따라서 소스 폴더를 최신화(예: `git pull`)하고 CC를 재시작하기만 해도 반영되며, 재설치는 필요 없다.

### 4-2. GitHub 원격 마켓플레이스 설치 — 실측 확정 절차

**전제** — repo 루트에 `.claude-plugin/marketplace.json`(namu-plugin을 가리키는 봉투)이 있어야 한다. NAMU repo는 커밋 `e2fba2e`부터 이 봉투를 포함한다. 이게 없으면 clone 자체는 성공해도 `Marketplace file not found at ...\.claude-plugin\marketplace.json` 에러로 등록이 실패한다.

```
claude plugin marketplace add onmiso-hash/namu-agent
claude plugin install namu@namu-marketplace
```

(또는 CC 대화 세션 안에서 `/plugin marketplace add onmiso-hash/namu-agent`도 동일하게 동작한다.) 설치 스코프는 기본 **user**. private repo는 HTTPS credential manager 등 git 자격증명이 사전에 설정돼 있어야 clone이 된다.

**실측 물증(2026-07-08, samsung, CC v2.1.204)** — `installed_plugins.json`에 `version 0.1.5`·`gitCommitSha=e2fba2e`가 기록돼 GitHub발 설치임이 확인됐고, repo 밖 폴더에서 `claude mcp list` → `plugin:namu:namu-memory ✔ Connected`, 새 세션에서 MCP 3도구·statusLine 정상 동작(라이브 스크린샷 물증)까지 확인됨.

원격 설치는 로컬 directory 소스와 달리 **캐시 복사** 방식이다(`~/.claude/plugins/cache/<marketplace>/<plugin>/<버전>/`에 플러그인 폴더만 복사돼 실행됨). 따라서 소스 갱신만으로는 반영되지 않고 별도 update 절차(6절 참고)가 필요하다.

## 5. agy(Antigravity)에 설치

```
agy plugin install <namu-plugin 경로>
```

설치가 끝나면 agy용 MCP 등록(`mcp_config.json`)은 워크스페이스 상대경로 기반이라, agy가 이 플러그인이 필요한 데이터 경로를 실행 시점에 절대경로로 자동 교정해준다(PreInvocation 훅). 다만 **재설치 직후 첫 세션**에는 이 교정이 아직 한 번도 돌지 않아 `/mcp`가 정상으로 안 보일 수 있다.

이 문제를 포함해 재설치·업데이트를 한 번에 안전하게 처리하는 스크립트가 `scripts/agy_reinstall.ps1`이다.

```powershell
scripts/agy_reinstall.ps1
```

내부적으로 다음 3단계를 순서대로 실행한다.

1. `agy plugin uninstall namu` — agy의 `plugin install`은 비파괴 병합이라, 소스에서 지운 파일이 설치본에 그대로 남는다. 완전히 청소하려면 반드시 먼저 지워야 한다.
2. `agy plugin install <경로>` — 재설치.
3. 설치본 훅을 `--heal` 모드로 즉시 실행 — `mcp_config.json`을 그 자리에서 절대경로로 교정해, 첫 세션부터 `/mcp`가 바로 동작하도록 만든다.

수동으로 하려면 `uninstall → install → --heal` 순서를 그대로 따르면 된다.

## 6. 업데이트

플러그인 코드가 바뀌었을 때 반영하는 절차는 **설치 방식에 따라 다르다.**

| | Claude Code | agy |
|---|---|---|
| **directory(로컬 경로) 소스** — 소스를 라이브 참조 | `git pull`(또는 소스 폴더 갱신) + CC 재시작만으로 반영. 재설치 불필요 | `scripts/agy_reinstall.ps1` 실행(수동: `uninstall → install → --heal`) |
| **원격(GitHub) 설치** — 캐시 복사 | `claude plugin update namu@namu-marketplace` + CC 재시작. **반드시 `이름@마켓플레이스` 전체 식별자**로 — 짧은 이름(`update namu`)은 "not found"로 실패한다(실측: 0.1.5→0.1.6 버전·커밋 sha 반영 확인, 2026-07-08) | `scripts/agy_reinstall.ps1` 실행(수동: `uninstall → install → --heal`) |

핵심 구분: directory 소스는 "라이브 참조"라서 소스만 최신화하면 끝나지만, 원격/캐시 기반 설치는 캐시가 낡은 채로 남으므로 명시적인 update 동작이 필요하다.

## 7. 워커(서브에이전트)

NAMU는 `namu-coder`/`namu-reviewer` 같은 워커를 오케스트레이션 스킬(`/namu-task`)이 호출해 실제 구현·검수를 맡긴다.

- **`namu_workers.yaml`이 없으면** — `engine=native`로 간주하고, **현재 실행 중인 엔진의 네이티브 서브에이전트**를 그대로 쓴다. 추가 설정도, 추가 비용도 들지 않는다. 설치형 사용자 대부분은 이 기본 동작으로 충분하다.
- **파일이 있으면** — 그 설정이 override로 동작해 다른 엔진/워커를 지정할 수 있다(고급 설정, 이 문서에서는 다루지 않음).
- 호출명은 엔진에 따라 자동으로 갈린다 — Claude Code는 플러그인 에이전트에 `namu:` 네임스페이스가 붙고(예: `namu:namu-coder`), agy는 네임스페이스 없이 그대로(`namu-coder`) 불린다. 사용자가 직접 신경 쓸 부분은 아니다.

## 8. 함정·제한 사항

설치형 환경에서 실측으로 확인된 함정이다. 인코딩(cp949)·구식 conhost 터미널·agy 워크스페이스 상대경로·"설치본은 복사본" 같은 공통 함정은 루트 README의 [셋업 함정](../README.md#셋업-함정) 4종과 겹치므로 그쪽을 참고하고, 여기서는 **설치형에서만 두드러지는 함정**만 적는다.

1. **agy `plugin install`은 비파괴 병합** — 소스에서 삭제한 파일이 설치본에 그대로 남는다. 반드시 `agy plugin uninstall namu` 후 `install`해야 완전히 청소된다(5절 `agy_reinstall.ps1` 참고).
2. **agy `-p`(비대화) 모드 + MCP = 세션 전체가 멈춘다** — MCP 서버가 설정돼 있으면 `-p` 비대화 모드 실행 시 세션이 응답 없이 멈춘다(자체 print-timeout도 무시됨). 경로 방식이나 `--dangerously-skip-permissions` 여부와 무관하게 재현된다. **agy에서 자동화 스크립트로 NAMU를 비대화 호출하는 것은 현재 불가능**하며, 대화형 세션에서만 정상 동작한다.
3. **agy MCP 경로는 실행 폴더(cwd) 기준 상대경로** — 봉투(`mcp_config.json`)가 `${extensionPath}` 같은 변수 치환을 지원하지 않아, agy 실행 폴더가 바뀌면 경로 해석이 조용히 실패(스킵)할 수 있다. PreInvocation 훅이 매 실행마다 절대경로로 자동 교정하지만, **재설치 직후 첫 세션**은 아직 교정 전이라 `/mcp`가 이상해 보일 수 있다(5절의 `--heal` 즉시 교정으로 해결).
4. **CC directory 소스는 라이브 참조, 원격 설치는 캐시 복사** — 둘을 혼동해 원격 설치인데 소스만 갱신하고 "왜 반영이 안 되지"라고 헷갈리지 않도록 6절 표를 참고할 것.
5. **agy MCP 도구 스키마 캐시** — MCP 도구 정의가 `~/.gemini/antigravity-cli/mcp/<server>/*.json`에 캐시된다. 도구 시그니처(예: `namu_record`의 파라미터)가 바뀌면 이 캐시가 갱신됐는지 확인이 필요할 수 있다.
6. **같은 이름으로 marketplace add하면 조용히 대체된다** — 이미 등록된 이름(`namu-marketplace`)으로 다시 `marketplace add`하면 충돌 에러 없이 기존 등록이 새 소스로 교체된다. 개발 기기에서 로컬 directory로 등록해 둔 `namu-marketplace`가 실수로 GitHub 원격 소스로 바뀔 수 있으므로, **개발 기기에서는 원격 add를 하지 말거나, 한 뒤 반드시 directory로 재등록**할 것.
7. **원격 캐시=repo 전체 clone이지만 실행본=플러그인 폴더만** — `~/.claude/plugins/marketplaces/<이름>/`에는 `memory/`를 포함한 repo 전체가 clone되지만, 실제 실행되는 코드는 `~/.claude/plugins/cache/<marketplace>/<plugin>/<버전>/`에 복사된 플러그인 폴더뿐이다. 즉 3절의 "유령 경로" 사고(캐시 폴더 안에 실수로 데이터를 씀)는 원격 설치에서도 나지 않는다(config.py 분기 3이 정상 발동, 실측 확인).
8. **Windows 훅 cp949 무음 실패** — 0.1.5 이하 설치본은 CC SessionStart 훅(`session_recall.py`)이 이모지 포함 JSON을 print할 때 Windows 파이프 stdout의 기본 cp949 인코딩과 충돌해 `UnicodeEncodeError`가 나고, 훅의 광범위 예외 처리가 이를 조용히 삼켜 **세션 자동주입이 티 없이 실패**한다. **0.1.6에서 해소**(`sys.stdout.reconfigure(encoding="utf-8")` 추가). 0.1.5 이하를 쓰고 있다면 세션 시작 시 작업 상태·교훈이 안 뜨는 게 이 버그일 수 있다.

## 뺀 것 (소재에 실측 근거가 없어 제외)

- namu_workers.yaml의 override 상세 문법(엔진/워커 지정 방식) — 이 문서의 소재(4개 파일)에 스키마가 없어 "고급 설정, 다루지 않음"으로만 언급했다.
