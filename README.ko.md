# NAMU Agent System

English: [README.md](README.md)

벤더 독립 에이전트 시스템. 특정 AI 벤더에 종속되지 않고, 이식 가능한 메모리 코어를 중심으로 작업 기록과 교훈을 누적해 스스로 학습한다.

## 📖 안내서 — 여기서 시작

코드를 몰라도 읽힌다. 아래 한 장이 나머지로 가는 길을 전부 안내한다.

| 안내서 | 이럴 때 |
|---|---|
| [🌳 **나무 안내서**](https://onmiso-hash.github.io/namu-agent/docs/index.html) | 나무가 뭔지, 쓰는 방법 네 갈래가 어떻게 다른지 |
| [🔧 설치하기](https://onmiso-hash.github.io/namu-agent/docs/install_guide.html) | Claude Code·agy에 붙이기 — 설치·첫 작업·업데이트·삭제 |
| [☁️ **나무 클라우드**](https://namu-cloud.onnamu.kr/) | 브라우저에서 쓰는 AI에 붙이기 — 설치 없이 GitHub 로그인만 |
| [🌐 웹에서 직접 서버 돌리기](https://onmiso-hash.github.io/namu-agent/docs/remote_mcp_guide.html) | 웹에서 쓰되 서버는 내가 직접 |
| [📐 기억 설계도](https://onmiso-hash.github.io/namu-agent/docs/memory_architecture.html) | 기억이 어디에 어떤 모양으로 쌓이는지 |

## NAMU가 뭐 하는 물건인가

AI 에이전트(Claude Code, agy 등)가 작업하며 얻은 교훈을 **이식 가능한 메모리**에 쌓아, 다음 작업에서 더 잘하게 만드는 시스템이다. "이 버그의 원인은 이거였고", "이 설계를 이렇게 한 이유는 이것" 같은 판단은 보통 대화가 끝나면 사라진다. NAMU는 이걸 `~/.namu`에 append-only로 남겨 다음 세션·다음 프로젝트에서도 같은 실수를 반복하지 않게 한다.

실행 엔진(Claude Code·agy)은 언제든 바꿔 끼울 부품일 뿐이고, NAMU의 진짜 가치는 **메모리 레이어**에 있다.

```mermaid
flowchart LR
    A[작업 수행] --> B["교훈 기록<br/>(namu_record)"]
    B --> C["~/.namu 에 누적"]
    C --> D["다음 세션에서 회상<br/>(namu_recall)"]
    D --> A
```

## ⚡ 30초 시작

```
claude plugin marketplace add onmiso-hash/namu-agent
claude plugin install namu@namu-marketplace
```

agy는 `agy plugin install https://github.com/onmiso-hash/namu-agent.git`.
업데이트는 대화창에서 `/namu:update` 한 줄이면 끝난다.

자세한 절차·확인법·문제 해결은 [설치하기](https://onmiso-hash.github.io/namu-agent/docs/install_guide.html)에 있다.

## 정체성

NAMU의 차별점은 실행 엔진이 아니라 **메모리 레이어(MCP)**에 있다. 이 원칙은 "봉투 둘, 내용물 하나" 구조로 구현된다 — 같은 메모리 코어(`mcp_server.py`), 같은 워커 정의(`namu-coder`/`namu-reviewer`), 같은 오케스트레이션 스킬(`/namu-task`)을 Claude Code와 agy가 그대로 공유한다. 다른 건 각 엔진이 요구하는 등록 형식(봉투)뿐이다.

## 아키텍처 개요

- **네 그릇** — 교훈(`learnings.yaml`) · 개인 사실(`profile.yaml`) · 작업일지(`tasks/<프로젝트>/log.md`) · 쪽지(`memo.yaml`). 모든 기록은 3층(요약 `summary` · 왜 `reason` · 원문 `body`)으로 남는다. 쪽지만 유일하게 지워진다.
- **진실의 원천** — 전부 `~/.namu` 아래. 데이터 루트는 고정 상수라 어느 프로젝트에서 실행하든 같다(namu-35).
- **SQLite(FTS5) 검색 캐시** — `learnings.yaml`을 인덱싱한 재생성 가능한 로컬 캐시. gitignore 대상이며, 항목 수 불일치를 감지하면 부팅 시 자동 재생성된다.
- **작업 상태 2파일** — `task.md`(불변 목적) / `log.md`(append-only 원본, 권위 있는 기록). "다음 할 일"은 마지막 `[다음]` 줄로 남기고, 작업을 닫는 말은 `[완료]`·`[중단]` 둘뿐이다.
- **MCP 도구 7종** — `namu_recall` · `namu_search` · `namu_record` · `namu_memo_remove` · `namu_task_pin` · `namu_task_unpin` · `namu_sync_setup`. 웹(원격 MCP)에는 앞의 3종만 노출된다.
- **워커 층** — `namu-coder`/`namu-reviewer` 서브에이전트가 각 엔진 네이티브 형식으로 이중 존재하되 시스템 프롬프트는 동일하다. 오케스트레이션은 `/namu-task` 스킬이 맡는다.
- **세션 표면** — statusLine(하단 상시 한 줄) · `/namu`(직접 부르는 브리핑) · 세션 시작 자동 주입.

상세는 [기억 설계도](https://onmiso-hash.github.io/namu-agent/docs/memory_architecture.html) 참고.

## 폴더 구조

| 폴더 | 역할 |
|------|------|
| `namu-plugin/` | 현역 코드 — MCP 메모리 서버(`mcp_server.py`), 코어 로직(`db.py`), 설정(`config.py`), 훅(`hooks/`), 오케스트레이션 스킬(`skills/namu-task/`) |
| `.claude/` | Claude Code 전용 글루 — 네이티브 서브에이전트, 세션 브리핑 명령(`commands/namu.md`), 로컬 설정 |
| `.agents/` | agy 전용 글루 — 네이티브 서브에이전트, 세션 브리핑 스킬 |
| `scripts/` | 두 엔진 공용 stdlib-only 스크립트 — 상태줄, 활성 task 선정, 문서 스타일 동기화 |
| `docs/` | 안내 문서(HTML, GitHub Pages 공개) + 설계 문서(md). 대체된 옛 문서는 `docs/archive/` |

이 repo에는 `memory/`·`tasks/`·`db/` 폴더가 없다(namu-34·namu-35로 폐지). 전부 개인 풀 `~/.namu` 아래에 쌓인다 — repo가 어디에 있든, 이 repo 자체를 개발 중이든 상관없다.

워커 정의는 의도적으로 플러그인 봉투에 동봉하지 않는다. 이 repo를 `git pull`만 하면 멀티 PC에 자동 배포되고, 세션 중 파일을 고쳐도 재시작 없이 즉시 반영되는 핫 리로드가 실측됐기 때문이다.

## 개발용 셋업

이 repo를 clone해 나무 자체를 고치려는 경우다.

```
git clone https://github.com/onmiso-hash/namu-agent.git
claude plugin marketplace add /path/to/namu-agent/namu-plugin
claude plugin install namu@namu-marketplace
sh scripts/setup_dev_hooks.sh
```

- **필요조건** — Python 3.12+ · [uv](https://docs.astral.sh/uv/) · SQLite ≥3.34(FTS5) · git
- **환경변수** — `NAMU_MACHINE`(이 PC 식별자, 미설정 시 호스트명) 하나뿐이다. 데이터 루트는 고정 상수라 바꿀 수 없다.
- **버전 bump** — 반드시 `scripts/namu_bump.py <버전>`을 쓴다. `setup_dev_hooks.sh`가 pre-push 훅으로 버전 드리프트를 막는다.
- **문서 스타일** — 안내 문서 CSS는 나무 클라우드 홈페이지에서 파생된다. 홈페이지 디자인이 바뀌면 `python3 scripts/sync_docs_css.py`로 다시 뽑는다.

설치형 사용자의 업데이트·삭제·문제 해결은 전부 [설치하기](https://onmiso-hash.github.io/namu-agent/docs/install_guide.html)에 있다.

## 로드맵

- **1단계 (완료):** 개인용 시스템 완성
- **2단계 (진행):** 공개 배포 + 개인 메모리 연동 + 나무 클라우드
- **3단계:** 공개 메모리 풀 (커뮤니티 집단지성, 선택적 기여/구독)

## 참고·감사

NAMU의 플러그인 방식 제작은 [netwaif/multi-agent-starter](https://github.com/netwaif/multi-agent-starter)의 「MultiAgent 한국어 매뉴얼 v2.1」에서 영감을 받았다.

## 라이선스

Apache-2.0 — [LICENSE](LICENSE) 참조.
