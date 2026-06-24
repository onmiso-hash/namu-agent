# 나만의 멀티에이전트 시스템 기획

> 📅 시작: 2026-06-22 | 대화를 통해 점진적으로 채워나가는 문서

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
10. 🔶 **MCP 메모리 서버 구현** — `namu_recall`/`namu_record`/`namu_search`
    - ✅ 설계 확정 (스키마·SQLite·FTS·entry 포맷, docs/mcp_memory_design.md 참조)
    - ✅ db.py 쓰기 계열 — init_db/record/rebuild_from_yaml, 검증 완료 (커밋 `08afc69`)
    - 🔶 db.py 읽기 계열 — recall(맥락 로딩+폴백)/search(FTS+요약) ← **다음 시작점**
    - ⬜ mcp_server.py — FastMCP 도구 3개 + stdio
    - ⬜ MCP Inspector 테스트 → Claude Code stdio 등록
11. ⬜ Claude Code 글루: SessionStart 훅(기억 주입) + Stop/PostToolUse 훅(자동 기록)
12. ⬜ CLAUDE.md + `/namu-task` 스킬 작성
13. ⬜ 전체를 Claude Code 플러그인으로 패키징
14. ⬜ git pull 후 SQLite 자동 재생성 기능 구현
15. ⬜ 삼성 노트북에서 git pull 후 동기화 테스트
16. ⬜ (나중) agy용 글루 — Antigravity 방식 설정/훅

### 보류/기각
- ❌ gemini_subscription.py (agy non-TTY 버그 + 쿼터)
- 🔵 기존 어댑터(adapters/)·main.py는 "API 키 폴백 + 독립 실행용"으로 유지
- ⬜ Ollama 설치 후 로컬 모델 테스트
