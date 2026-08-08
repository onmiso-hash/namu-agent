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
| [🌐 웹에서 직접 서버 운영하기](https://onmiso-hash.github.io/namu-agent/docs/remote_mcp_guide.html) | 웹에서 쓰되 서버는 내가 직접 |
| [📐 기억 설계도](https://onmiso-hash.github.io/namu-agent/docs/memory_architecture.html) | 기억이 어디에 어떤 모양으로 쌓이는지 |
| [⚙️ 절차 설계도](https://onmiso-hash.github.io/namu-agent/docs/workflow_architecture.html) | 나머지 절반 — 일의 순서를 어떻게 잡고 어디서 멈춰 물어보는지 |
| [📎 파일 주고받기](docs/attach_files.md) | 내 저장소에 파일을 올리고 받는 법, 절대 어기면 안 되는 격리 규칙 |
| [🔎 검색 통일](docs/search_index_unify.md) | 다섯 그릇이 어떻게 SQLite 색인 하나 뒤로 모였는지 |

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

## 지원 현황 — 지금 어디서 쓸 수 있나

NAMU는 두 부분이다 — **기억**(그릇 5개·작업일지·파일 첨부)과 **일하는 절차**(세션 브리핑·`/namu-task`·워커·statusLine·실수 방지 훅).
기억은 MCP 주소만 받아 주면 어디든 붙고, 절차는 **그 호스트용 플러그인 봉투를 따로 만들어야** 붙는다.

| AI | 붙이는 법 | 🧠 기억 | ⚙️ 일하는 절차 | |
|---|---|---|---|---|
| **Claude Code** (터미널) | 플러그인 | 전부 (도구 14개) | 전부 | ✅ 지원 |
| **agy** (터미널, Antigravity CLI) | 플러그인 | 전부 (도구 14개) | 거의 전부 — 실수 방지 훅 2개만 빠짐 | ✅ 지원 |
| **claude.ai** (웹) | MCP 주소 | 전부 (다섯 그릇 + 작업일지 + 파일 첨부, 도구 10개) | 아직 | ✅ 지원 |
| ChatGPT · Gemini(웹) · Copilot · Cursor 등 | — | 아직 | 아직 | ⏳ 준비 안 됨 |

- **"아직"은 그 AI가 못 한다는 뜻이 아니라, NAMU 쪽이 아직 그 자리를 잡지 않았다는 뜻이다.**
  기억은 원격 MCP를 붙일 수 있는 클라이언트면 원리상 동작하고(확인한 것은 claude.ai),
  절차는 호스트별 봉투가 필요한데 지금 만들어진 것은 Claude Code·agy 둘뿐이다.
- **실수 방지 훅** = 마무리 시 `[다음]` 줄 누락 차단(Stop) + 상시 주의 재알림(UserPromptSubmit).
  agy에는 대응 이벤트가 없어 이 둘만 빠진다(namu-62). 세션 브리핑은 agy용 PreInvocation 훅이 따로 동봉돼 동작한다.
- MCP 주소로 붙었을 때 노출되는 도구는 14개 중 10개다 — 기억 3종
  (`namu_recall`/`namu_record`/`namu_search`)과 파일 첨부 7종.
  쪽지 떼기·책갈피·동기화 설정은 플러그인 전용이며, 다섯 그릇과 작업일지 자체는 전부 읽고 쓸 수 있다.
- Claude Code 행은 실측값(같은 폴더에서 플러그인 on/off 비교), agy 행은 플러그인 동봉 구성 기준이다.

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

- **다섯 그릇** — 교훈(`learnings.yaml`) · 개인 사실(`profile.yaml`) · 작업일지(`tasks/<프로젝트>/log.md`) · 쪽지(`memo.yaml`) · 첨부 기록(`attachments.yaml`). 모든 기록은 3층(요약 `summary` · 왜 `reason` · 원문 `body`)으로 남는다. 쪽지만 유일하게 지워진다.
- **진실의 원천** — 전부 `~/.namu` 아래. 데이터 루트는 고정 상수라 어느 프로젝트에서 실행하든 같다(namu-35).
- **SQLite(FTS5) 검색 캐시 — 다섯 그릇 전부.** 교훈은 자기 표(`learnings` + `learnings_fts`)를 쓰고, 나머지 넷은 같은 모양의 표(`bowl_<이름>` + `bowl_<이름>_fts`, trigram)를 하나씩 갖는다. gitignore 대상이고 원본에서 언제든 다시 만들어진다. "낡았나" 판정은 그릇마다 **원본 파일의 크기·수정시각을 모은 서명 하나**로 하므로 바뀐 그릇만 다시 만든다(세션 시작·서버 부팅·pull 직후). 검색어는 **낱말별 AND**이며, 세 글자 미만 낱말이 섞이면 색인을 건너뛰고 LIKE로 전수 조회한다(trigram은 두 글자를 원리상 못 찾는다).
- **작업 상태 2파일** — `task.md`(불변 목적) / `log.md`(append-only 원본, 권위 있는 기록). "다음 할 일"은 마지막 `[다음]` 줄로 남기고, 작업을 닫는 말은 `[완료]`·`[중단]` 둘뿐이다. 작업일지 검색은 일지 줄과 함께 **각 작업의 설명서 한 장을 통째로 한 건**(`tag`가 `설명서`)으로 돌려준다.
- **파일 첨부** — 파일은 나무 서버가 아니라 **회원 본인의 동기화 저장소** `attach_file/`로 간다. 그 폴더는 각 PC에서 sparse-checkout으로 격리돼 몸통이 안 내려오고, 첨부 이력만 모든 기기에 남는다. 일회용 티켓 주소를 쓰면 파일 몸통이 AI의 출력을 아예 안 거친다. **파일 크기는 언제나 첨부 기록에서 읽지 저장소에 묻지 않는다** — 물으면 git이 빠진 몸통을 전부 내려받아 격리가 무너진다.
- **MCP 도구 14종** — 기억: `namu_recall` · `namu_search` · `namu_record` · `namu_memo_remove` · `namu_task_pin` · `namu_task_unpin` · `namu_sync_setup` / 첨부: `namu_upload_file` · `namu_list_files` · `namu_download_file` · `namu_delete_file` · `namu_create_upload_ticket` · `namu_create_download_ticket` · `namu_check_ticket`. 웹(원격 MCP)에는 10종이 노출된다 — 플러그인 전용 4종(쪽지 떼기·책갈피 2종·동기화 설정)만 빠진다.
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
