# 나만의 멀티에이전트 시스템 기획

> 📅 시작: 2026-06-22 | 최종 갱신: 2026-06-26 (로드맵 12번 완전 종료 — 검수 게이트 fail 멈춤 라이브 검증까지 통과: pass(06-25)+fail(06-26) 양면 검증) | 대화를 통해 점진적으로 채워나가는 문서

---

## 🎯 프로젝트 목표
- 어느 하나의 AI에 종속되지 않는 멀티에이전트 시스템
- 작업에 맞는 에이전트를 그때그때 정의/생성하고, 성공/실패 기록을 공유하며 스스로 학습해 발전하는 시스템

## 💡 핵심 아이디어
- 클라우드 AI에 종속되지 않는 에이전트 시스템
- 자체 메모리 기능 구성
- 모든 AI가 공통 기억/맥락을 공유
- 성공/실패 이력 저장 → 자가학습/발전

## 🔧 핵심 기능 (5가지)
1. **Agent 정의/생성** — 작업에 맞는 에이전트를 그때그때 만들어내기
2. **Task 분할/배분** — 큰 작업을 쪼개서 적절한 에이전트에게 맡기기
3. **Agent 관리** — 실행 중인 에이전트들 상태 모니터링/제어
4. **기록 공유** — 성공/실패 이력을 모든 에이전트가 볼 수 있게 저장
5. **자가학습** — 쌓인 기록으로 스스로 개선 (적응형 학습)

## 🧠 학습 방식: Human-in-the-loop → Human-on-the-loop
- **초기:** 사람이 직접 감독, 성공/실패 판단, 재실행 여부 결정
- **중기:** 판단 기록 누적 → 패턴 분석 → 판단 기준 자동 도출
- **이후:** AI가 기준으로 자율 판단, 사람은 감시만

### ⚠️ 핵심 설계 원칙
- 기록 시 **결과뿐 아니라 판단 이유**까지 저장해야 함
  - 이유 없는 기록 → 패턴은 찾아도 엉뚱한 기준 도출 위험
  - 이유 있는 기록 → 정확한 기준 도출 가능

## 📌 참조
- Harness MultiAgent 2.1 매뉴얼 (netwaif/multi-agent-starter)

---

## ✅ 결정된 사항
| 날짜 | 항목 | 결정 내용 |
|------|------|-----------|
| 2026-06-22 | 작업 방식 | 대화하며 단계적으로 설계, 결정사항은 이 문서에 누적 |
| 2026-06-22 | 모델 선택 | 기획은 Sonnet 4.6, 구현 시 Opus 4.8 또는 Claude Code |
| 2026-06-23 | HP 경로 | ~/project/namu-agent (삼성과 달리 project 폴더 하위) |
| 2026-06-23 | 개발 환경 | HP 노트북 WSL + Claude Code v2.1.186, Node.js v24.17.0 |
| 2026-06-23 | 구독 어댑터 | Claude Agent SDK로 구현 완료 (GPT Plus 구독은 공식 방법 없어 제외) |
| 2026-06-23 | gitignore | tasks/, db/ 는 gitignore (개인 작업기록 + SQLite는 로컬 전용) |
| 2026-06-23 | 메모리 구조 | learnings.md = 공용 append-only 메모리 (git 동기화), SQLite = 로컬 패턴분석용 캐시 |
| 2026-06-24 | Gemini 어댑터 | gemini_api.py 구현 완료 (google-genai SDK, priority 5) |
| 2026-06-24 | CLI 진입점 | main.py 구현 완료 (단일명령 + REPL 모드, .env 키 관리) |
| 2026-06-24 | Gemini 구독 | agy CLI 경유 구독 어댑터 보류 — 기술적으로 가능하나 쿼터 불안정, 추후 구현 |
| 2026-06-24 | .env 관리 | .env.example 템플릿 제공, .env는 gitignore |
| 2026-06-24 | 버그수정 #1 | orchestrator.py — read_text/write_text에 `errors="replace"` 추가 (surrogate 문자 크래시 방지) |
| 2026-06-24 | 버그수정 #2 | claude_subscription.py — async for 루프를 try/finally로 감싸 `await gen.aclose()` 명시 호출 (연쇄 traceback 방지) |
| 2026-06-24 | **아키텍처 방향 전환** | 자체 CLI 구현 → **플러그인 + MCP 메모리 코어** 방식으로 전환. 독립성은 인터페이스가 아니라 메모리 레이어에 둔다 |
| 2026-06-24 | Gemini 구독 최종 | agy(Antigravity CLI) non-TTY stdout 버그 + 쿼터 불안정 → 구독 어댑터 포기, API 키 방식으로 일원화 |
| 2026-06-24 | 실행 엔진(A층) | Claude Code/agy의 실행 엔진을 **빌려쓴다** (직접 구현 안 함). NAMU는 하네스엔지니어링(B층)+메모리(C층) 담당 |
| 2026-06-24 | MCP SDK | 공식 `mcp` 패키지 `mcp[cli]>=1.28,<2` (v2 임박: beta 6/30·안정 7/27, 전송계층 변경 → 상한 핀 필수). 내장 FastMCP 사용 |
| 2026-06-24 | learnings 스키마 확정 | `{id(ULID), timestamp, task, task_type, outcome, reason, machine, verified_by, tags}` |
| 2026-06-24 | ID 전략 | **ULID** (`python-ulid`) — 시간순 정렬 + 다중 PC 머지 충돌 0. recall 최신순과 궁합 |
| 2026-06-24 | machine 컬럼 | ID에 안 박고 독립 컬럼. `.env`의 `NAMU_MACHINE`(samsung/hp/home)에서 주입 |
| 2026-06-24 | verified_by 컬럼 | human/ai/unverified — append-only라 백필 불가, Human-in→on-the-loop 전환의 핵심 구분자 |
| 2026-06-24 | SQLite FTS | 한글 부분검색 위해 **trigram 토크나이저**(3.34+ 내장) + 2글자 이하 LIKE 폴백. INSERT 트리거로 FTS 자동 동기화 |
| 2026-06-24 | 구현 위치 | MCP 메모리 서버(4·5·6번) 실제 코딩은 HP 노트북 Claude Code에서 (실환경 sqlite3·WSL에서 검증하며) |
| 2026-06-24 | recall 폴백 정책 | **옵션 A** 확정: query 매칭 0개일 때만 최신 N 폴백, limit 기본 작게(5). recall은 SessionStart 자동주입 후보라 토큰 효율 우선. append-only라 향후 변경 시 기존 데이터 영향 0(recall 함수 내부만 수정) → 대안 B(부족분 채우기)/하이브리드는 맥락 빈약 체감 시 |
| 2026-06-24 | recall/search 정렬 | recall=최신순(id DESC, 맥락 로딩) / search=관련도순(bm25, 패턴 분석). search는 폴백 없음 + 전체 매칭 outcome 경향 요약(limit·filter 무시) |
| 2026-06-24 | db.py conn 두 패턴 | **의도된 분리(통일 금지):** 읽기(recall/search)=conn 인자로 받음(`:memory:` 주입 단위테스트) / 쓰기(record/init_db/rebuild)=함수 내부서 conn 열고닫음(YAML-first→SQLite 트랜잭션 경계 완결) |
| 2026-06-24 | .env 로딩 위치 | `main.py` 진입점 → **`config.py`로 일원화**. 모든 진입점이 import하는 공통 지점서 `load_dotenv(BASE_DIR/".env")` 경로 명시 로드 → mcp_server.py 직접 실행(Inspector/Claude Code)서도 machine=hp 정상 |
| 2026-06-24 | MCP 경계 입력 정규화 | FastMCP가 `list[str]` 타입힌트로 JSON 문자열 tags를 단일원소 리스트로 코어션 → 이중인코딩 버그. db.py의 `list\|None` 계약 유지하고 **신뢰 경계인 mcp_server.py 래퍼(`_normalize_tags`)에서 정규화**. 책임 분리 원칙 |
| 2026-06-24 | namu_record 기본값 | `verified_by` 기본 "ai"(MCP 래퍼) — db.py record 기본은 "human". 자동 기록은 ai, 사람 검증은 명시 |
| 2026-06-24 | learnings.yaml git 추적 | source of truth라 git 추적 시작(커밋 `697f470`). append-only 원칙대로 버그수정 전 테스트 기록(machine=unknown 등)도 보존 — `verified_by`/`machine` 필터로 깨끗한 것만 쿼리 가능하므로 물리 삭제 불필요 |
| 2026-06-24 | 문서 동기화 규칙 | plan.md=대화창서 갱신→다운→repo 커밋 / design.md=Claude Code·repo서 갱신→프로젝트는 repo본 받아 교체. **공통: 최종적으로 repo가 진실의 원천** |
| 2026-06-25 | MCP 등록 스코프 | **local 확정(지금).** 등록은 "Claude Code 전용 글루"(플랫폼별)지 포터블 코어 아님 + 아직 MVP라 blast radius를 namu-agent로 좁혀 검증. 동기화돼야 할 것(learnings.yaml)은 등록과 무관하게 git으로 따로 흐름 |
| 2026-06-25 | 스코프 승격 경로 | 도구 신뢰되면 → **user**(어느 프로젝트서든 namu_recall/record, config.py BASE_DIR 고정이라 중앙 learnings.yaml 하나를 바라봄 = NAMU "보편 기억" 비전) → 최종 **플러그인**(로드맵 13, `${CLAUDE_PLUGIN_ROOT}`로 다중 PC 포터블 배포). **project 스코프는 건너뜀**(OS별 python 경로 차 + 플러그인이 대체) |
| 2026-06-25 | 등록 명령(HP) | `claude mcp add namu-memory --scope local --transport stdio -- "$(pwd)/.venv/bin/python" "$(pwd)/mcp_server.py"`. 절대경로가 `~/.claude.json [project: namu-agent]`에 박힘. NAMU_MACHINE은 config.py가 .env서 읽으니 `--env` 불필요, venv activate도 불필요(절대경로 파이썬 직접 호출) |
| 2026-06-25 | plugin 시 챙길 점 | 지금은 코드(mcp_server.py)·노트(learnings.yaml)가 같은 repo라 BASE_DIR 고정으로 문제 0. **플러그인화 때만** 코드가 별도 설치폴더로 갈라지므로 그 단계서 learnings.yaml 경로를 env/`${CLAUDE_PROJECT_DIR}`로 분리(한 줄). 미리 당길 필요 없음 |
| 2026-06-25 | **로드맵 11번 자동/수동** | **recall=SessionStart 훅 자동주입(결정론적, AI 턴 안 씀) / record=수동 유지(CLAUDE.md 규칙).** 자동 저장 보류 — "작업 완료" 시점이 기계적으로 모호해 자동기록 시 쓰레기 데이터 누적 + 의미 있는 reason 생성 불가. 과거 교훈 #5([failure] learnings.md 자동기록 제거)와 동일 결론, recall이 그걸 자동으로 꺼내와 재확인됨 |
| 2026-06-25 | 11-b 보류 | record 자동화는 누락이 실제로 관측될 때만 재검토. Stop 훅은 매 응답 턴마다 발화하므로(작업완료 아님) 무지성 리마인더는 노이즈 → 게이트(세션당 1회/조건부) 필요. SubagentStop은 별도 이벤트라 워커 노이즈 격리 가능 |
| 2026-06-25 | 훅 설정 위치 | `.claude/settings.local.json`(gitignore, 로컬 전용). MCP local 스코프와 동일 논리 — PC별 절대경로(HP WSL `.venv/bin` vs 삼성 Win) 차로 repo 공유 불가, 플러그인화(13번) 때 플러그인으로 이전. `session_recall.py`는 경로 비의존이라 git 추적 |
| 2026-06-25 | 훅 스펙 검증(공식 docs) | code.claude.com 교차확인: SessionStart는 stdout/`additionalContext`로 컨텍스트 주입(2.1.0부터 무음 주입), Stop은 매 응답 턴마다 발화, blocking 가능 이벤트=PreToolUse/UserPromptSubmit/Stop/SubagentStop. 훅은 세션 시작 시 스냅샷(핫적용 X)→`/hooks`에서 검토 |
| 2026-06-25 | agy 확장점 사실확인 | (멀티에이전트 대비) **agy도 MCP 호스트**: `~/.gemini/config/mcp_config.json`(공유)·`.agents/mcp_config.json`(워크스페이스), `/mcp` 관리. **훅도 있음**: `hooks.json`, 이벤트 PreToolUse/PostInvocation/Stop+세션시작, Gemini CLI와 동일 포맷. **네이티브 서브에이전트**(`/agents`, `agy -p`). 단 MCP env var 버그(키 하드코딩 강제)·non-TTY stdout #76·훅 경로 버그(최근 수정) 존재 → agy 글루(16번) 착수 시 재검증 |
| 2026-06-25 | **12번 전제검증(검색)** | Anthropic: `claude -p`(진짜 CLI 서브프로세스)=허용, OAuth 토큰 추출해 제3자 클라이언트에 주입=금지(2026-02 ToS 명문화, 04월 차단 시행). 단 `-p` 비대화형은 표준 구독풀 아닌 **별도 Agent SDK 크레딧**(고정·이월불가, API요율, 2026-05 도입) 소모 → Task/`/agents`/`-p` 세 경로가 **과금상 비대칭**. Gemini 무료 API=프롬프트 학습+사람 리뷰(코드보안 부적합), 유료는 학습 안 함, **Pro는 2026-04 무료티어서 제거**(유료 전용) |
| 2026-06-25 | **워커 구성 확정** | 기본=메인 AI **네이티브 서브에이전트**(Claude Code=Claude, agy=Gemini, 같은 구독풀·비용0·보안OK·엔진무관). 검수도 같은 구독 안(무료 Gemini는 코드 학습돼 부적합, `-p`는 별도 크레딧이라 "구독 안 저렴" 아님). 이종 엔진(Ollama/유료Gemini)은 설치·실행 초기 **override**로 후순위. 워커 spawn 어댑터는 엔진차+과금·보안등급을 메타데이터로 흡수. **MVP는 native만** 구현, 이종 subprocess는 인터페이스 자리만 |
| 2026-06-25 | 검수 게이트 | 검수 fail=**자동 재실행 금지**. 사용자에 판정 이유 보고 → ①재실행(횟수 입력)/②통과 처리(검수 오판단 시)/③중단. 사용자 통과 시 `verified_by`=human. 검수 워커도 AI라 오판 가능 → 사람 게이트가 가치, `verified_by` 컬럼과 자연 연결 |
| 2026-06-25 | 워커 설정 위치 | `namu_workers.yaml`로 **분리**(config.py 상수와 성격 다른 사용자 선택값, override 마법사 표면 명확). 민감값(키)은 yaml에 안 박고 `.env` 참조. learnings 패턴과 동일 — 기본구성 git공유, override 로컬값은 후분리(13번 플러그인화 때) |
| 2026-06-25 | 스킬/커맨드 통합 확인 | Claude Code 2.1.3서 `.claude/commands/`와 `.claude/skills/<name>/SKILL.md` **통합** — 둘 다 같은 `/슬래시` 생성, 신규는 skills 권장(supporting files·frontmatter 제어·동적 컨텍스트 주입). 서브에이전트=`.claude/agents/*.md`(frontmatter: name/description/model/tools, body=시스템 프롬프트), **Task 도구→Agent 도구 개명**, `model` 필드로 비용 라우팅(검수=haiku). 스코프 우선순위 session>project>user>plugin |

## 🏗️ 저장소 구조 (GitHub 기반)
```
github/
├── tasks/          ← gitignore (PC별 로컬에만 존재)
└── memory/         ← 공통 학습 기억 (git 동기화)
    └── learnings.yaml  ← append-only, 모든 PC가 추가만 가능
```

**사용 흐름:** git pull → 작업 실행 → git push
**learnings.yaml 원칙:** 추가만 가능, 삭제/수정 금지 (자동학습 이력 보존)

## 💻 사용 환경
- 여러 PC에서 사용 (홈PC, 작업용 노트북, 삼성 노트북 등)
- 실행은 각 PC 로컬에서
- 메모리/기록은 GitHub으로 공유 동기화
- 초반: 한 번에 한 PC만 사용
- 나중: 홈PC 백그라운드 큰 프로젝트 + 노트북 소규모 작업 병행

## 🗺️ 로드맵
- **1단계 (진행중):** 개인용 시스템 완성
- **2단계 (나중):** 공개 배포 + 개인 메모리 연동 구조
- **3단계 (미래):** 공개 메모리 풀 — 선택적 기여/구독
  - 💡 각자 private 메모리 보유하되, 일반적인 학습은 공개 풀에 선택적 기여/구독 가능
  - 쓰면 쓸수록 커뮤니티 전체가 똑똑해지는 구조

---

## 📝 대화 로그 요약
### 2026-06-22
- 하네스 멀티에이전트 매뉴얼을 참조로 제시
- 벤더 독립 + 공유 메모리 + 자가학습 시스템 구상 중
- 아직 구체적인 방향 정리 단계

### 2026-06-23
- HP 노트북 WSL 환경 셋업 완료 (Node.js v24, Claude Code v2.1.186)
- ~/project/namu-agent clone 완료
- Claude Code에서 첫 코드 작성 시작
- 기본 폴더 구조, AI 어댑터 4개, 오케스트레이터 생성
- 구독 어댑터 방식 조사 → Claude Agent SDK로 구현 가능 확인
  - GPT Plus 구독은 공식 프로그래밍 방식 없음 → 제외
  - claude_subscription.py 구현 완료
- 전체 동작 테스트 통과 (API 키 없이 Claude 구독으로 실제 AI 호출 성공!)
- venv 환경 구성, requirements.txt 완성
- .gitignore에 tasks/, db/ 추가
- GitHub push 완료
- learnings.md vs SQLite 역할 명확히 정리

### 2026-06-24
- main.py 없다는 것 인지 → CLI 진입점 필요성 확인
- 하네스 매뉴얼 분석 → 하네스는 파일 기반 시스템, NAMU는 AI를 호출하는 구조로 차이 확인
- Gemini 구독 어댑터 조사:
  - Gemini CLI → agy(Antigravity CLI)로 전환됨 (2026-06-18 개인 구독 종료)
  - agy 경유 구독 어댑터 기술적으로 가능하나 쿼터 불안정 → 추후 구현으로 보류
- gemini_api.py 구현 완료 (google-genai 2.9.0, gemini-2.5-flash, priority 5)
- main.py 구현 완료 (단일명령 + REPL 모드, --no-approve, --system 옵션)
- .env 기반 키 관리 구조 도입 (.env.example 템플릿)
- 전체 통합 테스트 통과
- GitHub push 완료
- 버그수정 2건:
  - `UnicodeEncodeError`: `orchestrator.py` 파일 입출력에 `errors="replace"` 추가 → surrogate 문자로 인한 크래시 방지
  - `aclose()` 오류: `claude_subscription.py`의 async for 루프를 `try/finally`로 감싸 generator 명시적 종료 → 연쇄 traceback 방지
- **(오후 세션) 근본적 아키텍처 재검토:**
  - Gemini 구독 연결 재조사 → agy non-TTY stdout 버그 + 쿼터 불안정 확인 → 구독 어댑터 최종 포기
  - "자체 CLI vs 플러그인" 토론 → **독립성은 인터페이스가 아니라 메모리에 있다**는 결론
  - 하네스 A/B/C층 구분: 실행엔진(A)은 빌려쓰고, 하네스엔지니어링(B)+메모리(C)를 직접 제작
  - Claude Code 확장 포인트 확인(MCP/Hook/Skill/CLAUDE.md/Plugin) → NAMU 레이어 매핑 완료
  - 다음: MCP 메모리 서버(recall/record/search) 구현이 최우선

### 2026-06-24 (저녁 세션 — MCP 메모리 서버 설계 확정)
- mcp_memory_design.md 체크리스트 1·2·3 진행:
  - **1번 (MCP SDK 조사):** 공식 `mcp` 1.28.0 확인. v2 임박(beta 6/30) → `mcp[cli]>=1.28,<2` 상한 핀. FastMCP 사용
  - **2번 (스키마 확정):** 초안에 `machine`·`verified_by` 추가, `id`는 ULID로
    - ULID 선택 이유: auto-increment 정수는 오프라인 PC들이 같은 번호 만들어 git 머지 충돌 → ULID로 회피
    - machine: ID에 박지 않고 독립 컬럼(GROUP BY 위해). 역할 다른 PC라 환경 디버깅용 보험
    - verified_by: append-only라 백필 불가, "사람이 검증한 성공만" 뽑아 기준 도출하려면 필수
  - **3번 (SQLite 설계):** trigram FTS + LIKE 폴백, INSERT 트리거 동기화
    - 검색으로 검증: 기본 unicode61은 한글 부분검색 불가, trigram(3.34+)이 CJK 부분검색 지원하나 최소 3글자 필요 → 2글자 이하 LIKE 폴백
    - tags는 JSON 문자열 1컬럼(`json.dumps(ensure_ascii=False)`), 정밀필터는 `json_each()`로 확장
- mcp_memory_design.md 업데이트 완료 (스키마·SQLite 설계·도구별 쿼리 매핑·rebuild 방식)
- **4·5·6번(실제 구현)은 HP 노트북 Claude Code로 인계** — 구현 스펙 전달본 작성
  - ⚠️ 구현 전 확인: 두 PC sqlite3 ≥ 3.34 & FTS5+trigram 활성 여부 실측
  - ⚠️ 다음 설계 포인트: learnings.md 포맷(record 쓰기 ↔ rebuild 파싱 짝)

### 2026-06-24 (밤 세션 — db.py 쓰기 계열 구현, HP)
- 환경 확인: HP `sqlite3` 3.45.1 + FTS5/trigram OK → 설계 그대로 진행 확정
- learnings.yaml entry 포맷 확정 (옵션 B = YAML 멀티 문서 `---` 구분):
  - `safe_dump(allow_unicode=True)` 쓰기 / `safe_load_all()` 읽기 → 정규식 없이 견고
  - reason 필수(빈 값 `ValueError`), timestamp·id·machine은 서버 자동 생성
- recall/search 역할 분리 재확정: recall=작업 시작 전 맥락 로딩(폴백 있음), search=패턴 분석(정확 매칭+경향 요약). 내부 FTS는 헬퍼 공유
- 옛 구조 정리:
  - `orchestrator.py`의 `_append_learning` 호출 제거 + deprecated 표시 (커밋 `7b864ec`)
  - 옛 `memory/learnings.md` 삭제 + `*.bak`,`*:Zone.Identifier` gitignore (커밋 `9339acc`, `c210911`)
  - 설계 문서를 repo `docs/`로 이동 + CLAUDE.md에서 참조 (커밋 포함)
- **db.py 쓰기 계열 구현 + 검증 완료 (커밋 `08afc69`):**
  - `init_db`(스키마+FTS+트리거) / `record`(yaml-first→sqlite) / `rebuild_from_yaml`
  - 검증 4종 통과: yaml 포맷(`---`,한글 OK) / reason 없으면 ValueError / rebuild 항목수 일치 / FTS5+trigram OK
  - `config.py`에 `LEARNINGS_YAML_PATH`/`NAMU_DB_PATH`/`NAMU_MACHINE` 추가
  - `.env`에 `NAMU_MACHINE=hp` 설정, 테스트 yaml은 비움(첫 진짜 기록부터 시작)
- **다음 세션 시작점: db.py 읽기 계열(recall/search)** → 이후 mcp_server.py
- 교훈: learnings.yaml은 git 동기화 대상(진실의 원천)이나 db/는 캐시라 gitignore. record는 반드시 yaml 먼저 쓰고 sqlite 나중(DB 실패해도 복구 가능)

### 2026-06-24 (저녁 세션 2 — db.py 읽기 계열 + MCP 서버 구현·검증, HP)
- **recall 폴백 정책 토론 → 옵션 A 확정:** B(부족분 채우기)는 맥락 풍부하나 SessionStart 자동주입 시 매 세션 무관한 최신 기록까지 토큰 누적 → A(0개일 때만 폴백)+limit 작게가 효율적. append-only라 나중에 쉽게 변경 가능
- **db.py 읽기 계열 구현·검증 완료 (커밋 `d191a7d`):**
  - `_fts_query` 헬퍼 공유(3자+ FTS5 MATCH/2자↓ LIKE, MATCH는 phrase 감싸 특수문자 방어)
  - recall=최신순 정렬+0개일때 폴백 / search=bm25 정렬+폴백없음+전체매칭 outcome 경향요약
  - `_row_to_dict`로 tags json.loads 복원, 검증 7케이스 전부 통과
- **mcp_server.py 구현·검증 완료 (커밋 `573ae33`):** FastMCP로 `namu_recall`/`namu_record`/`namu_search` 3개 + stdio. per-call conn(스레드 안전), 모듈레벨 `_ensure_db()`(DB 없을때만 init+rebuild), docstring으로 도구 설명 노출. SDK 1.28 `@mcp.tool()` 인자없이 사용 OK
- **MCP Inspector로 stdio 실호출 검증 (6-a 완료):** `mcp dev`/`.venv/bin/python mcp_server.py`로 STDIO 연결 → 도구 3개 노출·docstring 확인, record→ULID 반환, recall로 항목 확인
- **검증 중 버그 2건 발견·수정:**
  - `machine=unknown`: `.env`가 `main.py` 진입점에만 로드돼 mcp_server.py 직접실행 시 폴백 → `config.py`로 일원화 (커밋 `2d885b3`) → machine=hp 정상
  - tags 이중인코딩: FastMCP가 JSON 문자열을 단일원소 리스트로 코어션 → MCP 래퍼 `_normalize_tags`로 경계 정규화 (커밋 `c5efc76`), 5케이스 검증
- **잔정리 커밋:** requirements에 mcp[cli] (`9e5f57b`), learnings.yaml git 추적 시작 (`697f470`)
- **NAMU가 자기 개발 교훈을 자기 메모리에 처음 기록** (machine=hp, verified_by=human 정상 항목 2건: .env 일원화 / tags 정규화)
- 교훈: ① 환경 로딩은 진입점 아닌 공통 config에 (모든 경로 일관) ② 외부(AI 클라이언트) 경계서 타입 코어션 발생 → 신뢰 경계(MCP 래퍼)서 입력 정규화. 둘 다 "여러 AI가 같은 MCP 붙음" 가치 때문에 반복될 패턴
- **다음 세션 시작점:** ① design.md 체크리스트 6번 [x] 반영 ② 6-b: Claude Code에 stdio 서버 등록(스코프 local/project/user 결정 — 시작 전 최신 등록방식 검색 확인)

### 2026-06-25 (MCP 서버 Claude Code 등록·검증 — 6-b 완료, HP)
- **등록 방식 최신 문서 재확인:** 공식 docs(code.claude.com/docs/en/mcp)로 교차검증. 스코프 3종 = local(`~/.claude.json`, 현재 프로젝트만, 비공유) / project(`.mcp.json`, git공유) / user(`~/.claude.json`, 전체 프로젝트). stdio 등록은 `claude mcp add [옵션] <이름> -- <명령> [인자]`, `--` 가 Claude 옵션/서버명령 구분자. (옛 이름: local=project, user=global — 지금 용어와 다름 주의)
- **스코프 토론 → local 확정:** NAMU A/B/C 구분상 등록은 플랫폼별 글루(포터블 아님) + MVP 검증 단계라 namu-agent로 좁힘. 승격 경로 = local→user(보편 기억)→플러그인(포터블 배포). project는 OS별 python 경로 차 + 플러그인이 대체라 건너뜀
- **learnings.yaml 위치 질문 정리:** 지금은 코드·노트가 같은 repo(BASE_DIR 고정)라 git clone 시 짝이 항상 맞음 → **고민 항목 아님 확정.** 플러그인화 때만 경로 분리(한 줄) 필요, 그때 챙김
- **HP에서 등록·검증 완료:**
  - `claude mcp add namu-memory --scope local --transport stdio -- "$(pwd)/.venv/bin/python" "$(pwd)/mcp_server.py"` → `~/.claude.json [project: namu-agent]`에 절대경로 등록
  - `claude mcp list`/`get`: Scope=Local, Type=stdio, Status=✓Connected, Command/Args 일치
  - **새 세션 `/mcp` 라이브 확인:** namu-memory ✓connected · 3 tools(recall/search/record) 노출
  - **namu_recall 실호출 검증:** Claude Code가 도구 호출 → 최근 6건 정상 반환(최신순 id DESC, outcome success/partial/failure 혼재), machine=hp·tags 리스트 정상(이중인코딩 버그 안 남), recall이 맥락 요약까지 수행
- **의미:** NAMU 자기개발 교훈(tags 정규화/.env 일원화)을 Claude Code가 작업 시작 시 꺼내볼 수 있게 됨 = C층(메모리 코어)이 실제 작업 루프에 처음 연결
- **검증 범위:** record는 일부러 미호출(learnings.yaml = source of truth라 테스트 잡음 방지). 쓰기 경로는 추후 실제 기록 거리 생길 때 자연 검증
- design.md 체크리스트 6번은 Claude Code가 repo서 6-a[x]/6-b[x]로 분리 갱신(커밋은 사용자 직접)
- **다음 세션 시작점:** 로드맵 11번 — Claude Code 글루(SessionStart 훅=기억 자동주입 / Stop·PostToolUse 훅=자동기록). 열린 질문(자동 vs 수동 호출)부터 정리

### 2026-06-25 (저녁 세션 — 로드맵 11번 종료: Claude Code 글루)
- **자동/수동 결정:** recall=SessionStart 훅 자동주입(결정론적, AI 턴 안 씀), record=수동 유지(CLAUDE.md 규칙). 자동 저장 보류 — "작업 완료" 시점이 모호해 자동기록 시 쓰레기 데이터/reason 부실 위험. (과거 교훈 #5 `[failure] learnings.md 자동기록 제거`와 동일 결론 — recall이 그걸 자동으로 꺼내와 재확인)
- **Claude Code 훅 스펙 최신 문서 확인** 후 설계 확정 (SessionStart=컨텍스트 주입 가능, Stop=매 턴 발화→리마인더는 게이트 필요, SubagentStop 별도)
- **`hooks/session_recall.py` 신규:** .venv 파이썬 실행 + `sys.path.insert`로 프로젝트 루트 추가. `config`·`memory.db` import, `_ensure_db`(DB 없으면 init+rebuild, 새 PC 첫 실행 대비), **`db.recall(conn, limit=5)` 기존 함수 그대로 재사용**, 결과를 `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":...}}`로 stdout 출력(`ensure_ascii=False`). **어떤 예외든 `except: sys.exit(0)`**(세션 시작 절대 안 막음), 0건이면 조용히 종료
- **`.claude/settings.local.json`:** SessionStart 훅 등록(HP 절대경로 command). `.gitignore`에 `.claude/settings.local.json` 추가
- **`CLAUDE.md`:** "교훈 저장 규칙" 섹션 추가 — 저장 대상(반복 패턴/근본원인/설계결정+이유) vs 제외(1회성/맥락없는 결과), reason 필수, 애매하면 사용자에 확인, 훅 자동화 금지+이유 명시
- **라이브 검증 통과:** 새 세션에서 아무 요청 없이 과거 교훈 5건 자동주입 확인(outcome/reason/tags 정상). C층(메모리 코어)이 작업 루프에 자동 연결된 첫 순간
- **커밋 `b5d4670` 푸시 완료** (`session_recall.py`, `CLAUDE.md`, `.gitignore`). `settings.local.json`은 gitignore라 제외(의도된 것)
- **(논의) 멀티에이전트 워커 — 검토중·미확정:** agy 확장점 사실확인 완료(결정표 참조). 핵심 원칙 = 오케스트레이터-워커는 엔진 무관(Claude Code/agy 대칭), 실행 차이는 "워커 spawn 어댑터" 한 겹으로 흡수. 단 전제 일부 미검증(Anthropic CLI 래핑 차단 시점·Gemini 무료 API 약관) → 12/16번 본격화 때 검증 후 확정. 상세는 로드맵 하단 "🔭 검토중" 참조

### 2026-06-25 (밤 세션 — 로드맵 12번 MVP: `/namu-task` 멀티에이전트 라우팅)
- **전제 검증(검색 2건) 후 워커 구성 확정** — 상세는 결정 테이블 참조. 핵심: 검수도 같은 구독 안 네이티브 서브에이전트로(무료 Gemini는 코드 학습돼 부적합, `-p`는 별도 Agent SDK 크레딧이라 "구독 안 저렴" 아님). 이종 엔진은 override 후순위 → MVP는 native만. "어쩔 수 없이 같은 구독 안"이 보안·비용상 최적이란 결론
- **최신 스펙 확인:** skills/commands 통합(2.1.3), 서브에이전트=`.claude/agents/*.md`+`model` 필드 비용 라우팅, Task→Agent 개명. 11번 훅 스펙 검증처럼 본격 구현 전 교차확인
- **중요 기술 함의:** Claude Code 네이티브 서브에이전트(Agent 도구)는 같은 Claude 모델만 → "코딩=Claude, 검수=Ollama" 이종 혼합은 네이티브로 불가, bash subprocess 필요 = "워커 spawn 어댑터"의 진짜 이유. 사용자가 기본=native 택한 덕에 MVP서 이종 복잡도 회피
- **5개 파일 생성** (Claude Code, 커밋 직전 멈춤→사용자 diff 검토 후 직접 커밋·푸시):
  - `.claude/skills/namu-task/SKILL.md` — 7단계 오케스트레이션(recall→분할→명단확인→coding→review→**게이트**→record)
  - `.claude/agents/namu-coder.md`(model=sonnet) / `.claude/agents/namu-reviewer.md`(model=haiku, read-only)
  - `namu_workers.yaml`(repo 루트, 기본 전부 native, 외부 엔진 자리만 비움) / CLAUDE.md "작업 오케스트레이션 규칙" 3줄 추가
  - `.claude/`는 `settings.local.json`만 gitignore, `skills/`·`agents/`는 git 추적 확인
- **라이브 검증(새 세션) 통과:** `/agents`로 워커 2개(coder·sonnet/reviewer·haiku) 등록 확인 → 작은 작업(yaml 주석 추가)으로 회사 한 바퀴 — recall(교훈0→진행) → coder 위임 → reviewer가 `yaml.safe_load` **실파싱 검사** → pass → 7단계서 "단순 주석이라 일반화 교훈 없음" **판단해 record 생략**. 11번 저장 규칙이 실제로 작동(쓰레기 기록 방지)
- **미검증 잔여:** 검수 게이트 fail 멈춤은 이번 pass라 미발동 → 다음 세션서 의도적 fail 작업으로 확인 필요
- **진행 방식 확인:** Claude Code는 diff까지만, 커밋·푸시는 사용자 직접. 권한은 "Yes, this time only"만. plan.md는 대화창서 갱신→다운→repo 커밋
- **다음 세션 시작점:** ① 이 plan.md 갱신 커밋 ② 검수 게이트 fail 테스트 ③ (이후) 13번 플러그인 패키징 또는 16번 agy 글루

### 2026-06-26 (검수 게이트 fail 라이브 검증 — 12번 완전 종료)
- 지난 세션 미검증 잔여(게이트 fail 멈춤) 검증: 확실한 fail 유발 위해 닫는 괄호 누락 파이썬을 `/tmp`에 "수정 금지·그대로 작성"으로 고정(coder가 자동수정해 pass 나는 것 방지)
- 라이브 흐름: recall(교훈0→진행)→coder가 깨진 코드 그대로 Write→reviewer(haiku)가 `python -m py_compile` 실행→`SyntaxError: '(' was never closed` line4 잡음→6단계 게이트 🔴FAIL
- 게이트 4동작 전부 확인: ①자동재실행 안 함 ②fail 이유(py_compile 원문) 보고 ③재실행/통과/중단 3선택 ④③중단 선택→record 없이 종료(11번 저장규칙 작동, 테스트 잡음 메모리 미저장)
- 의미: 검수 워커가 형식적 OK/NG가 아니라 **실제 검증도구(py_compile)를 돌려** 그 출력 근거로 판정함을 fail 케이스서 입증. 12번 pass(06-25)+fail(06-26) 양면 검증 완료
- 진행방식 재확인: Claude Code 자동제안 프롬프트("plan.md 커밋·푸시")는 실행 안 함 — plan.md는 대화창 갱신→사용자 커밋, 커밋·푸시는 사용자 직접
- **다음 세션 시작점:** 13번 플러그인 패키징 또는 16번 agy 글루

## 🤖 AI 호출 방식 (어댑터 구조) — 확정
```
내 시스템
    ↓
AI 어댑터 (연결 다리)
    ├── 로컬 모델:   adapters/ollama.py               (Ollama - 무료, priority 1)
    ├── Claude 구독: adapters/claude_subscription.py  (Agent SDK - priority 2) ✅ 구현완료
    ├── Claude API:  adapters/claude_api.py            (API 키 - priority 3)   ✅ 구현완료
    ├── GPT API:     adapters/gpt_api.py               (API 키 - priority 4)   ✅ 구현완료
    └── Gemini API:  adapters/gemini_api.py            (API 키 - priority 5)   ✅ 구현완료
```

**Gemini 구독 어댑터:** ❌ 포기 (agy non-TTY 버그 + 쿼터 불안정). Gemini는 API 키 방식으로만 사용.

## 🏛️ 설계 방향: 하네스 기반 + 자동학습 추가

### 🔑 핵심 통찰 (2026-06-24): 독립성은 인터페이스가 아니라 메모리에 있다

NAMU의 3대 요구사항(① AI 비종속 ② 메모리 맥락 공유 ③ 자가발전)은 전부
**메모리/학습 레이어**의 이야기지 인터페이스(CLI냐 플러그인이냐)의 이야기가 아니다.
→ 진짜 차별점은 harness(실행 엔진)가 아니라 **memory + learning 코어**.

### "하네스"의 두 층위 구분
- **A층 (실행 엔진):** 모델 호출→도구 실행→재호출 루프, 파일편집, bash, 샌드박스, 권한.
  Claude Code/agy가 수년간 다듬은 부분 → **빌려쓴다** (직접 구현 안 함)
- **B층 (하네스 엔지니어링):** CLAUDE.md 설정, 훅으로 실행 강제, 오케스트레이터-워커,
  승인 게이트 → **NAMU가 만든다**
- **C층 (메모리/학습):** learnings + SQLite + 자동학습 루프 → **NAMU의 심장, 직접 만든다**

```
        자체 CLI (기각)            플러그인 방식 (채택)
  C층  │ 메모리/학습  │ 직접     │ 메모리/학습  │ 직접 (심장)
  B층  │ 하네스엔지   │ 직접     │ 하네스엔지   │ 직접
  A층  │ 실행 엔진    │ 직접😩   │ 실행 엔진    │ 빌려씀 (Claude Code/agy)
```

### Claude Code 확장 포인트 매핑 (공식 문서 확인됨)
| NAMU 레이어 | 얹는 곳 | 비고 |
|---|---|---|
| 메모리 코어 (C층) | **MCP 서버** | 벤더 중립 — agy/Cursor에도 붙음 (포터블) |
| 세션 시작 시 기억 주입 | Hook (SessionStart) | Claude Code 전용 글루 |
| 작업 후 자동 기록 | Hook (Stop/PostToolUse) | 자가학습 루프 |
| 항상 지킬 규칙 | CLAUDE.md | "작업 전 메모리 조회" 등 |
| 작업 절차/검증 | Skill | `/namu-task` 오케스트레이션 |
| 전체 패키징 | Plugin | 한 번에 설치 배포 |

**⚠️ 포터블한 건 MCP뿐.** Hook/Skill/CLAUDE.md는 Claude Code 전용.
→ 구조: **MCP 메모리 코어(한 번만 제작) + 플랫폼별 얇은 글루**(Claude Code용 / agy용)

---

### 하네스에서 가져올 것 (B층):
- 파일이 곧 기억 (task.md / brief.md / result.md / log.md)
- 오케스트레이터-워커 구조
- 워커 호출 전 승인 게이트
- append-only 로그 (삭제 금지)
- 벤더 독립 원칙

**하네스에서 우리가 추가/변경할 것:**
- 수동 학습 → **자동 학습 루프** (핵심 차별점)
- 파일만 → **파일 + SQLite** (분석/패턴 추출용)
- GitHub 동기화 (다중 PC 지원)
- AI 어댑터 (API + Claude 구독 + 로컬 모두 지원)

## 🛠️ 개발 방식
- 하네스를 참조하되 처음부터 직접 구현
- 이유: 시스템 구석구석을 완전히 이해하고 통제하기 위해

## 💻 개발 환경
| PC | 경로 | 사양 | 역할 |
|---|---|---|---|
| 삼성 노트북9 | C:/Users/onmiso/namu-agent | i5-5200U, RAM 8GB, Win10, Python 3.12, Git, Node.js v24 | 기획/문서/가벼운 작업 |
| HP 노트북 | ~/project/namu-agent | RAM 16GB, WSL, Claude Code v2.1.186, Node.js v24 | 주 개발 환경 |

## 🔧 기술 스택 확정
- 언어: Python 3.12+
- DB: SQLite (로컬 패턴분석 캐시)
- 동기화: GitHub (memory/learnings.yaml)
- AI 어댑터: anthropic SDK + claude-agent-sdk + openai SDK + ollama + google-genai
- 개발도구: Claude Code (HP), VS Code (삼성)

## 📁 전체 폴더 구조
```
namu-agent/
├── core/
│   ├── __init__.py
│   └── orchestrator.py        ← 핵심 엔진 ✅
├── adapters/
│   ├── __init__.py
│   ├── base.py                ← 추상 기반 클래스 ✅
│   ├── ollama.py              ← 로컬 모델 (priority 1) ✅
│   ├── claude_subscription.py ← Claude 구독 Agent SDK (priority 2) ✅
│   ├── claude_api.py          ← Claude API 키 (priority 3) ✅
│   ├── gpt_api.py             ← GPT API 키 (priority 4) ✅
│   └── gemini_api.py          ← Gemini API 키 (priority 5) ✅
├── memory/
│   └── learnings.yaml         ← 공용 append-only 기억 (git 동기화) ✅
├── tasks/                     ← 작업별 기록 (gitignore, 로컬 전용) ✅
├── db/                        ← SQLite (gitignore, 로컬 캐시) ✅
├── .venv/                     ← Python 가상환경
├── main.py                    ← CLI 진입점 ✅
├── config.py                  ← 설정 (우선순위, API 키 등) ✅
├── requirements.txt           ← 패키지 목록 ✅
├── .env                       ← API 키 (gitignore) ✅
├── .env.example               ← 키 템플릿 ✅
├── .gitignore                 ← tasks/, db/, .env 제외 ✅
└── CLAUDE.md                  ← Claude Code용 프로젝트 설명 ✅
```

## 🔄 검증 루프 (Harness Engineering 핵심 요소)
```
작업 유형 감지
   ├── 코딩 작업  → 린터 + 테스트 자동 실행으로 검증
   ├── 문서 작업  → 형식/완성도 체크로 검증
   ├── 분석 작업  → 기준 충족 여부로 검증
   └── 기타 작업  → 사용자 정의 검증
```

**핵심 원칙:** 실패 시 프롬프트 수정이 아니라, 구조적으로 재발 방지하는 피드백 루프

## 🧠 메모리 구조 (확정)
```
[공유] memory/learnings.yaml  ← git으로 PC간 동기화 (진짜 기억, append-only)
           ↓ pull 후 자동 변환 (미구현)
[로컬] db/namu.db           ← 빠른 검색/패턴분석용 SQLite (캐시, gitignore)
```
- learnings.yaml: 모든 PC가 추가만 가능한 공용 메모장
- SQLite: learnings.yaml를 구조화해서 패턴분석에 쓰는 로컬 캐시
- git pull 시 learnings.yaml 최신화 → SQLite 자동 재생성 (구현 예정)

## 📋 다음 할 일
1. ✅ GitHub namu-agent 저장소 생성
2. ✅ 기본 폴더 구조 + 어댑터 4개 + 오케스트레이터 생성
3. ✅ claude_subscription.py 구현 (Claude Agent SDK)
4. ✅ 전체 동작 테스트 통과
5. ✅ GitHub push 완료
6. ✅ gemini_api.py 구현 (google-genai SDK)
7. ✅ main.py 구현 (CLI 진입점, 단일명령 + REPL 모드)
8. ✅ 버그수정: UnicodeEncodeError & async generator 오류 (e667ae3)
9. ✅ 아키텍처 방향 결정: 플러그인 + MCP 메모리 코어 (2026-06-24)

### 🎯 새 방향 작업 (우선순위순)
10. ✅ **MCP 메모리 서버 구현 — 완료** — `namu_recall`/`namu_record`/`namu_search`
    - ✅ 설계 확정 (스키마·SQLite·FTS·entry 포맷, docs/mcp_memory_design.md 참조)
    - ✅ db.py 쓰기 계열 — init_db/record/rebuild_from_yaml, 검증 완료 (커밋 `08afc69`)
    - ✅ db.py 읽기 계열 — recall(맥락 로딩+폴백)/search(FTS+요약), 검증 완료 (커밋 `d191a7d`)
    - ✅ mcp_server.py — FastMCP 도구 3개 + stdio (커밋 `573ae33`)
    - ✅ .env 일원화(`2d885b3`) + tags 경계 정규화(`c5efc76`) 버그수정
    - ✅ MCP Inspector stdio 실호출 검증 (6-a)
    - ✅ Claude Code에 stdio 서버 등록·라이브 검증 (6-b, local 스코프, namu_recall 실호출 통과)
11. ✅ **Claude Code 글루 — 완료** — SessionStart 훅(기억 자동주입) + CLAUDE.md 교훈 저장 규칙
    - ✅ `hooks/session_recall.py` — `db.recall(limit=5)` 재사용, 어떤 예외든 `exit 0`(세션 시작 안 막음), 새 PC 대비 `_ensure_db`, 새 세션 라이브 검증 통과
    - ✅ `.claude/settings.local.json`에 SessionStart 훅 등록 (로컬 전용, gitignore)
    - ✅ `CLAUDE.md` 교훈 저장 규칙 (저장은 AI 수동 호출, 자동기록 보류) — 커밋 `b5d4670` 푸시 완료
    - 🔶 11-b (보류): record 자동화는 누락 관측 시 게이트형 Stop 리마인더로 재검토
12. ✅ **CLAUDE.md + `/namu-task` 스킬 — 완료(MVP)** — 멀티에이전트 워커 라우팅
    - ✅ 전제 검증(검색): Anthropic `claude -p` 허용/OAuth 추출 금지·`-p`는 별도 Agent SDK 크레딧 / Gemini 무료 API는 학습+사람리뷰라 검수 부적합·Pro 2026-04 유료전환 (결정 테이블 참조)
    - ✅ 워커 구성 확정: 기본=메인 AI 네이티브 서브에이전트(같은 구독풀·비용0·보안OK). 이종 엔진은 override 후순위, MVP는 native만
    - ✅ `.claude/skills/namu-task/SKILL.md`(7단계 오케스트레이션) + `namu-coder`(sonnet) + `namu-reviewer`(haiku, read-only) + `namu_workers.yaml`(기본 native) + CLAUDE.md 규칙 3줄
    - ✅ 라이브 검증 통과: recall(교훈0→진행)→coder 위임→reviewer가 yaml 실파싱 검사→pass→record는 "단순작업이라 교훈없음" 판단해 적절히 생략(11번 저장 규칙 실작동)
    - ✅ 검수 게이트 fail 멈춤 라이브 검증 완료(2026-06-26): 의도적 SyntaxError 작업 → reviewer가 `py_compile` 실행 → SyntaxError 원문 보고 → 게이트 ①자동재실행안함 ②이유보고 ③3선택(재실행/통과/중단) 정상 → ③중단 선택 시 record 없이 종료. pass(06-25)+fail(06-26) 양면 검증 완료
13. ⬜ 전체를 Claude Code 플러그인으로 패키징
    - ⚠️ 이 단계서 코드(별도 설치폴더)·노트(git repo)가 갈라짐 → learnings.yaml 경로를 BASE_DIR 고정에서 env/`${CLAUDE_PROJECT_DIR}`로 분리(한 줄)
14. ⬜ git pull 후 SQLite 자동 재생성 기능 구현
15. ⬜ 삼성 노트북에서 git pull 후 동기화 테스트
16. ⬜ (나중) agy용 글루 — Antigravity 방식 설정/훅
    - ℹ️ 사실확인 완료(2026-06-25): agy도 MCP 호스트(`~/.gemini/config/mcp_config.json` + `/mcp`), 훅 있음(`hooks.json`, PreToolUse/PostInvocation/Stop+세션시작, Gemini CLI 동일 포맷), 네이티브 서브에이전트(`/agents`,`agy -p`). 단 MCP env var 버그·non-TTY stdout #76·훅 경로 버그(최근 수정) 있어 착수 시 재검증

### 🔭 멀티에이전트 워커 구조 — 12번서 MVP 확정·검증, 이종 엔진은 후속
> 다른 창에서 시작했던 설계. **12번(2026-06-25)서 전제 검증 + 워커 구성 확정 + 라이브 검증 완료.** 아래는 확정 결과와 남은 작업.
- ✅ **방향 확정:** 오케스트레이터 + 코딩 워커 + 검수 워커. 단 "검수는 저렴한 경로로"는 검증 결과 **기각** — 무료 Gemini는 코드 학습돼 보안 부적합, `-p`는 별도 크레딧. 기본은 같은 구독 안 네이티브 서브에이전트(검수=haiku로 비용만 절감)
- ✅ **핵심 원칙 유지:** 오케스트레이터-워커는 **엔진 무관**(Claude Code/agy 대칭). 실행 차이(Agent 도구 vs `/agents` vs `-p`)는 **"워커 spawn 어댑터" 한 겹**으로 흡수 — 단 세 경로가 과금상 비대칭이라 어댑터가 과금·보안 등급도 메타데이터로 들어야 함
- ✅ **공유 기억 검증됨:** 워커가 같은 MCP(namu-memory) 호출 → 교훈 공유. 12번 라이브 검증서 coder/reviewer가 같은 메모리 코어 바라봄 확인(현재는 둘 다 native)
- ✅ **미검증 전제 → 검증 완료:** Anthropic CLI 래핑(`-p` 허용/OAuth 추출 금지) / Gemini 무료 API(학습+사람리뷰)·Pro 유료화. 상세 결정 테이블
- ⬜ **남은 작업(후속):** ~~① 검수 게이트 fail 멈춤 라이브 확인~~ ✅완료(06-26) ② 이종 엔진 워커(Ollama/유료Gemini) bash subprocess spawn 어댑터 + 설치·실행 초기 override 마법사 ③ agy 대칭 구현(16번, `/agents`·`agy -p`로 같은 워커 구조)

### 보류/기각
- ❌ gemini_subscription.py (agy non-TTY 버그 + 쿼터)
- 🔵 기존 어댑터(adapters/)·main.py는 "API 키 폴백 + 독립 실행용"으로 유지
- ⬜ Ollama 설치 후 로컬 모델 테스트
