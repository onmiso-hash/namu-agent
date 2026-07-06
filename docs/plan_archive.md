# plan.md 세션 로그 아카이브

plan.md에서 이관된 과거 세션 로그 아카이브(2026-06월분). 원문 그대로(verbatim) 보존. 최신 세션은 [plan.md](plan.md)를 참조. 이관일 2026-07-06(#19 plan.md 정리).

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

### 2026-06-26 (저녁 세션 — 상태 메모리 설계: `context.md` 되살리기, 대화창)
- **발단:** 13번(플러그인) vs 16번(agy) 정하려다 **메모리에 빠진 한 층** 발견 → 13/16 보류하고 먼저 처리
- **진단:** 메모리는 **상태(어디까지·다음, 덮어쓰기) + 교훈(왜, 누적)** 두 종류. NAMU는 교훈(learnings.yaml)만 있고 상태 누락. 정답은 하네스 `context.md`인데 초기 오케스트레이터가 task/result/log만 이식하고 빠뜨린 게 근본원인
- **구조 확정:** 변경빈도로 3파일 분리 — `task.md`(목적, 불변) / `context.<machine>.md`(현재상태, 덮어쓰기, PC별) / `log.md`(이력, append). **log.md=진실의 원천, context=재구성 가능한 뷰**(learnings.yaml↔SQLite 패턴 재사용)
- **사용자 질문 3건 반영해 설계 교정:** ① task.md를 context로 접으면 목적이 log 재생성서 복원 안 됨 → **분리 유지** ② 동시작업 충돌은 소스뿐 아니라 *상태파일*도 대상 → **context PC별 분리**로 해소 ③ plan.md는 엔진 부품 아님(사람이 쓰는 기획일지), 다만 프로젝트단위 상태메모리 노릇 → 자동화는 후속
- **시뮬레이션 검증**(HP=프론트/삼성=백, 같은 task A1): ①이어가기 ②병합 ③완료확인 ④초기화 플로우. 결론 = PC별 분리+log append면 **상태 소실 없음**, 막지 못하는 건 논리모순뿐(log에 드러내 화해). 사용자 결론: 평소 **한 번에 한 PC**면 이 고민 대부분 소거, 안전망은 깔려 있음
- **`/namu-task` 스킬(현행 7단계) 확인** → 교훈 북엔드(1.recall/7.record) **양옆에 상태 북엔드 추가** 설계 확정. 새로 정할 것 = **작업 이름(slug)**, **3파일 템플릿**
- **자동화 정합성:** 11번 "자동기록 보류"는 교훈 한정 → 상태는 헐겁게 자동 갱신 안전
- ⚠️ **구현 전제:** `tasks/` gitignore → **git 추적 전환** 필요(다중 PC 공유의 전제)
- **다음 세션 시작점:** ① 3파일 템플릿 확정 ② 작업이름(slug) 방식 ③ `/namu-task` SKILL.md 개정본 설계 → ④ Claude Code 구현 프롬프트(+ `tasks/` git 추적). 13/16은 그 뒤

### 2026-06-26 (저녁 세션 2 — 상태 메모리 구현·검증 완료, 대화창+HP)
- **설계 마무리(대화창):** 3파일 템플릿 확정(task.md/context.<machine>.md/log.md, 각 칸·태그 5종) + slug 방식(AI 제안→확인, `state-memory` 슬러그 확정) + `/namu-task` 개정안(진입 분기 신규/재진입, 상태 북엔드, 안전장치)
- **사용자 질문으로 교정:** ① "재진입"=같은 작업 다시 열기(다른 PC 이어받기 포함) ② recall(교훈)과 context복원(상태)은 **별개 관심사** → 재진입은 파일로 상태 복원되니 recall 생략 가능 ③ 완료 context는 폴더 졸업 없이 `▶ 다음`만 비움(본체는 log.md)
- **Claude Code 구현(HP, diff까지만→사용자 직접 커밋):** `.gitignore` `tasks/` 제거(db/는 유지) + `/namu-task SKILL.md` 개정. `git rm --cached` 불필요 확인(tasks/가 ignored라 인덱스에 없었음→`.gitignore` 빼면 바로 untracked). **커밋 `9f9f71f` main 푸시**(2 files changed, 127+/13-)
- **라이브 검증(test-run 버리는 슬러그):**
  - 신규 경로: `tasks/test-run/` 없음→신규 분기 / machine=hp 감지 / task.md 목적·완료조건 **물어봄**(멋대로 안 채움) / 3파일 생성(**context.hp.md 포함** — NAMU 초기 누락분이 바로 이것!) / log `[시작]`→`[완료]` 도장+태그 / 완료처리로 `▶ 다음`=`(완료)` / recall은 "파일생성 자체가 목적"이라 적절히 생략
  - 재진입 경로: `tasks/test-run/` 있음→재진입 분기 / 3파일 읽어 상태 복원(목적 재질문 X) / "다른 PC 흔적 없음(context.hp.md만)" 정확 판단해 통과 / 완료작업 재진입을 "이어갈 미완성 단계 없음"으로 올바르게 인식(명시 설계 안 한 케이스인데 똑똑하게 처리)
  - 검증 후 `rm -rf tasks/test-run/`(테스트 산출물이라 커밋 안 함)
- **의미:** NAMU 메모리에 빠져 있던 **상태 층**이 작업 단위 3파일로 복구됨. 신규·재진입 양쪽 실동작 증명. 교훈(learnings.yaml)+상태(tasks/) 두 그릇이 갖춰짐
- **다음 세션 시작점:** 13번 플러그인 패키징(우선) 또는 16번 agy 글루(버그 3개 재검증 선행). 별건=CLAUDE.md stale 점검(learnings.md→.yaml)

### 2026-06-26 (저녁 세션 3 — 로드맵 13번: 플러그인 패키징 완료, 대화창+HP)
- **설계 결정(대화창):** 공식 Claude Code 플러그인 스펙 재확인(`.claude-plugin/plugin.json`만 숨김폴더, 나머지 컴포넌트는 플러그인 루트, `.mcp.json`+`${CLAUDE_PLUGIN_ROOT}`). 결정 4건 = 데이터 분리(`NAMU_HOME` env+BASE_DIR 폴백) / 의존성(uv+PEP 723) / 소스 배치(`namu-plugin/` 서브폴더 git mv) / 배포 범위(로컬 플러그인, 공개 보류). 상세는 결정 테이블 06-26 행
- **Claude Code 구현(HP, diff까지만→사용자 직접 커밋):**
  - 0단계 현황 보고: config.py가 `load_dotenv(BASE_DIR/".env")` 봄 → 캐시선 무력이라 NAMU_HOME/NAMU_MACHINE 셸 환경변수 주입으로 해결(첫 갈림길 결론). uv 미설치 발견 → 사용자가 `curl -LsSf https://astral.sh/uv/install.sh \| sh`로 직접 설치(`~/.local/bin/uv`)
  - 1단계: config.py에 `NAMU_HOME` 도입, learnings/db/tasks 경로 4개 `BASE_DIR`→`NAMU_HOME` 전환(폴백 유지)
  - 2단계: `git mv`로 코드 5개 `namu-plugin/`로 이동(`config.py`/`db.py`[memory/→]/`session_recall.py`[hooks/→]/`mcp_server.py`/`SKILL.md`[.claude/→]). `memory/`·`tasks/`·`db/`는 루트 잔류 확인
  - 3단계: `mcp_server.py` 상단 PEP 723 블록(4개 핀), import `memory.db`→`db` 평탄화
  - 4·5단계: `.mcp.json`(uv run --script) + `hooks/hooks.json`(SessionStart=session_recall.py 자동주입). **session_recall.py는 실제 `hooks/` 위치 유지**(parent.parent sys.path 트릭이 그걸 전제, 옮기면 변경점만 늘어 비추)
  - 6단계: `/namu-task SKILL.md`의 tasks 경로 `${NAMU_HOME:-.}/tasks/<slug>/` 보정
  - 신규 4: `plugin.json`/`marketplace.json`/`.mcp.json`/`README.md`/`hooks.json`
- **로컬 검증 통과:** `uv run --script mcp_server.py` 의존성 38개 설치 후 STDIO 대기 정상(빈 JSON validation error=인자없이 띄운 예상 응답) / `NAMU_HOME` 박고 session_recall.py 실행→과거 교훈 5건 JSON 출력 정상 / import 평탄화 무오류
- **잔해 정리:** untracked `tasks/2026...` 12개 발견 → log.md 1건 열어 확인(`task_id`=폐기 타임스탬프 ID, `adapter=ClaudeSubscriptionAdapter`=폐기 구독어댑터, `success:False`/1.6s=초기 어댑터 테스트 빈 껍데기) → **초기 죽은 오케스트레이터 잔해 확정, `rm -rf tasks/2026*`로 삭제**(git 한 번도 안 올라간 로컬 잔해라 이력 손실 0, 새 slug 방식으로 정리). 이번 13번 커밋엔 미포함(staged 아님)
- **커밋·푸시 완료:** `git add namu-plugin/` → 10개 staged(이동 5 + 신규 5, `113+/18-`) → 데이터 폴더 미포함 확인 → 커밋·푸시(사용자 직접)
- **의미:** A/B/C층 중 글루(B)+코어(C)가 **로컬 플러그인 단위로 패키징**됨. 코드(캐시 복사)와 데이터(git 동기화)가 `NAMU_HOME`으로 깔끔히 분리 → 멀티 PC 포터블 배포의 토대
- **미검증 잔여:** 진짜 플러그인 캐시 설치(`/plugin install`) 상태 + 삼성 동기화는 15번에서. agents 2개 이동은 16번에서
- **다음 세션 시작점:** 14번(git pull 후 SQLite 자동 재생성) 또는 16번(agy 글루, 버그 3개 재검증 선행). 별건=CLAUDE.md stale 점검(learnings.md→.yaml)

### 2026-06-26 (저녁 세션 4 — 로드맵 14번: SQLite 캐시 자동 재생성 완료, 대화창+HP)
- **설계 결정(대화창):** #14는 `rebuild_from_yaml()` 함수 자체가 아니라 **"언제 부를지" 배선**이 핵심(rebuild는 08afc69서 이미 구현). 둘 정함 —
  - **신호 = 카운트 비교**(yaml `^id:` 수 vs db `COUNT(*)`), mtime 기각. mtime은 "같은-초 pull"이면 `>` 비교가 조용히 놓쳐 캐시 구멍(silent stale) 위험. 카운트는 시간 무관 + record가 yaml·db 둘 다 쓰니 평소 일치(헛 rebuild 0) + 부분 쓰기 자동 치유. 부팅 때 파일은 파싱 없이 줄만 세서 rebuild보다 가벼움
  - **트리거 = `_ensure_db()`(서버 부팅).** 세션마다 stdio 서버 재기동 → pull 직후 첫 세션이 곧 트리거(git 훅·수동 명령 불필요). git post-merge 훅은 PC별 설치 부담이라 기각
- **Claude Code 구현(HP, diff까지만→사용자 직접 커밋):**
  - `db.py`에 함수 2개(`_COLS` 직전): `count_yaml_docs(yaml_path)`(줄 스캔 `startswith("id:")`, 파일 없으면 0) / `cache_is_stale(yaml_path, db_path)`(yaml count ≠ db COUNT면 True, **`OperationalError`=테이블 없는 빈 db도 True** 처리)
  - `mcp_server.py` `_ensure_db()`: db 없으면 init+rebuild+`return`(신규), 있으면 `cache_is_stale()` True일 때 rebuild 단독 호출. import에 `cache_is_stale` 추가
  - `test_cache_stale.py` 신규 — 4케이스(count일치→stale아님 / yaml>db[pull 시뮬]→stale / yaml없음+db0행→일치 / row1개 DELETE→stale→rebuild로 복구), 전부 `tempfile.TemporaryDirectory`로 **비파괴**(원본 learnings.yaml 안 건드림)
- **커밋 전 사용자 diff 검토(3종 확인):** ① `rebuild_from_yaml`가 `unlink(missing_ok=True)→init_db()`로 스키마 자체 재생성 확인(`sed`로 본문+grep 11/114/115줄) → stale 경로 rebuild 단독 호출 안전 ② `git status`에 `learnings.yaml` 안 뜸 + 테스트 전부 tempfile 확인(비파괴 OK) ③ `cache_is_stale`가 `conn` 인자 없이 `with sqlite3.connect` 자체개통+`except OperationalError` 확인(읽기계열 주입 규칙 안 건드림)
- **커밋 `7e81906`**(3 files changed, 134+/1-, `test_cache_stale.py` 신규). 코드만 커밋(문서·교훈 별도)
- **알아둘 점(블로커 아님):** rebuild가 `INSERT OR IGNORE`라 만약 yaml에 id 중복 있으면 db_count<yaml_count로 매 부팅 무한 rebuild 가능 — 단 id가 ULID라 충돌 사실상 0. yaml 실수 삭제 시 빈 yaml로 rebuild돼 db 비워짐(yaml=진실의 원천 모델상 맞는 동작이나 파괴적, git 추적본이라 평소 안 일어남)
- **의미:** `learnings.yaml`(원본) ↔ SQLite(캐시) 사이 동기화 배선 완성. 다른 PC에서 push한 교훈을 pull로 받으면 다음 세션 부팅 때 자동으로 검색 캐시에 반영됨 = 멀티 PC "공유 기억"의 마지막 연결고리(15번 실검증의 토대)
- **미해결 잔여 없음.** design.md 체크리스트 7번 `[x]` 처리
- **다음 세션 시작점:** 15번(삼성 동기화 + 플러그인 캐시 설치·셸 환경변수 주입 실검증 — 13번 미검증 잔여 합류) 또는 16번(agy 글루, 버그 3개 재검증 선행). 별건=CLAUDE.md stale 점검(learnings.md→.yaml)

### 2026-06-26 (저녁 세션 5 — 로드맵 15번: 삼성 동기화 검증 + 윈도우 unlink 버그 발견, 대화창+삼성)
- **선행: CLAUDE.md stale 절반 재작성·커밋(대화창→repo).** 피벗 이전(독립 CLI+커스텀 오케스트레이터+adapters/) 구조가 통째로 남아있었음. `core/`·`adapters/` 폴더표서 제거(죽은 코드, 실물 잔류) / `namu-plugin/`·`.claude/` 추가 / `learnings.md`→`learnings.yaml`(3곳) / `tasks/` 3파일(`task.md`/`context.<machine>.md`/`log.md`) 정정 / `db/`=FTS5 검색캐시(pull 후 자동재생성) / "어댑터 우선순위"→"에이전트 실행 모델" 교체 / 개발원칙 1·2 재작성 / 메모리 구조 섹션 신설 / 기술스택 MCP·uv·FTS5·ULID 보강. 푸시 후 삼성 pull로 동기화 확인(5342B/75줄 일치)
- **진행 순서 확정:** ①삼성 상태점검 → ②HP 푸시정리 → ③HP push → ④삼성 pull → ⑤#14 실전검증. **#15(검증) 먼저, #16(agy)은 그 위에** — 토대 검증 전 복잡도 얹으면 디버깅 층 두꺼워짐
- **① 삼성(Windows 네이티브 PowerShell, `D:\Project\namu-agent`) 환경점검 — 전부 통과:** Python 3.12.3 / SQLite 3.45.1(≥3.34) / **FTS5 OK** / Claude Code 2.1.186. 초기 미충족 2건 즉시 해결 — `uv` 미설치→`pip install uv`(0.11.24) / `NAMU_MACHINE` 미설정→`SetEnvironmentVariable(...,"samsung","User")` 후 새 창서 반영 확인
- **②③ HP 푸시 — 할 것 없음:** `git log origin/main..HEAD` 빈 출력 = HP 모든 작업(CLAUDE.md 포함) 이미 origin 동기화 완료
- **④ 삼성 pull — 깔끔한 fast-forward** `3aba383..f39e49a`(삼성 클론은 6/23 시점 = 깨끗한 stale → #14 테스트 이상적). 36 files/3131+. `namu-plugin/`·`docs/`·`.claude/`·`memory/learnings.yaml`(77줄) 다 도착. `tasks/` gitignore 아님 확인(`git check-ignore` 빈 출력) → 빈 이유는 아직 새 구조로 돌린 task가 없어서(정상). `db/namu.db` 없음(gitignore된 캐시, 정상) = learnings.yaml↔db 카운트 불일치 = #14 출발점
- **⑤ #14 자동 재생성 실전검증 → 🐛 윈도우 파일잠금 버그 발견(핵심 결과):** `$env:NAMU_HOME=(Get-Location).Path` → `uv run --script namu-plugin\mcp_server.py` 첫 부팅(uv 40패키지 1.88s 설치) → **`_ensure_db()`(mcp_server.py:31) → `rebuild_from_yaml()`(:25) → `db.py:114 cfg.NAMU_DB_PATH.unlink(missing_ok=True)` → `PermissionError [WinError 32] 다른 프로세스가 파일 사용 중`(`db\namu.db`)**
  - **근본 원인:** rebuild가 "기존 db 파일 unlink → init_db 재생성" 방식인데 **열린 db 핸들이 살아있는 채로 unlink.** 리눅스(HP)는 열린 파일 unlink 허용, **윈도우(삼성)는 거부.** → HP 단독 테스트로는 절대 못 잡는 버그 = **#15(2nd PC 검증)의 존재 이유 그 자체**
  - 결과: `namu.db` 36864B 반쪽 생성(못 씀). 삼성서 `del db\namu.db`로 정리 예정
- **다음(=새 작업) — HP에서 `rebuild_from_yaml` 윈도우 안전화:** 후보 A=unlink 전 열린 conn 확실히 close(leak 색출) / **후보 B(추천 검토)=파일삭제 제거, 단일 conn 안에서 `DROP TABLE`/`DELETE FROM` 후 재생성(FTS·트리거 포함)** — 크로스플랫폼+"어디서나 가볍게" 부합, unlink 의존 자체 제거. 단 쓰기계열 conn 경계 규칙 안에서 처리 + HP(리눅스) 회귀 없는지 확인. 수정 후 삼성서 ⑤ 재검증(yaml `^id:` 수 = db `COUNT(*)` 일치) 하면 #14·#15 완료
- **교훈(미기록):** "rebuild의 파일 unlink는 윈도우서 열린 핸들 때문에 깨진다 — 크로스플랫폼 코드는 OS 파일잠금 차이를 가정해야" → 수정 완료 후 `namu_record` 권장(verified_by: human)

### 2026-06-27 (로드맵 15번 종료 — 윈도우 unlink 버그 수정 + 삼성 재검증, 대화창+HP+삼성)
- **진단 심화(대화창, db.py 실코드 검토):** 처음엔 "후보 B(파일삭제 제거)"만 봤는데 실코드 보니 **진짜 범인은 `with sqlite3.connect() as conn`이 commit만 하고 close를 안 하는 파이썬 sqlite3 함정.** 첫 부팅 시 `init_db`가 만든 핸들이 살아있는 채 rebuild의 unlink가 터졌고, **stale 경로의 `cache_is_stale`도 같은 함정** — 두 진입 경로 다 걸림(처음엔 init 경로만 봤던 걸 교정)
- **결정 = 후보 B + 하드닝 동시(사용자가 "나중에 하면 잊는다"며 지금 완전히 잡기로):**
  - `rebuild_from_yaml`: unlink·init_db 제거 → 단일 conn 안에서 `DROP TRIGGER learnings_ai → DROP TABLE learnings_fts → DROP TABLE learnings`(의존성 순서) 후 기존 `_SCHEMA` 재실행 + yaml 재INSERT. **파일 안 지우니 OS 잠금 무관**
  - 하드닝: `init_db`/`record`/`cache_is_stale`/`rebuild` 전부 `from contextlib import closing`으로 감싸 conn 확실히 close — 함정 자체 박멸
  - `_ensure_db`: 신규(db없음)·stale 양쪽 다 `rebuild_from_yaml()`만 호출로 통합(rebuild가 스키마 self-create하니 init_db 선행 제거). init_db 함수 자체는 record가 쓰니 잔류
  - **읽기계열(recall/search/_fts_query) 불변** — conn 주입 규칙 유지
- **Claude Code 구현(HP, diff까지만→사용자 직접 커밋):** db.py 5곳(import/init_db/record/rebuild/cache_is_stale) + mcp_server.py 1곳(_ensure_db). `test_cache_stale.py` 4케이스 전부 통과(리눅스 회귀 없음). diff 검토 2종 — ① rebuild DROP 순서(트리거→fts→main) 정확 ② recall/search/_fts_query diff에 안 뜸(=불변, 정답) → 커밋·푸시
- **삼성 재검증 ⑤(핵심):** `git pull`(fast-forward, db.py 83줄·mcp_server.py 6줄) → `del db\namu.db`(반쪽 정리) → `$env:NAMU_HOME=(Get-Location).Path` → `uv run --script` 재기동 → **WinError 사라짐**, 서버 STDIO 대기 정상(`Ctrl+C`의 긴 KeyboardInterrupt 트레이스백은 입력 끊김 신호일 뿐, 우리 코드 무관). `dir db`로 `namu.db` **53248B 온전 생성**(지난 36864B 반쪽과 대비) → **yaml `^id:`=5 = db COUNT(*)=5 일치** ✅
- **의미:** #14·#15 완전 종료. **"HP 단독으론 절대 못 잡는 버그를 두 번째 PC가 발견 → 수정 → 그 PC가 수정까지 검증"** 한 바퀴 완주 = NAMU 멀티 PC 검증 구조가 자기 가치를 스스로 증명. "독립성은 메모리 레이어에 있다" 토대가 크로스플랫폼서 실제 작동함을 입증
- **곁가지 버그 B — config.py NAMU_HOME 폴백(유령 경로):** 삼성서 MCP 미등록이라 `record`를 파이썬 직접 실행 → `NAMU_HOME` 미설정 → `namu-plugin/memory/learnings.yaml` 유령 위치에 기록됨(사람이 알아채고 올바른 위치로 옮김). 근본원인=`BASE_DIR`이 13번 이후 `namu-plugin/`을 가리킴(repo 루트 아님). **HP서 수정**(`REPO_ROOT=BASE_DIR.parent` 폴백 대상 교체, diff→커밋·푸시→양 PC pull). 이제 `NAMU_HOME` 깜빡해도 repo 루트로 안전하게 떨어짐
- **`.env` 안전망(양 PC):** HP·삼성 `.env`에 `NAMU_HOME` 추가(셸 환경변수 깜빡 대비 멜빵). 삼성은 `NAMU_MACHINE`+`NAMU_HOME` 둘만으로 메모리 코어 충분, HP 옛 API 키는 메모리와 무관 확인
- **교훈 기록(멀티 PC 공유 기억 첫 실사용):** 삼성서 `namu_record`로 1건 기록(`01KW397QE2Q0HSM39GB10TQAJV`, rebuild 윈도우 버그, verified_by=human) → push → HP pull로 공유 확인. 🔶 미기록 1건 = "NAMU_HOME 유령경로 함정"(partial), 다음 세션서 기록 권장
- **다음 세션 시작점:** ① **플러그인 실설치(`/plugin install`) 검증** — 삼성 `.mcp.json`이 `${CLAUDE_PLUGIN_ROOT}` 형식이라 플러그인 설치돼야만 변수 채워짐(`mcp add` 직접등록은 변수 안 풀려 깨짐). 이게 13번 미검증 잔여 + 삼성 MCP 등록을 한 번에 해결. 새 창서 집중(검증 단계 많음) ② 16번 agy(버그 3개 재검증 선행) ③ 미기록 교훈 1건 기록

### 2026-06-27 (로드맵 13번 종료 — 플러그인 실설치 검증, 대화창+삼성)
- **사전 리서치(대화창, 웹검색):** `/plugin install` 공식 절차 + `${CLAUDE_PLUGIN_ROOT}` 동작 재확인. 핵심=이 변수는 **MCP/LSP 서버 설정·훅 커맨드의 JSON에서 치환되고 MCP 자식 프로세스에 env로 export**(공식 docs) → NAMU `.mcp.json`의 `uv run --script ${CLAUDE_PLUGIN_ROOT}/mcp_server.py`가 정확히 지원되는 자리. 알려진 버그 3개 발견·매핑: #9427(플러그인 `.mcp.json` env 확장 실패)→NAMU는 셸 export라 회피 / #17565(cwd 무시)→절대경로라 무관 / #9354(커맨드md서 변수 빈값)→NAMU는 JSON서만 사용 무관. + 로컬 marketplace는 install 전 auto-refresh 안 됨(#9 함정)→`/plugin marketplace update` 선행
- **삼성 실설치(사용자 직접, 화면 공동검토):**
  - `claude` 켠 뒤 `/plugin marketplace add D:\Project\namu-agent\namu-plugin` → **1차 실패** `Invalid schema: name/owner undefined`. marketplace.json에 최상단 `name`/`owner` 누락(13번 때 `uv run`만 검증해 숨어있던 버그). 수정 2줄(`name:namu-marketplace`+`owner:{name:onmiso}`) → **add 성공**
  - `/plugin marketplace update`(✓1) → `/plugin install namu@namu-marketplace`(local 스코프, UI Discover서 선택) → `✓Installed namu` → `/reload-plugins`
  - `/mcp` → **`plugin:namu:namu-memory ✓connected · 3 tools`** = 핵심 관문 통과(직접등록 아닌 진짜 플러그인, 변수 자동채움 증거)
- **도구 라이브 검증:**
  - recall(권한 1.Yes) → 과거 교훈 5건 최신순, 1번이 어제 삼성 기록(`01KW397...`) = **캐시밖 NAMU_HOME yaml을 정독**(코드/데이터 분리 실작동)
  - record(미기록 교훈 1건 실기록으로 갈음) → ULID `01KW3T9TDSZGMMR7BZ511ZR9BT` 반환, learnings.yaml append+SQLite 반영. **PowerShell 직접 확인**: `Get-Content ...\memory\learnings.yaml`에 그 ULID·`machine:samsung`·경로함정 교훈 존재 ✅ + `Test-Path ...\namu-plugin\memory\learnings.yaml`=**False**(유령파일 없음) → **B 버그 최종 박멸 확인**
- **커밋·푸시(사용자 직접):** marketplace.json 수정 + learnings.yaml 교훈 1건 → 커밋 `62b246b`(2 files, 37+), push `58ecd50..62b246b`. (commit 전 add 누락으로 "no changes" 한 번 떴으나 add 후 정상 — 순서 엉킴일 뿐 무해)
- **HP pull로 동기화 완주:** HP `git pull` 후 새 세션 recall에 그 경로함정 교훈(samsung) 보임 = **삼성→push→HP pull→recall 한 바퀴.** 단 HP recall이 "MCP 미로드, yaml 직접 read"로 동작 = **HP는 플러그인 미설치 상태**(별건으로 차기 결정)
- **의미:** #13 완전 종료. 웹검색으로 우려한 함정 3개 다 우회됨(셸 export+절대경로 설계가 결과적 안전판). "실설치 검증"이 marketplace 스키마 버그를 잡아 제값 증명. NAMU 핵심(코드=캐시 복사 / 데이터=NAMU_HOME git동기화)이 크로스플랫폼 플러그인 형태로 실동작
- **다음 세션 시작점:** ① **16번 agy 글루**(착수 전 agy 버그 3개 재검증 선행 — MCP env var/non-TTY stdout #76/훅 경로) + `namu-plugin/agents/` 이동 ② 별건: HP도 플러그인 방식 통일 검토

### 2026-06-27 (16번 착수 — agy 자동 주입 설계 확정, 대화창+HP)
> **이번 세션 = 설계만. 코드 변경/커밋 없음**(스모크 테스트용 임시 파일 제외). 다음 세션은 이 설계로 구현 지시서 작성부터.
- **1단계 회고(완료분):** agy MCP 호스트 연결은 이미 통과 상태(워크스페이스 `.agents/mcp_config.json`, `namu-memory ✓connected 3 tools`). 이번 세션은 **2단계(자동 주입)** 착수
- **전제 검증 → 붕괴 → 재설계 (이번 세션의 핵심 흐름):**
  - 원래 구상 = "agy 새 세션 시작 시 과거 교훈 자동 주입"(11번 Claude Code SessionStart 훅 방식 이식). **착수 전 전제부터 검증**(웹검색): agy 훅 설정 경로(`.agents/hooks.json` or `~/.gemini/config/hooks.json`), 스키마(네임스페이스 래핑), SessionStart 존재 여부
  - **스모크 테스트(더미 훅) 설계 → 사용자 HP 실행 → `/hooks` 화면 캡처:** 지원 훅 **5종뿐(PreToolUse/PostToolUse/PreInvocation/PostInvocation/Stop), SessionStart 없음.** 원래 구상이 agy선 불가 판명 — **5분짜리 검증이 헛삽질을 막음**
- **재설계 (사용자와 단계적 합의):**
  - "자동 주입이 꼭 필요한가" 근본 재검토 → NAMU 본 설계("AI가 프로젝트서 켜질 때 과거 상태+교훈으로 자가학습된 모습으로 시작")가 맞음을 재확인. **(나) AI가 알고 시작**이 목표(사람 눈에만 뜨는 (가) 아님)
  - **agy식 정답 = PreInvocation 훅 + ephemeralMessage** (공식 docs + **ContextOS 오픈소스**가 정확히 이 패턴: "Antigravity는 UserPromptSubmit 안 쓰고 PreInvocation으로 ephemeralMessage 주입"). agy엔 현관 못(SessionStart) 없지만 거실 길목 못(PreInvocation)은 있음
  - **PreInvocation 매호출 비용 우려 → 체크/주입 분리로 해소**: 매번 도는 건 플래그 깃털 체크(5~10ms), 실 주입은 `conversationId`로 세션 1회만. LLM 호출 대비 1% 미만 → 자동 채택
  - **주입 내용 = 상태(tasks/) 메인 + 관련 교훈 곁들이기**: 활성 task 제목·태그를 검색어 삼아 learnings 조회(폴백 옵션 A). 상태가 무게중심
  - **저장(record) = Claude Code 11번 정책 그대로 대칭**(프로젝트 문서로 확인): recall=훅 자동 / record=AI 수동 호출, 자동저장 보류(완료시점 모호→쓰레기+reason 부실, 과거 #5). **차이는 주입 훅만(SessionStart→PreInvocation), 저장 정책 동일.** PostInvocation 자동저장 기각
  - **AGENTS.md 안 건드림**(사용자 거부 — 공유 파일 침범): 저장 규칙은 PreInvocation 주입 쪽지에 "새 교훈 생기면 namu_record로" 한 줄 동봉
- **미확정(다음 세션):** ephemeralMessage 출력 JSON 형식 / 세션 1회 플래그 저장 위치 / `.agents/hooks.json` 정확한 포맷(네임스페이스 vs 직접) / 스모크 테스트 잔재 정리
- **다음 세션 시작점:** ephemeralMessage 형식 확정(ContextOS 소스 까보기 or 로컬 찍기) → 세션 1회 플래그 설계 → 구현 지시서 작성해 Claude Code(HP)에 인계 → 라이브 검증

### 2026-06-27 (16번 2단계 설계 완전 확정 — ephemeralMessage 형식·hooks.json 포맷·플래그 키 확정, 대화창+HP)
> **이번 세션도 설계만. 코드 변경/커밋 없음**(스모크 훅 임시파일만). v7 미확정 3개를 공식 docs + HP 스모크 실측으로 전부 닫음. 다음 세션 = 구현 지시서 작성부터.
- **① ephemeralMessage 출력 형식 확정 (공식 docs):** Antigravity 공식 hooks 문서 정독(JS 렌더라 한국어 번역 wikidocs 360097로 원문 JSON 확보). PreInvocation stdout = `{"injectSteps":[{...}]}`, 각 원소는 **`toolCall`/`userMessage`/`ephemeralMessage` 중 하나만**. NAMU는 시스템 컨텍스트라 **ephemeralMessage(문자열 하나)** 채택 → 상태+교훈을 **한 덩어리 마크다운으로 조립**(userMessage는 사용자 위장이라 부적합). 안 주입할 땐 `{}`. stdin엔 `invocationNum`/`initialNumSteps`+공통필드(conversationId 등) 들어옴 확인
- **② hooks.json 포맷 = 네임스페이스 래핑 확정 (v7 의문 종결):** 공식 예시가 `{"<훅이름>":{"PreInvocation":[{"type":"command","command":"..."}]}}`. PreInvocation은 **matcher 무시**(PreToolUse/PostToolUse만 정규식 매처). 위치 `.agents/hooks.json`
- **③ 세션 1회 플래그 키 = conversationId 확정 (HP 스모크 실측):**
  - 스모크 훅(`smoke_inject.py`, 절대경로+`echo fired`/`2>>py_err` 3중 진단) HP 라이브 → 로그 회수: 한 세션 prompt 2회(`initialNumSteps` 1→6 = 다른 turn 입증)인데 **`invocationNum`은 둘 다 0** = **매 turn 0 리셋** → "세션 첫 호출" 판정 불가, **invocationNum 폐기**(v7의 이중장치 아이디어 기각)
  - `initialNumSteps`도 값 예측불가+세션경계 모름이라 부적합. **`conversationId`만** 세션단위 고정+세션바뀌면 변경 → 적격
  - **핵심 멘탈모델(사용자와 합의):** 판정은 *값 비교*가 아니라 **플래그 파일 존재 여부**. conversationId는 파일 *이름표*일 뿐 — 있으면 패스, 없으면 주입+`flag.touch()`. "같은 값이라 못 쓴다"가 아니라 "같아야 같은 파일을 알아본다"
  - 저장 위치=`tempfile.gettempdir()/f"namu_injected_{cid}"` → **WSL=/tmp·Win=%TEMP% 자동 분기**(양 PC 한 줄 커버)
- **부수교훈 (스모크가 잡아냄):** 첫 시도서 로그 안 생김 → 원인=**상대경로**. agy 훅 `command`는 실행 cwd를 workspace 루트로 **보장 안 함** → 상대경로면 python이 파일 못 찾고 **조용히 죽음**(stderr도 안 봐서 무음). **절대경로 필수**(`realpath`로 박기). 진단법=`echo fired`(발화 확인)+`2>>py_err`(죽으면 이유)+stdout 로그 3분리
- **남은 일(다음 세션):** 구현 지시서 작성 → HP Claude Code(Sonnet) 인계. `hooks/session_inject.py`(가칭) = db.recall 재사용 + 활성 task 상태 읽기 + ephemeralMessage 한 덩어리 조립 + conversationId 플래그(temp) + 어떤 예외든 exit 0. 그 뒤 `.agents/hooks.json` 네임스페이스 래핑 등록 → 라이브 검증 → 스모크 잔재 정리
- **사용량 관리:** 세션 후반 사용량 85% 도달 → 구현 지시서는 다음 창 첫 작업으로 미루고 이 창은 마무리 루틴만 실행(설계 굳었으니 인계로 충분)


### 2026-06-27 (16번 — 양쪽 1:1 자동주입 구현 + 라이브 검증 디버깅, 대화창+HP)
> **설계가 세션 중 진화**(agy만 → 양쪽 1:1) → HP Claude Code 구현(4파일·테스트 6/6) → 라이브 검증 실패 → **끝까지 파고들어 근본원인 규명**(HP 플러그인 미설치). 코드 미커밋(검증 후), 이 창은 plan.md만 단독 커밋. 사용량 80%로 마무리.
- **설계 진화 — 양쪽 1:1:** 사용자 통찰 "agy 메시지가 클로드코드에서도 똑같이 나오나?" → 점검하니 클로드코드는 **교훈만** 띄우고 작업상태 누락(06-25 만들 때 상태층 없어 빠진 타이밍 사고). → 양쪽을 같은 내용으로 통일. "독립성=메모리 레이어"를 사용자 체감(같은 경험)까지 끌어올림
- **구조 = 공유 헬퍼 + 호스트별 래퍼:** "무슨 내용"은 코어 `session_context.py`(뇌) 단일화 → 두 훅(`session_recall.py`=SessionStart·additionalContext / `session_inject.py`=PreInvocation·ephemeralMessage)은 같은 헬퍼 호출 후 자기 봉투에 담기만(=포장지). 내용 어긋남 원천 차단. 유일 비대칭=SessionStart는 천성 1회(플래그 불필요)/PreInvocation은 매 turn이라 conversationId 플래그로 1회 만듦
- **활성 task = 옵션 A(mtime):** 현재 머신 `context.<machine>.md` mtime 최신·`(완료)` 아닌 것. 머신별 context를 봐 타 PC pull 함정 회피
- **분리 원칙(사용자 의심에서):** "1회 자동조회 로직이 수동 요청도 막나?" → 플래그는 **훅에만**, MCP 도구(`namu_recall`)는 무관·항상 동작. 지시서에 명문화
- **`session_inject.py` 위치 검증:** 사용자 "`.agents`에 둔 히스토리 있을 텐데 옮겨도 되나?" → repo 기록 조사: `.agents`는 agy **설정집**(hooks.json·mcp_config)일 뿐, 스크립트는 hooks.json command가 **절대경로**로 가리켜 위치 자유(절대경로 필수 교훈이 곧 반증). → `namu-plugin/hooks/`로 이동(=`session_recall.py` `parent.parent` 트릭 공유, git 자연 추적). 좋은 의심이 더 깔끔한 구조로 귀결
- **구현(HP Claude Code Sonnet):** 4파일 생성·수정, 단위테스트 6/6 통과. gitignore=코드 추적/`hooks.json` 로컬전용(Claude Code가 `.agents/` 전체 gitignore라 hooks.json까지 커밋하려 함 → "등록은 PC별이라 커밋 금지"로 교정)
- **🔴 라이브 검증 디버깅 체인(사용자 주도):** 새 세션 자동주입 안 뜸 → "자동 전달 컨텍스트 없음" → ① 플러그인 번들 hooks.json 정상 ↔ `settings.local.json`에 옛 경로 중복 훅 발견 ② `namu-memory` MCP `Failed to connect`(첫 화면 "2 servers need authentication"이 무해한 게 아니었음 — 내가 추측으로 넘긴 걸 사용자가 파고들어 잡음) ③ 최종: **HP `No plugins installed`** = 삼성은 #13서 설치, HP는 미설치. 옛 `claude mcp list` 등록은 `~/.claude.json` local 직접등록 잔재. **= 새 코드 무죄, #13 개편 잔재가 늦게 드러남**
- **토대 복구 착수:** `claude mcp remove namu-memory -s local`로 옛 등록 제거 완료. 설치명령은 삼성 marketplace 흐름과 대조 필요해 실행 전 중단
- **교훈:** ① 자동주입 같은 "안 보이는 동작"은 "스크립트 새로 돌리지 말고 받은 것 보여줘"로 검증해야 진짜 자동성 확인 ② MCP 경고는 추측 말고 `/mcp`로 실확인(내 추측 오류를 사용자 끈기가 교정) ③ 멀티 PC는 설치 방식까지 일치시켜야(HP가 삼성처럼 플러그인 설치 안 된 비대칭이 화근)
- **커밋 정책:** 검증 안 된 코드는 통과 후 커밋(작업폴더 대기), 진행기록 plan.md는 지금 단독 커밋(`git add plan.md`만)
- **다음 창:** 토대 복구(플러그인 설치)→서버 연결→훅 정상화→라이브 검증(양쪽+1:1 대조)→커밋

### 2026-06-28 (16번 — 토대 복구 완료 + 자동주입 작동 확인, 진범=NAMU_MACHINE unknown, 대화창+HP)
> **토대 복구는 끝.** HP 플러그인 설치+옛 훅 청소 완료, 자동주입도 작동. 그러나 📌진행중 task가 안 뜨고 교훈만 → 디버깅 끝에 진범(`NAMU_MACHINE=unknown`)을 한 줄로 규명. 컨텍스트 무거워져 env 해결은 새 창에서. (Opus 헛발질 누적 → 사용자 제안으로 창 교체)
- **토대 복구 (검증된 삼성 흐름 그대로):** `/plugin marketplace add ~/project/namu-agent/namu-plugin` → `/plugin marketplace update`(이때 install까지 동시) → `/reload-plugins`. `/mcp`에 **`plugin:namu:namu-memory ✓connected·3 tools`** + `1 hook·1 plugin MCP server`. 접두사 `plugin:namu:`=진짜 플러그인 기동. (Claude Code **2.1.195**, 양 PC 동일 — 기존 2.1.186은 오기)
- **옛 훅 청소:** `settings.local.json`의 옛 죽은 SessionStart 훅(`.venv/bin/python .../session_recall.py`) 제거. **permissions.allow 17개 보존**(.bak 백업과 대조 17=17, 기존 "22개" 기록은 오기), enabledPlugins 보존
- **검증용 task:** `tasks/namu-16-live-verify/`(task.md/context.hp.md/log.md). context.hp.md 첫 생성 시 heredoc 인코딩 깨짐(`## ▶ 다음`이 깨진 바이트로) → `printf`+`LC_ALL=C.UTF-8` 강제 재작성 → `grep "^## ▶ 다음"` 매칭 성공. (교훈: `cat -A`는 비ASCII를 무조건 `M-..`로 표시해 정상/깨짐 판정에 부적합 → `grep`으로 판정)
- **자동주입 작동 확인:** 새 세션서 "🌳 NAMU — 세션 컨텍스트 자동 로딩" 헤더+교훈 5건 뜸 = 새 헬퍼 `build_context_markdown` 실행. 캐시본(`~/.claude/plugins/cache/namu-marketplace/namu/0.1.0/`) vs 작업본 `diff` 동일(session_recall·session_context 둘 다) → 재설치 불필요
- **🔴 진범 규명 (디버깅 체인):** 자동주입은 뜨는데 📌진행중만 누락 → 헬퍼 직접 실행 진단 → 첫 줄 `NAMU_MACHINE = unknown`. `find_active_task`는 `context.<machine>.md` 글로빙이라 machine이 `hp`여야 `context.hp.md`를 잡는데 `unknown`이라 `context.unknown.md`를 찾음→없음→None→교훈만. 원인=`config.py` `BASE_DIR=Path(__file__).parent`(플러그인 모드선 캐시폴더)·`load_dotenv(BASE_DIR/".env")` → repo 루트 `.env`의 `NAMU_MACHINE=hp` 안 읽힘+셸 export 없음. **config.py 12행 주석이 이미 정답 시사**("플러그인 모드선 NAMU_HOME을 셸 env로 지정해야 함"=NAMU_MACHINE 동일)
- **❓ 미확정(새 창 첫 수):** 교훈은 잘 떴음(learnings.yaml 읽음=NAMU_HOME은 어떻게든 풀림)인데 NAMU_MACHINE만 unknown인 모순 → 실제 자동주입 셸의 env를 직접 찍어 확정. 유력 해법=HP rc에 `export NAMU_HOME`+`export NAMU_MACHINE=hp`(삼성 성공 이유 추정)
- **교훈:** ① 즉석 진단 스크립트는 실제 진입점(`mcp_server.py`)의 PEP 723 의존성 헤더를 그대로 베껴야 의존성 누락 안 남(`typing_extensions` 등 transitive 새는 것 반복) ② `__file__`은 `uv run --script -`(파이프) 환경서 미정의 → 즉석 스크립트 작성 시 주의 ③ 설계가 "셸 env 전제"면 코드 수정보다 환경설정이 정석
- **정정 반영:** Claude Code 버전 2.1.186→2.1.195(양 PC), permissions.allow 22개→17개
- **다음 창:** env 실태 확정→`export NAMU_MACHINE/NAMU_HOME`→재검증→클로드코드 통과→agy 검증→양쪽 1:1 대조→4파일 커밋+잔재 청소

### 2026-06-28 (16번 — 셸 env 진단 + export 검증 실패 + 전제 정정, 대화창2+HP)
> v10 인계받아 디버깅 이어감. 진범을 좁히던 중 **이전 추정(셸 export로 끝)이 틀렸음**을 확인하고, plan.md 재검토로 **"삼성은 됐다"는 전제 자체가 오해**였음을 발견. 다음 수를 "추측"에서 "관측"으로 전환 결정.
- **① 셸 env 실태 확정:** `env | grep NAMU`(없음) + `grep NAMU ~/.bashrc ~/.profile ~/.bash_profile`(없음). repo 루트 `.env`엔 `NAMU_MACHINE=hp`·`NAMU_HOME=/home/onmiso/project/namu-agent` 둘 다 정상.
- **② config.py 직독 → 진짜 버그 확정:** `BASE_DIR=Path(__file__).parent`(=`namu-plugin/`), `load_dotenv(BASE_DIR/".env")`가 **`namu-plugin/.env`(없는 파일)를 봐 repo 루트 `.env`를 영영 못 읽음.** `NAMU_HOME=os.environ.get("NAMU_HOME", REPO_ROOT)`는 폴백 `REPO_ROOT`가 우연히 정답이라 생존, `NAMU_MACHINE=os.getenv("NAMU_MACHINE","unknown")`은 폴백이 `"unknown"`이라 사망. **`.env`에 hp로 적어놨는데 코드가 그 `.env`를 안 읽는 게 본질.**
- **③ 캐시 확인:** `~/.claude/plugins/cache/namu-marketplace/namu/0.1.0/`에 config.py는 있으나 `learnings.yaml`·`context.*.md`·새 task(`namu-16-live-verify`) **모두 없음**(빈 결과). 그런데 교훈은 자동주입에 떴음 → **자동주입이 캐시가 아니라 작업폴더(repo) 데이터를 읽는다는 강한 단서.**
- **④ ⚠️ export 1차 검증 실패:** `export NAMU_MACHINE=hp`+`NAMU_HOME` 후 **같은 셸**에서 새 세션 → 여전히 📌task 안 뜸. **"machine만 고치면 끝" 가설(v10·이전 헤더) 기각.** (셸 export가 자동주입 훅 실행 시점에 상속 안 되는지 등 추가 변수 의심됨, 미확정)
- **⑤ 🔑 전제 정정(가장 중요):** plan.md 기록 재검토 결과, **삼성에서 라이브 성공한 건 #13/#15(MCP 도구 `recall`/`record` 직접호출)뿐.** #16(자동주입 헤더에 📌task 띄우기)은 **삼성·HP 어느 PC서도 라이브 통과 0회**(HP는 구현·미커밋, 삼성은 미실행). "삼성은 됐는데 HP만"은 틀린 프레임 — **"되던 게 안 됨"이 아니라 "처음부터 마지막 미검증 한 조각."** 이 오해가 v10 이래 엉뚱한 export 추측을 유발.
- **❓ 미해결 모순:** 교훈은 자동으로 뜨는데(작업폴더 데이터 읽힘) task만 안 뜸. 둘 다 같은 repo 데이터인데 왜 하나만? **근본원인 아직 미확정.**
- **⬜ 다음(차기 창) = 추측 중단·관측으로 전환:** 자동주입 훅(`session_recall.py`/`session_context.py`)에 **임시 진단 한 줄** 삽입 → 주입 메시지 끝에 ① 실제 `machine` 값 ② 코드 실행 위치(캐시/작업폴더) ③ task 탐색 경로를 echo → **새 세션 1회**로 모순 한 번에 관측 → 결과로 fix 방향(`load_dotenv` 경로 수정 vs 훅 설정 env 주입 vs 기타) 확정. **진단은 수정·커밋 없이 임시 한 줄만**, 확정 후 정식 fix→라이브 통과→4파일 커밋.

### 2026-06-28 (16번 — 관측으로 모순 규명 + 진짜 근본원인=2.1.0 사양 발견, 대화창3+HP)
> v11 인계받아 "추측 중단·관측" 원칙대로 DEBUG 블록을 박아 실제 런타임 값을 관측. 미해결 모순을 풀고, **화면 미표시의 진짜 원인이 NAMU 코드가 아니라 클로드 코드 2.1.0 사양 변경**임을 검색으로 확정. 다만 목표(화면 가시성)는 미달이라 #16은 계속 진행.
- **① DEBUG 블록 구현·관측(HP Claude Code):** `session_context.py`에 `_build_debug_block(machine)` 추가(machine·home·`__file__`·glob 패턴·후보 리스트·채택/탈락 사유 6종 출력), `build_context_markdown` 끝에 호출 1줄. `--- DEBUG START/END ---` 주석으로 감쌈. 기존 로직 불변. 미커밋.
- **② 캐시 함정 규명 = 뺑뺑이의 진범:** 작업폴더 코드를 고쳐도 클로드 코드는 **캐시 사본**(`~/.claude/plugins/cache/...`)을 실행 → `grep DEBUG ~/.claude/plugins/cache`(없음)로 확정. **NAMU만의 2단계 갱신 필요**(`marketplace update`=작업폴더→캐시 복사 + `reload-plugins`=재로딩). 그동안 ②번 누락으로 헛검증 반복. ⚠️ `marketplace update`가 "already at latest 0.1.0"이라 떠도 실제 파일은 갱신됨(`head`로 신본 확인) — 버전 숫자 안 바뀌어도 복사는 됨.
- **③ 셸 env 고정:** `~/.bashrc`에 `export NAMU_MACHINE=hp`+`export NAMU_HOME` → `env\|grep NAMU` 둘 다 확인. (config.py의 `.env` 경로 버그를 셸 export로 우회 — 캐시 모드 정석)
- **④ `uv run` 직접 실행 = 모순 해소:** 훅 실행 방식 그대로 `uv run --script <캐시>/hooks/session_recall.py` → **DEBUG 정상 출력: `NAMU_MACHINE='hp'`·glob `tasks/*/context.hp.md`·후보 `namu-16-live-verify` 미완료 채택.** machine=hp 잡히고 task도 정상 채택. (⚠️ 맨 `python3` 직접 실행은 `ModuleNotFoundError: dotenv`로 실패 — 훅은 `uv run`이 PEP723으로 의존성 자급하므로 진단도 반드시 `uv run`으로 해야 함. `python3` 진단은 헛다리.)
- **⑤ 🔑 진짜 근본원인 확정(검색):** 코드·데이터·등록(`/hooks`에 SessionStart 등록 확인)·실행·전달 다 정상인데 화면만 빔 → `claude --debug` 로그가 `Hook SessionStart ... provided additionalContext (1426 chars)`+`success` 찍음. **[공식 docs + GitHub #9591/#32221] Claude Code 2.1.0(ultrathink)부터 SessionStart 훅 `additionalContext`는 화면 표시 안 하고 모델 컨텍스트로만 조용히 주입.** 신규 세션에 "진행 중 task?" 물으니 클로드가 정확히 답함=모델은 받음(화면만 안 보임). **"화면 미표시=고장"이 틀린 전제였음.**
- **❗ 목표 재확인:** 본 작업의 목표는 "자동주입"이 아니라 **"화면에 📌task가 보이는 것."** 주입은 처음부터 됐으나 가시성은 2.1.0이 구조적으로 막음 → **#16 미완(목표 미달).**
- **⬜ 다음(차기 창):** 화면 가시성 확보 실험 — `additionalContext` 벗고 `print(md)` 직접 stdout → 새 세션 관측. 안 되면 statusLine / UserPromptSubmit 첫턴 노출 / CLAUDE.md 첫응답 요약 지시 중 택1. (상세=16번 항목 마지막 ⬜)

### 2026-06-28 (16번 — 화면 가시성 달성: statusLine 양쪽 + 커밋·푸시, 대화창4+HP)
> v12 인계받아 마지막 한 조각(화면 가시성) 마무리. "load-bearing 전제는 작업 전 직접 검증" 원칙대로 v12 핵심 주장을 검색 재검증 → 참 확정 + 계획됐던 실험이 헛다리임도 같은 검색으로 발견. statusLine으로 갈아타 양쪽 라이브 통과·커밋·푸시까지 완주.
- **① v12 주장 검색 재검증 = 참:** Claude Code 2.1.0부터 SessionStart `additionalContext` 화면 미표시·모델만 주입(공식 docs + #9591/#32221 실재 확인). **추가: 계획됐던 `print(md)` 직접 stdout 실험도 같은 사양으로 화면 억제**(#15174/#32221) → 실험 1번 건너뜀(세션 1회 헛걸음 절약). 보너스: 훅 JSON `systemMessage` = 사용자 화면 노출용(후보 추가).
- **② 화면 경로 = statusLine 채택:** 후보 비교 후 "항상 보이는 📌task"에 최적. settings.json 명령에 JSON stdin→stdout 첫 줄 하단 렌더(≤300ms, 한 줄 강제, ANSI 가능, 빠르게 유지 필요, 트러스트 필요). **핵심 이점=SessionStart 훅과 별개 + 플러그인 캐시 경유 X**(repo 작업본 직접 실행 → 캐시 2단계 갱신 문제 통째 회피).
- **③ agy도 statusLine 보유·원리 동일:** 검색 확정(antigravity.google/docs). `~/.gemini/antigravity-cli/settings.json` `statusLine` 블록, stdin JSON에 `cwd`/`workspace.current_dir`/`model`/`context_window`/`agent_state`/`vcs.branch`. **양쪽 다 `cwd` 줌 → task 찾기 스크립트 1개 공용** = NAMU "1:1 대칭" 코드 레벨 자연 성립. 차이=경로·형식(agy `enabled:true`·camelCase 엄격)·갱신 시점. bash/PowerShell 둘 다 있어 크로스플랫폼 OK.
- **④ 형식·구현 결정:** `[모델] 폴더 | 📌 task-id · 제목 | 컨텍스트%`(모델·폴더·컨텍스트% 묶음). 기존 additionalContext 주입 **유지**(모델엔 유용)·statusLine은 "보이는 층"만 추가. 스크립트=plain python3·stdlib only(uv/dotenv 금지=속도)·repo 위치·settings.json은 절대경로.
- **⑤ 구현(HP Claude Code, diff만):** 파트A `task_resolve.py`(stdlib-only **추출**, find_active_task 위임, 훅도 거기서 import=단일 출처) / 파트B `scripts/namu_statusline.py`(40줄, 빈/깨진 stdin·null pct 엣지 3종 모두 한 줄 보장, `sys.path.insert(0, str(Path(__file__).parent.parent/"namu-plugin"))`로 **cwd 무관 import** — 커밋 전 확인 통과) / 파트C 양쪽 settings.json 등록(`/home/onmiso/...` 절대경로).
- **⑥ 라이브 검증 통과(스크린샷):** Claude Code(Sonnet 4.6·하단 바 28%)·agy(처음 켬, Gemini 3.1 Pro High·하단 바 0%) **양쪽 동일 형식·동일 task `namu-16-live-verify` 표시 = 1:1 대조 완료.** 단독 echo 테스트도 12%로 통과. **✅ #16 핵심 목표(화면 가시성) 달성.**
- **⑦ 커밋·푸시 완료:** 2커밋 분리 — `feat(statusline)`(7경로) + `docs(namu)`(지시서 2개). push 완료. 한글 파일명 git 8진수 이스케이프는 표시상 현상(실제 정상, `core.quotepath false`로 해소). 지시서 동반은 의도(설계 기록=자산).
- **❗ 미반영:** plan.md(이 갱신본) → 사용자 커밋 `docs(plan)`. 잔재 청소(구식 DEBUG 블록·`.agents/hooks/smoke_*`·`agy_*.log`)는 후속.
- **🆕 차기 1순위 도출 = "세션 브리핑" 원안 복원:** statusLine은 "상시 한 줄 표지판"이지만, 사용자 원래 바람은 **세션 시작 1회 task 진행상황+교훈 화면 출력 + 재요청 시 재출력**(상세 펼침). 둘은 경쟁 아닌 공존 층. SessionStart 화면 제약 회피 경로(systemMessage/UserPromptSubmit/첫 응답) 설계가 차기 핵심 과제.

### 2026-06-28 (16번 차기 — "세션 브리핑" 트리거 방식 확정: 슬래시 명령, 대화창5)
> v13 인계받아 차기 1순위("세션 브리핑" 원안 복원) 착수. "load-bearing 전제는 작업 전 검증" 원칙대로 검색·라이브 테스트로 경로를 골랐고, 후보(MCP 프롬프트)를 5분 라이브 테스트로 깔끔히 기각. 컨텍스트가 쌓여 본 구현 지시서 작성은 차기 창으로 인계.
- **① 전제 재검증(검색) = 참:** Claude Code 2.1.0+ SessionStart `additionalContext` 화면 미표시(공식 docs + #9591 + Claude-Mem docs "2.1.0 ultrathink부터 사용자 가시 메시지 미표시"). `systemMessage` 필드가 사용자 화면 노출용이나 **플러그인 디스패치 시 미렌더 버그 다수**(#16289/#50542/#15344) → NAMU 플러그인 모드라 위험. 결론: "세션 시작 자동 화면 출력"을 무리하게 뚫지 말고 방향 전환.
- **② 방향 전환 = 슬래시 명령:** "세션 시작 자동 1회"(불확실·systemMessage 의존) 대신 **사용자가 직접 부르는 슬래시 명령 `/namu`**(확실·화면 출력 보장). statusLine(상시 한 줄)과 공존하는 별개 층. 사용자 추가 의견: 상세는 슬래시에 다 안 넣고 "recall로 상세 보여줘"로 펼침.
- **③ 양쪽 슬래시 메커니즘 확인(검색):** 두 엔진 다 **"마크다운 파일 1개 = 슬래시 명령"** 동일 패러다임. Claude Code=`.claude/commands/*.md`(또는 플러그인 commands `/플러그인__명령`)·skills / agy=`.agents/skills/*.md`(또는 글로벌 `~/.gemini/antigravity-cli/skills/`)·플러그인 skills. MCP 서버는 도구뿐 아니라 **프롬프트도 슬래시로 노출 가능**(Claude Code 문서 확인).
- **④ MCP 프롬프트 방식 라이브 테스트 → 탈락:** NAMU MCP(FastMCP)에 더미 `@mcp.prompt() namu_brief_test` 추가(HP Claude Code, 추측 없이 설치 SDK `base.py:172-174` 직독 확인, 미커밋 진단). **구조 발견:** 두 엔진이 같은 `mcp_server.py`를 다른 위치서 실행 — Claude Code=캐시 사본(`~/.claude/plugins/cache/.../0.1.0/`, gitCommitSha 4개 뒤처져 갱신 필요) / **agy=repo 원본 직접**(`namu-plugin/mcp_server.py`, 갱신 불필요·재시작만). 관측: **Claude Code=O**(`/plugin:namu:namu-memory:namu_brief_test (MCP)` 슬래시 노출) / **agy=X**(`/namu`→No matches). agy `/mcp`: namu-memory ✓연결·**tools 3개 받음**이나 **prompt 슬래시 미노출**. → MCP 프롬프트는 양쪽 1:1 불가로 **기각**.
- **⑤ 🟢 구현 방식 확정:** **각 엔진 네이티브 마크다운 슬래시 + 공용 도구 `namu_recall` 호출.** 양쪽 다 namu_recall 연결·검증됨(agy `/mcp`로 확인). 봉투 둘·내용물 하나=statusLine과 같은 1:1. 내용=진행중 task + 최근 교훈(원안), 상세는 recall 추가 호출.
- **⬜ 다음(차기 창):** 본 구현 지시서 작성 — `commands/namu.md`(Claude Code)·`skills/namu.md`(agy)가 `namu_recall` 불러 "진행중 task + 교훈" 화면 출력하도록. 마크다운 슬래시 문구·양쪽 문법(`!`bash 임베드·도구 호출 지시 등) 차이를 검색 확인 후 작성. **진단용 더미 `namu_brief_test`(@mcp.prompt, 미커밋)는 본 구현 전 제거.** 이후=잔재 청소(구식 DEBUG·smoke), agy 플러그인 승격, 네이티브 서브에이전트 대칭.

### 2026-06-28 (16번 — 세션 브리핑 `/namu` 구현·라이브·커밋 완료, 대화창6+HP)
> v14 인계받아 본 구현 지시서 작성→HP 구현→양쪽 라이브 1:1 통과→커밋·푸시. 설계 단계서 사용자 질문으로 **두 번 교정**(context 버릴 뻔→유지 / 시각 정밀도 토대 먼저).
- **설계 교정 ①(context 유지):** 초안이 `context.<machine>.md`를 "빼거나 보조로" 돌렸으나, 작업이력(하네스 매뉴얼·06-26 결정) 확인 결과 context 존재 이유 2가지(현재 스냅샷 / 머신별=머지충돌 회피)를 놓친 실수. → **context 유지**, 핸드오프 후 현재상태=머신별 `▶ 다음` 라벨 동시 표시, 진행이력=`log.md` 꼬리, 선정=task 중심. `/namu-task` 재진입 읽기를 읽기전용 재사용. `session_context.py`(auto-inject) 불가침.
- **설계 교정 ②(시각 토대 먼저):** `/namu` 선정이 시각 의존인데 log가 날짜뿐 → "나중에 시:분 추가"는 `/namu`를 다시 열게 함. 순서 바로잡아 **PHASE 1(log 타임스탬프 `%Y-%m-%d %H:%M:%S` 초단위) 먼저 → PHASE 2(`/namu`)**. 사용자 요구로 초(`%S`)까지(다른 변수 차단).
- **HP 구현(diff까지만→사용자 직접 커밋):** STEP -1 더미 `namu_brief_test` 제거(HEAD 동일) → PHASE 1 SKILL.md 타임스탬프 초단위(템플릿 "적힌 형식"≠"찍히는 형식" 불일치도 발견·통일) → PHASE 2 두 파일.
- **🔴 agy 스킬 = 폴더 전용(실측):** 플랫 `.agents/skills/namu.md`는 `/namu→No matches`. agy 바이너리서 `{workspace}/.agents/skills/<name>/SKILL.md` 확인 → **`.agents/skills/namu/SKILL.md`로 이동**해야 인식. (Claude Code는 `.claude/commands/namu.md` 플랫 정상.)
- **🟠 `.agents/` gitignore:** 통째 ignore돼 커밋 불가 → **PC별 파일만 콕 집어 차단**(hooks.json·mcp_config.json·hooks/*.log), `.agents/skills/`는 추적 열음. `git check-ignore … SKILL.md` 빈 출력 확인.
- **🟡 `/namu-task` 슬래시 직접 호출 불가**(`Unknown command`) → PHASE 1 검증은 log 줄을 자연어로 직접 append해 우회(초단위·옛 줄 공존 확인).
- **라이브 1:1 통과:** Claude Code `/namu` = agy `/namu` 동일 — 📌 `namu-16-live-verify`·🕘 log 꼬리(옛 `[시작] 2026-06-28` + 새 `[결정] 2026-06-29 07:35:51` 공존)·▶ (hp) context·💡 `namu_recall` 교훈. 양쪽 스크린샷 대조.
- **커밋·푸시 완료:** 1커밋(`SKILL.md`·`.claude/commands/namu.md`·`.agents/skills/namu/SKILL.md`·`.gitignore`·`tasks/namu-16-live-verify/log.md`). `mcp_server.py`=더미 제거 후 HEAD 동일 미커밋. 지시서 v3(실제 결과·정정 박스 추가, v2 폐기 삭제)=`docs(namu)` 별도 푸시 완료.
- **⬜ 다음(차기 창):** ① (선택) `/namu` 선정 로직 stdlib 헬퍼로 굳히기 ② statusLine(머신 중심 `find_active_task`)↔`/namu`(task 중심) 선정 통합 여부 ③ 잔재 청소(구식 DEBUG·smoke·`agy_*.log`) ④ agy 플러그인 승격 ⑤ 네이티브 서브에이전트 대칭. + 삼성 pull 후 `/namu` 멀티PC 동기화 최종 확인.

### 2026-06-29 (16번 후속 — ⑦ learnings 커밋 + ⑥ `/namu` 멀티PC 통과 + statusLine 삼성 미해결, 대화창7+HP+삼성)
> v15 인계받아 가벼운 마무리부터. ⑦·⑥ 닫힘. statusLine 삼성(Windows)은 진단 깊이 들어갔으나 미해결 → 차기 이월. **이번에도 \"검증됐다 가정\"(false frame)이 시간 잡아먹음 — statusLine 1:1은 HP 단독이었는데 \"양쪽 통과\"로 기억됨.**
- **⑦ learnings 4건 커밋·푸시:** 기록 자체는 직전 창서 완료(`namu_record` 4건, ULID 확인). 이번 창=`git add learnings.yaml` 단독 → `chore(learnings)` 커밋·푸시. (4건 = agy 폴더전용 / `.agents/` gitignore PC별만 / 설계요소 제거 전 근거확인 / 멀티PC 초단위 토대)
- **⑥ 삼성 `/namu` 멀티PC 1:1 통과:** 삼성 `git pull` → Claude Code `/namu` = agy `/namu` 양쪽 모두 HP와 **동일 4블록**(📌·🕘·▶·💡). 스크린샷 대조. agy는 `learnings.yaml` Search/Read 후 동일 출력. **`/namu` 멀티PC 닫힘.**
- **🔴 statusLine 삼성(Windows) 미해결 — 진단 체인:**
  - **🔑 전제 정정:** plan.md 재검토 → statusLine 양쪽 1:1 통과는 **HP 단독**(CC+agy 모두 HP, 대화창4). 삼성/Windows는 **첫 시도** = \"삼성도 됐겠지\"는 검증 안 된 가정(false frame 재발). 사용자가 \"계속 확인만 할거냐\"로 제동 → 설계·로그 직접 추적으로 전환.
  - **머신 토대 복구:** ① `NAMU_MACHINE` PowerShell 환경 미설정(PS는 `.bashrc` 안 읽음 — HP는 `.bashrc export`로 생존) → `[Environment]::SetEnvironmentVariable("NAMU_MACHINE","samsung","User")`+`NAMU_HOME` 영구 등록 ② `.env`도 `samsung` 정상.
  - **진짜 막힘 발견:** statusLine은 **머신 중심** `find_active_task("samsung")`=`tasks/*/context.samsung.md` 글로빙인데 **task 폴더엔 `context.hp.md`만 존재**(HP가 만든 것) → 못 찾음. (`/namu`는 task 중심이라 영향 없음 — 두 선정 로직 차이가 실전서 드러남.) → `Copy-Item context.hp.md context.samsung.md` → **스크립트 직접 실행 시 `[Sonnet 4.6] namu-agent | 📌 namu-16-live-verify · … | ?` 정상 출력 확인.**
  - **그러나 CC 하단 바 여전히 미표시:** settings.json 유효(`ConvertFrom-Json` 통과)·`statusLine` 블록 정상·스크립트 단독 정상인데 바에 안 뜸.
  - **검색 확정(공식 docs + GitHub):** ⓐ Windows에서 `command`의 백슬래시 경로는 Claude Code가 Git Bash 경유 시 **조용히 깨짐** → docs가 슬래시 권장 → `D:/Project/...`로 교체 → **여전히 미표시**(백슬래시는 범인 아님). ⓑ **네이티브 Windows statusLine 미실행 회귀 다수 보고**(#27161 \"Session environment not yet supported on Windows\"·#30725·#31670·#23994 — command 자체가 호출 안 됨, 여러 2.1.x). 삼성=2.1.195(고쳐졌는지 미확정). cf) `extraKnownMarketplaces.path` 백슬래시가 잘 먹는 건 셸 안 거치는 **데이터 값**, `command`는 셸 거치는 **실행 문자열**이라 다름(사용자 질문서 갈림).
- **⬜ 차기 1순위 = 탐침 흑백 판정:** 탐침 스크립트(호출 시 `~/.claude/probe_statusline.log`에 시각 append + stdout `PROBE-OK` 출력)를 `~/.claude/probe_statusline.py`로 만들고 settings.json `command`를 잠깐 그걸로 교체 → Claude Code 재시작 → 판정: **바에 PROBE-OK=CC는 statusLine 부름→우리 `namu_statusline.py` 출력 문제**(인코딩/이모지/즉시종료) / **로그만 쌓이고 바 빔=호출은 되나 렌더 실패** / **둘 다 없음=네이티브 Windows 회귀 확정**(설정으로 불가 → 우회=삼성에서 Claude Code를 WSL로 구동, HP와 동일 환경). repo 파일(`scripts/namu_statusline.py`) 불가침 — 탐침은 별도 파일·settings만 임시 교체.
- **이월 잔여(우선순위순):** ① statusLine 삼성 탐침 판정·우회 ② `context.samsung.md` 커밋 여부 판단(머신별 파일이라 보통 각 PC가 자기 것 추적 — `context.hp.md`가 추적되니 대칭상 추적이 맞을 듯, 단 사용자 확인) ③ `/namu` 선정 stdlib 굳히기 ④ statusLine↔`/namu` 선정 통합 ⑤ 잔재 청소 ⑥ agy 플러그인 승격 ⑦ 서브에이전트 대칭.

### 2026-06-29 (16번 완전 종료 — statusLine 삼성(Windows) 해결: cp949 이모지 인코딩, 대화창8+삼성)
> v16 인계받아 statusLine 삼성 미해결 하나만 남은 상태로 시작. 차기안이던 "탐침 흑백판정"을 **건너뛰고** `claude --debug` 로그를 직접 까서 진범을 즉시 확정. 추측·진단 누적이 아니라 **로그 한 줄**이 답이었다. 사용자가 반복적 확인에 정당하게 제동 → 검색·로그 직독으로 단번에 마무리.
- **🔑 진범 = 📌 이모지 cp949 인코딩 사망:** debug 로그(`~/.claude/debug/*.txt`)에 `[DEBUG] StatusLine [python ...namu_statusline.py] stderr: Traceback ... UnicodeEncodeError: 'cp949' codec can't encode character '\U0001f4cc'(📌) ... [WARN] ... completed with status 1`. 즉 **CC는 스크립트를 정상 호출**하는데(2.1.x Windows 회귀 아님 = v16 ⓑ 가설 기각), 한글 윈도우 기본 코드페이지(cp949)가 파이프 stdout으로 📌를 못 내보내 스크립트가 죽어 출력 0 → 바 빔. 터미널 직접 실행 시 정상이던 건 그땐 stdout이 UTF-8이라 통과한 것(= false frame의 정체).
- **🟢 수정 = `python -X utf8`:** settings.json `statusLine.command`를 `python D:/.../namu_statusline.py` → **`python -X utf8 D:/.../namu_statusline.py`**(파이썬 UTF-8 모드 강제, PEP 540). repo 스크립트 무수정. 재시작 → 하단 바 `[Sonnet 4.6] namu-agent | 📌 namu-16-live-verify · #16 양쪽 1:1 자동주입 라이브 검증 | 14%` 표시 확인. **statusLine 삼성(Windows) 닫힘.**
- **🔭 공개 배포 필수 메모(사용자 지시):** 이 cp949/`-X utf8` 건은 일반 사용자(특히 비영어권 윈도우)가 자기 환경 셋업 시 반드시 부딪힐 경우의 수 → **공개 시 README/셋업 가이드에 반드시 명시.** (Claude 메모리에도 별도 기록 완료.)
- **교훈(차기 namu_record 후보):** ① statusLine 화면 미표시 디버깅은 추측 전에 `claude --debug` 로그의 statusLine stderr 한 줄부터 — 거기에 exit code·Traceback이 다 있음 ② 한글/비영어권 윈도우 네이티브 Claude Code는 파이프 stdout이 cp949라 이모지·비ASCII 출력이 `UnicodeEncodeError`로 죽음 → `python -X utf8`(또는 `PYTHONIOENCODING=utf-8`)로 강제 ③ "수동 실행은 되는데 CC가 부르면 죽는다" = stdout이 터미널(UTF-8)이냐 파이프(locale)냐 차이 ④ v16 "네이티브 Windows 회귀" 가설은 우리 케이스에선 오답 — 2.1.195는 statusLine 정상 호출.
- **#16 전체 종료:** statusLine(HP·삼성 양쪽 1:1) ✅ + `/namu`(양쪽 1:1) ✅ + learnings 커밋 ✅. **16번 닫힘.**
- **⬜ 남은 마무리(차기):** ① 이번 교훈 4건 `namu_record` ② `context.samsung.md` 커밋 여부 결정(`context.hp.md` 추적 중이라 대칭상 추적 유력, 사용자 확인) ③ `/namu` 선정 stdlib 굳히기 ④ statusLine↔`/namu` 선정 통합 ⑤ 잔재 청소(DEBUG·smoke·agy_*.log·probe_statusline.*) ⑥ agy 플러그인 승격 ⑦ 네이티브 서브에이전트 대칭.

### 2026-06-29 (16번 진짜 완전 종료 — 삼성 agy statusLine + 마무리 잔재 청소, 대화창9+삼성+HP)
> v17 인계받아 "마무리 잔재만" 남은 줄 알았는데, 라이브 테스트서 삼성 agy statusLine 미표시 발견 → 그것부터 잡고 잔재 마무리. 진단은 v17 반성대로 추측 스택 없이 settings 직독→흑백 분기로 단번에.
- **🟢 삼성 agy statusLine 해결 — 진범=등록 누락(cp949 아님):** 1순위 가설은 "CC만 `-X utf8` 고쳤고 agy는 안 고쳐 cp949 사망"이었으나, agy settings(`~/.gemini/antigravity-cli/settings.json`) 직독하니 **`statusLine` 블록 자체가 없었음**(colorScheme·model·permissions·trustedWorkspaces만). CC와 **별도 설정 파일**이라 한쪽만 고치면 누락. 처방=공식·커뮤니티 검색으로 형식 확정(root에 `statusLine` camelCase 블록, `type`/`command`/`enabled:true`; 소문자 `statusline`은 무시됨) → `command`에 `python -X utf8 D:/.../namu_statusline.py`(같은 공용 스크립트+예방용 utf8) 추가 → 재시작 → 바에 `📌 namu-16-live-verify` 표시. **agy도 같은 namu_statusline.py 공용**(HP서 이미 검증)이라 스크립트 무수정.
- **🟢 바 `�` 깨짐 = 터미널 렌더 문제(인코딩 아님):** 첫 표시 때 📌 자리가 `�`. 흑백 판정(콘솔 렌더 vs 데이터 인코딩) 위해 Windows Terminal 설치→agy 재기동→**📌 또렷이 표시 = 콘솔 렌더 문제 확정.** VS Code 터미널도 정상. 구식 conhost(멀티탭 없는 그 창)가 컬러 이모지를 못 그렸던 것. 데이터는 처음부터 멀쩡.
- **🟢 statusLine 4칸 전부 완성:** HP·삼성 × Claude Code·agy = 네 칸 모두 1:1. 삼성 agy가 마지막 빈칸이었음.
- **🟢 마무리 잔재:**
  - ① **교훈 6건 `namu_record`**(삼성 CC): 대화창8 4건(CC statusLine cp949 계열) + 대화창9 2건(agy 등록 누락 / 바 `�`=터미널). ULID·outcome(success 5·failure 1)·verified_by 전부 human 확인. `namu_recall` 대조 일치.
  - ② **`context.samsung.md`**: `git add` 후 status에 `learnings.yaml`만 뜸 → **이미 추적+동일**(v17 "untracked"는 outdated). 추가 작업 불필요.
  - ⑤ **잔재 청소:** HP smoke 3종(`smoke_inject.py`·`smoke_recall.py`·`smoke_inject.log`) / 삼성 `~/.claude/probe_statusline.py`(379B, 안 쓴 탐침). `*.bak`·`/tmp/namu_*.log`는 이미 없음.
- **🔑 교훈:** (a) 멀티 엔진 statusLine은 **엔진마다 설정 파일이 따로**라 한쪽 고치면 다른 쪽 누락 점검 필수 (b) 바 `�`는 인코딩 전에 **터미널부터** 의심.
- **⬜ 남은 차기(설계 작업·별도 세션):** ③ `/namu` 선정 stdlib 헬퍼로 굳히기 ④ statusLine(머신중심 `find_active_task`)↔`/namu`(task중심) 선정 통합 — **✅ 결정 완료(아래 대화창10): task중심·log타임스탬프로 단일화, 구현은 차기** ⑥ agy 플러그인 승격 ⑦ 네이티브 서브에이전트 대칭. + 공개 README에 `-X utf8`/터미널 안내.

### 2026-06-29 (④→③ 선정 로직 단일화 — 설계 확정·구현 미착수, 대화창10[Claude Code 이관 첫 세션]+HP)
> 설계·결정 작업을 claude.ai 대화창(Opus)에서 Claude Code(Opus 4.8·플랜모드)로 이관한 첫 세션. #16 종료 후 남은 설계 잔재 중 ④(두 선정 로직 통합 여부)→③(`/namu` stdlib 굳히기)을 다룸. **구현은 주간 사용량 한도 임박으로 미착수 — plan 확정까지만, 차기 세션(한도 회복 후) 구현.**
- **④ 결정 = 통합(task중심·log타임스탬프로 단일화):** 두 선정 로직을 직독해 갈림 규명 — statusLine(`task_resolve.find_active_task`)=머신중심·**mtime**·내 머신 context만 `(완료)` 판정 / `/namu`(자연어 스킬)=task중심·**log 줄 타임스탬프**·모든 context `(완료)` 판정. 삼성 `context.samsung.md` 부재 때 갈렸던 실전 버그의 뿌리. NAMU 대원칙(log.md=진실의 원천, mtime은 git pull이 오염)에 비춰 **task중심·log타임스탬프로 통일** 확정. mtime을 버리면 머신중심일 이유(=mtime 오염 회피책)도 같이 소멸.
- **③ = 같은 함수 위임:** `task_resolve.py`에 log 타임스탬프 기반 선정 함수 하나를 두고 **statusLine·`/namu`·session_context(자동주입) 셋 다 재사용**. `/namu` 양쪽 스킬은 선정을 작은 stdlib 스크립트(`scripts/namu_active_task.py` 신설)에 위임. ⚠️ 리스크=슬래시/스킬 본문 Bash 임베드가 양쪽 엔진(Claude Code·agy)에서 되는지 → 구현 시 라이브 검증, 안 되면 그 엔진만 자연어 규칙 1:1 동기화로 폴백.
- **구현 설계 확정·승인:** 상세 단계(log 타임스탬프 파서·완료판정·시그니처에서 machine 인자 제거·`_build_debug_block` 제거·단위테스트+라이브 검증)는 plan 파일 `~/.claude/plans/namu-memoized-twilight.md`에 기록·사용자 승인 완료. 불가침 파일(`task_resolve.py`·`session_context.py`·`scripts/namu_statusline.py`) 수정 근거=본 ④ 결정.
- **⬜ 차기(한도 회복 후 HP):** plan 파일대로 구현(task_resolve 교체 → statusLine/session_context 호출부 → `/namu` 스킬+`namu_active_task.py` → 단위테스트+양쪽 라이브 1:1+삼성 `context.samsung.md` 부재 갈림 회귀확인) → 라이브 통과 후 사용자 커밋. 이후 ⑥·⑦·README.

