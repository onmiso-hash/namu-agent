# NAMU Agent System

벤더 독립 에이전트 시스템. 특정 AI 벤더에 종속되지 않고, 이식 가능한 메모리 코어를 중심으로 작업 기록과 교훈을 누적해 스스로 학습한다. 실행 엔진(Claude Code, agy)은 빌려 쓰고 언제든 교체할 수 있으며, NAMU의 차별점은 **메모리 레이어(MCP)**에 있다.

## 폴더 역할

| 폴더 | 역할 |
|------|------|
| `namu-plugin/` | 현역 코드 — MCP 메모리 서버(`mcp_server.py`), 코어 로직(`db.py`), 설정(`config.py`), CLI 진입점(`main.py`) |
| `memory/` | 원본 학습 기억 (`learnings.yaml`) — append-only, GitHub 동기화 = 진짜 기억 |
| `tasks/` | 작업별 상태 기록 — `task.md`(불변 목적) / `context.<machine>.md`(기기별 스냅샷) / `log.md`(append-only 원본). git 추적(멀티 PC 공유) |
| `db/` | SQLite (`namu.db`) — learnings.yaml를 인덱싱한 검색 캐시(FTS5). gitignore, git pull 후 자동 재생성 |
| `.claude/` | Claude Code 글루 — 서브에이전트(`agents/`), 작업 절차 스킬(`skills/namu-task/`), 로컬 설정(`settings.local.json`) |

## 핵심 파일

- `namu-plugin/mcp_server.py` — FastMCP 메모리 서버. 도구 `namu_record`/`namu_recall`/`namu_search` 노출, stdio 전송
- `namu-plugin/db.py` — learnings.yaml ↔ SQLite 코어. 읽기 계열(recall/search)은 conn을 인자로 받고, 쓰기 계열(record/init_db/rebuild)은 함수 내부에서 conn을 열고 닫는다 (의도된 분리, 통일 금지)
- `namu-plugin/config.py` — 경로·환경변수 일원화. `NAMU_HOME`(데이터 루트)·`NAMU_MACHINE`(기기 식별)·learnings/db/tasks 경로 산출. `load_dotenv`도 여기서 호출
- `memory/learnings.yaml` — append-only 학습 기록 (절대 삭제·수정 금지)

## 설계 문서

- `docs/plan.md` — NAMU 전체 계획·결정 이력·로드맵
- `docs/mcp_memory_design.md` — MCP 메모리 서버 상세 설계 (스키마, SQLite 테이블, 도구 명세)

구현 작업 시 위 문서를 먼저 참조할 것.

## 메모리 구조

- **learnings.yaml** = 진실의 원천. append-only, git으로 PC 간 공유.
- **SQLite(`namu.db`)** = learnings.yaml를 인덱싱한 로컬 검색 캐시. gitignore되며, git pull 후 yaml↔db 항목 수 불일치를 감지하면 서버 부팅 시 자동 재생성된다.
- **tasks/** = 작업 상태. `context.<machine>.md`는 재생성 가능한 뷰, `log.md`가 권위 있는 기록.
- **ID** = ULID — 시간순 정렬 + 오프라인 다중 PC git 머지 충돌 0.

## 에이전트 실행 모델

- **기본 워커** = 메인 AI의 네이티브 서브에이전트 (동일 구독 풀, 추가 비용 0, 보안).
- **외부 엔진**(agy/Gemini 등) = 설치 또는 태스크 시작 시 사용자가 고르는 override.
- 코드 보안이 필요한 작업 → Claude Code `-p` 모드. 가벼운 검토 → Gemini Flash 무료 API 등 사용 가능.
- 워커 설정은 `namu_workers.yaml`(별도 파일)에 둔다 — config.py 상수와 성격이 다른 사용자 선택값.

## 개발 원칙

1. **독립성은 메모리 레이어에 있다** — 인터페이스가 아니다. 메모리는 반드시 MCP로 포터블하게 둔다. 실행 엔진(Claude Code/agy)은 빌려 쓰고 교체 가능한 부품으로 취급한다.
2. **원본이 곧 기억** — `learnings.yaml`가 진실의 원천(append-only). SQLite는 재생성 가능한 검색 캐시일 뿐이다. 작업 상태도 `log.md`가 권위, `context.md`는 뷰.
3. **append-only 로그** — `memory/learnings.yaml`와 작업 `log.md`는 수정·삭제하지 않는다.
4. **승인 게이트** — 워커 에이전트 호출 전, 그리고 검수 fail 시 재실행 전 사용자 확인을 반드시 거친다.
5. **판단 이유 기록** — 결과뿐 아니라 판단 근거(`reason`)까지 남겨야 자동 학습이 가능하다.

## 교훈 저장 규칙

작업 중 일반화할 만한 교훈이 생기면 `namu_record`로 저장한다.

**저장 대상** — 반복될 패턴, 버그의 근본 원인, 설계 결정과 그 이유.
**저장 제외** — 1회성 사실, 맥락 없는 결과. 노이즈는 검색 품질을 떨어뜨린다.
**필수 항목** — `reason`(왜 그런지)을 반드시 포함한다. 결과만 적지 말 것.
**판단 기준** — 애매하면 사용자에게 "이거 기록할까요?" 먼저 물어보고 진행한다.

저장 여부는 AI가 직접 판단해 명시적으로 호출한다 — 훅 자동화 금지.
(이유: 자동 기록은 "작업 완료" 시점이 기계적으로 모호해 쓰레기 데이터가 쌓이고, 의미 있는 reason을 만들 수 없다.)

## 기술 스택

- Python 3.12+
- MCP / FastMCP (`mcp[cli]>=1.28,<2`) — 메모리 서버 인터페이스
- SQLite + FTS5(trigram) — 검색 캐시 (3자 미만 쿼리는 LIKE 폴백)
- uv + PEP 723 inline 메타데이터 — 플러그인 의존성 자급
- `python-ulid` / `PyYAML` / `python-dotenv`
- GitHub — 메모리·상태 동기화

## 작업 오케스트레이션 규칙
- 멀티스텝 구현 작업은 `/namu-task` 절차(.claude/skills/namu-task/SKILL.md)를 따른다.
- 검수 fail 시 자동 재실행 금지 — 반드시 사용자 게이트(재실행/통과/중단)를 거친다.
- recall/record는 오케스트레이터만 호출한다. 워커는 메모리에 직접 쓰지 않는다.
