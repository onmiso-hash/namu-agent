# NAMU Agent System

벤더 독립 에이전트 시스템. 특정 AI 벤더에 종속되지 않고, 이식 가능한 메모리 코어를 중심으로 작업 기록과 교훈을 누적해 스스로 학습한다. 실행 엔진(Claude Code, agy)은 빌려 쓰고 언제든 교체할 수 있으며, NAMU의 차별점은 **메모리 레이어(MCP)**에 있다.

## 폴더 역할

| 폴더 | 역할 |
|------|------|
| `namu-plugin/` | 현역 코드 — MCP 메모리 서버(`mcp_server.py`), 코어 로직(`db.py`), 설정(`config.py`) |
| `tasks/` | (namu-34로 저장 위치 이전 — namu-26 개정) 작업별 상태 기록의 실제 원본은 개인 풀 `~/.namu/tasks/<basename(프로젝트 폴더)>/`에 있다(이 repo를 포함해 어떤 프로젝트도 예외 없음). `task.md`(불변 목적) / `log.md`(append-only 원본) **2파일** 구조이며(namu-57: `context.<machine>.md`는 신규 생성 중단 — 기존 40개는 읽기 폴백으로만 남김), git 추적은 이 repo가 아니라 `~/.namu`의 개인 전역 동기화에 편승한다 |
| `.claude/` | Claude Code 글루 — 서브에이전트(`agents/`), 로컬 설정(`settings.local.json`). 작업 절차 스킬은 `namu-plugin/skills/namu-task/`로 이전됨(플러그인 동봉) |

이 repo에는 `memory/`·`db/` 폴더가 없다(namu-35로 폐지). 교훈(learnings)·검색 캐시(db)는 이 repo가 어디에 있든 상관없이 항상 개인 풀 `~/.namu/`에 쌓인다 — 아래 "메모리 구조" 참고.

## 핵심 파일

- `namu-plugin/mcp_server.py` — FastMCP 메모리 서버. 도구 `namu_record`/`namu_recall`/`namu_search`/`namu_sync_setup` 노출, stdio 전송
- `namu-plugin/db.py` — `~/.namu/memory/learnings.yaml` ↔ SQLite 코어. 읽기 계열(recall/search)은 conn을 인자로 받고, 쓰기 계열(record/init_db/rebuild)은 함수 내부에서 conn을 열고 닫는다 (의도된 분리, 통일 금지)
- `namu-plugin/config.py` — 경로·`NAMU_MACHINE`(기기 식별)·**그릇 레지스트리(`BOWLS`)** 일원화. 데이터 루트는 `NAMU_DATA_ROOT = Path.home() / ".namu"` **고정 상수**다(namu-35: 이 repo에서 실행하든 설치형이든 구분 없음, 환경변수로 바꿀 수 없음 — 상세는 아래 "메모리 구조" 참고). `load_dotenv`도 여기서 호출(`NAMU_MACHINE` 등 잔여 환경변수용). **기록 시각은 반드시 `cfg.now()`로 찍는다**(namu-57 5단계) — `datetime.now()`를 직접 쓰면 시간대가 다른 호스트(웹 컨테이너=UTC)의 기록이 같은 log.md 안에서 비교 불가능해진다. 기준 시간대는 `NAMU_TZ`(기본 `Asia/Seoul`)
- `namu-plugin/memo.py` — memo 그릇(스틱노트, namu-56). **유일한 mutable 저장소**로, 떼면 파일에서 사라진다(tombstone 없음). SQLite 인덱싱 안 함 — 지식베이스(learnings) 오염 0이 이 그릇의 존재 이유다. 붙이기는 `namu_record(bowl='memo', text=...)`, 떼기는 전용 도구 `namu_memo_remove(id)`(기록과 다른 동사라 인자로 태우지 않는다)
- `namu-plugin/hooks/` — 훅 3종. `session_recall.py`(SessionStart, 세션 브리핑 주입) / `closing_guard.py`(Stop, namu-62 ① — "마무리해"인데 이번 세션에 `[다음]` 줄이 없으면 한 번 block) / `prompt_reminder.py`(UserPromptSubmit, namu-62 ② — `profile.yaml`에서 `상시` 태그(`cfg.PROFILE_ALWAYS_TAG`) 붙은 사실만 매 입력에 재주입). **셋 다 기록하지 않는다** — 알리고 막을 뿐이며, 판단과 `namu_record` 호출은 AI 몫이다(아래 "교훈 저장 규칙"의 훅 자동화 금지와 충돌하지 않는 이유). 등록은 `hooks/hooks.json`(Claude Code 전용 — agy는 대응 이벤트 없음)
- `namu-plugin/memory_sync.py` — `~/.namu`의 선택적 git 자동 동기화(record 직후 auto push, 세션 시작 시 auto pull). `namu_sync_setup`으로 명시 활성화해야 동작. `.gitattributes`의 `merge=union` 라인은 하드코딩하지 않고 `config.BOWLS`에서 파생한다(namu-57 — 아래 "그릇 레지스트리" 참고)

## 설계 문서

- `docs/plan.md` — NAMU 전체 계획·결정 이력·로드맵
- `docs/mcp_memory_design.md` — MCP 메모리 서버 상세 설계 (스키마, SQLite 테이블, 도구 명세)
- `docs/memory_schema_v2.md` — **기억 구조 v2 (namu-65, 2026-07-31 완료 · v0.1.43)**. 네 그릇 공통 3층(`summary`/`reason`/`body`), 입력 항목 19개→13개 통일. **현행 구조 설명서**이며 4장의 칸 표는 `config.FIELDS`에서 자동 생성된다(`python scripts/gen_field_docs.py`, 손으로 고치면 `test_field_docs.py` 실패) — 기록 관련 작업 전 반드시 읽을 것

구현 작업 시 위 문서를 먼저 참조할 것.

## 메모리 구조

- **`~/.namu/memory/learnings.yaml`** = 진실의 원천. append-only, `namu_sync_setup`으로 준비한 사용자 개인 원격 repo로 PC 간 공유(선택 기능). 데이터 루트는 `NAMU_DATA_ROOT`(=`Path.home() / ".namu"`) 고정 상수이며, 어떤 프로젝트에서 실행하든(이 개발 repo 포함, 환경변수로도 우회 불가) 항상 이 한 경로다 — namu-35로 "개발 모드/설치 모드" 구분 자체가 폐지됐다.
- **SQLite(`~/.namu/db/namu.db`)** = learnings.yaml를 인덱싱한 로컬 검색 캐시. gitignore 대상(namu_sync_setup이 자동 추가)이며, git pull 후 yaml↔db 항목 수 불일치를 감지하면 서버 부팅 시 자동 재생성된다.
- **tasks(개인 풀 `~/.namu/tasks/<basename(프로젝트 폴더)>/`, namu-34)** = 작업 상태. `log.md`가 유일한 권위 기록이며 "다음 할 일"도 마지막 `[다음]` 태그 줄로 여기 남긴다(namu-57). `context.<machine>.md`는 레거시 읽기 폴백. **작업을 닫는 말은 `[완료]`·`[중단]` 둘뿐이다** — `[종료]`·`[마무리]` 같은 유의어는 저장은 되지만 닫지 못해 조용히 열린 채로 남으므로 `namu_record`가 거절한다(namu-66, 실물 사고: namu-37이 `[종료]`로 적혀 기록상 미종결). **책갈피(namu-70)** — "다음엔 이것부터"는 log가 아니라 `~/.namu/tasks/<방>/.pin.<machine>` 한 장에 적는다(`namu_task_pin`/`namu_task_unpin`). log에 적으면 ①append-only라 뗐다 붙였다를 표현할 수 없고 ②그 task의 `last_ts`가 갱신돼 **순서가 두 경로로 흔들린다** — 이 작업이 없애려던 "기록을 건드려 화면 순서를 바꾸는" 짓과 결과가 같아진다. 파일을 기기마다 가르는 것이 git 충돌 0의 근거이며(각 기기는 제 파일에만 쓴다), 여러 개면 최근에 꽂은 순으로 앞에 선다. 닫힌 task를 가리키는 책갈피는 파일을 지우지 않고도 화면에서 사라진다. 닫을 때 `task.md`에 안 채운 완료조건이 남아 있으면 반환문에 경고가 붙는다(막지는 않는다 — 이관·범위 축소는 정당한 종결 사유). 저장 위치는 학습 기억(`NAMU_DATA_ROOT`)과 별개 산출 기준(프로젝트 폴더명 basename)으로 정해지지만, 물리적으로는 같은 `~/.namu` 계열에 모인다.
- **`~/.namu/memory/memo.yaml`(namu-56)** = 스틱노트. 위 그릇들과 **반대로 append-only가 아니다** — 떼면 그 항목이 사라진다. "영화 8시 20분" 같은 일회성 메모가 갈 곳이 없어 learnings.yaml로 밀려들어오던 문제를 끊기 위한 그릇이라, 검색 인덱스(SQLite)에 넣지 않는다. git은 `merge=union`이 아니라 파일 단위다(union은 삭제를 표현하지 못해 뗀 메모가 병합 때 되살아난다). 세션 브리핑 맨 앞과 `namu_recall` 반환의 `memo` 키로 다시 나타난다.
- **ID** = ULID — 시간순 정렬 + 오프라인 다중 PC git 머지 충돌 0.

### 그릇 레지스트리 (namu-57 3단계)

그릇(learnings / profile / tasks)의 성질은 `config.py`의 `BOWLS`에 한 번만 선언한다 — `Bowl(name, git_patterns, mutable, merge, cached, web_exposed)`. `git_patterns`는 `~/.namu` 기준 상대 패턴이며 경로 상수(`LEARNINGS_YAML_PATH` 등)를 참조하지 않는다(`.gitattributes`가 상대 패턴만 받고, 경로 상수는 테스트가 monkeypatch하는 대상이기 때문).

**새 그릇을 추가할 때는 `BOWLS`에 등록하는 것이 병합 정책 결정을 겸한다** — `memory_sync`가 `merge == "union" and not mutable`인 그릇의 패턴에서 `.gitattributes` union 라인을 파생하므로, 손으로 라인을 따라 붙이는 절차가 없다. 이 구조로 바꾼 계기는 namu-49로 profile 그릇을 만들 때 하드코딩 목록을 아무도 갱신하지 않아 `profile.yaml`이 병합 보호 없이 방치됐던 실제 버그다(오프라인 양쪽 PC에서 사실을 추가하면 CONFLICT — 실측 재현됨). `mutable=True`인 그릇은 union에서 제외된다: 파일 전체가 수시로 바뀌는 그릇에 줄 단위 병합을 걸면 삭제한 항목이 되살아난다.

`BOWLS`의 이름 집합은 `db._VALID_BOWLS`·`mcp_server._VALID_RECORD_BOWLS`와 일치해야 하며, 어긋나면 `test_bowls.py`가 실패한다.

namu-56에서 `memo`가 이 규약의 첫 수요자가 됐다 — `mutable=True, merge="file"`로 등록하는 것만으로 union 라인이 자동으로 생기지 않았고, `memory_sync.py`는 한 줄도 손대지 않았다. 새 그릇은 반드시 `BOWLS` **끝에** 추가한다(중간에 끼우면 기존 설치본의 `.gitattributes`가 통째로 재작성된다).

### 메모리 2원 분류 (#35, #32 개정)

교훈·상태는 성격에 따라 두 갈래로 나뉜다. (#32가 확정했던 "제품지식/개인전역지식/프로젝트상태" 3원
분류 중 제품지식 카테고리는 #35로 폐지됐다 — 상세 사유는 `docs/plan.md` namu-35 항목 참조.)

- **개인전역지식** = `~/.namu/memory/learnings.yaml` 하나. NAMU 자체를 만들며 배운 교훈(이
  repo의 개발 기록)과 NAMU를 도구로 다른 프로젝트 업무를 하며 배운 교훈이 **한 풀에
  통합**된다 — 어느 프로젝트에서 기록했든 실행 위치로 분기하지 않는다. `namu_sync_setup`으로
  준비한 사용자 개인 원격 repo로 공유된다.
- **프로젝트상태** = 개인 풀 `~/.namu/tasks/<basename(프로젝트 폴더)>/`(namu-34, namu-26
  "프로젝트 cwd 귀속" 결정의 개정 — 상세는 `docs/plan.md` namu-26 개정 이력 참조). tasks는
  여전히 성격상 프로젝트 종속 데이터이지만, 공개 repo 노출 차단·PC 간 전자동 공유·데이터
  루트 분열 해소를 위해 **저장 위치만** 개인 풀로 통합했다 — 규칙은 특례 없이 하나
  (`basename(프로젝트 폴더)`)다.

과거 "제품지식/개인전역지식은 성격이 다른 지식이라 병합하지 않는다"(#32)는 결정은 폐기됐다.
공유 대상 원격이 아직 팀·커뮤니티 풀이 아니라 사용자 개인 private repo인 이상 분리 실익이
없고, NAMU 개발 교훈 대부분이 다른 프로젝트 작업에도 일반화 가능해 오히려 병합이 유용하다는
판단이다. 나중에 공개 커뮤니티 메모리 풀이 생기면 task명(`namu-NN`)·태그로 기계적 추출이
가능하도록 설계됐다.

## 에이전트 실행 모델

- **기본 워커** = 메인 AI의 네이티브 서브에이전트 (동일 구독 풀, 추가 비용 0, 보안).
- **외부 엔진**(agy/Gemini 등) = 설치 또는 태스크 시작 시 사용자가 고르는 override.
- 코드 보안이 필요한 작업 → Claude Code `-p` 모드. 가벼운 검토 → Gemini Flash 무료 API 등 사용 가능.
- 워커 설정은 `namu_workers.yaml`(별도 파일)에 둔다 — config.py 상수와 성격이 다른 사용자 선택값.

## 개발 원칙

1. **독립성은 메모리 레이어에 있다** — 인터페이스가 아니다. 메모리는 반드시 MCP로 포터블하게 둔다. 실행 엔진(Claude Code/agy)은 빌려 쓰고 교체 가능한 부품으로 취급한다.
2. **원본이 곧 기억** — `~/.namu/memory/learnings.yaml`이 진실의 원천(append-only). SQLite는 재생성 가능한 검색 캐시일 뿐이다. 작업 상태도 `log.md`가 권위, `context.md`는 뷰.
3. **append-only 로그** — `learnings.yaml`과 작업 `log.md`는 수정·삭제하지 않는다.
4. **승인 게이트** — 워커 에이전트 호출 전, 그리고 검수 fail 시 재실행 전 사용자 확인을 반드시 거친다.
5. **판단 이유 기록** — 결과뿐 아니라 판단 근거(`reason`)까지 남겨야 자동 학습이 가능하다.
6. **버전 드리프트 이중 방지** — 개발 클론 최초 셋업 시 `sh scripts/setup_dev_hooks.sh` 실행 — pre-push 훅으로 버전 드리프트를 push 전에 차단(서버 백스톱은 `.github/workflows/version-guard.yml`). 버전 bump는 반드시 `scripts/namu_bump.py <버전>` 사용.

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
- 멀티스텝 구현 작업은 `/namu-task` 절차(namu-plugin/skills/namu-task/SKILL.md)를 따른다.
- 검수 fail 시 자동 재실행 금지 — 반드시 사용자 게이트(재실행/통과/중단)를 거친다.
- recall/record는 오케스트레이터만 호출한다. 워커는 메모리에 직접 쓰지 않는다.
