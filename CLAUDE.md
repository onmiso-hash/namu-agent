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

- `namu-plugin/mcp_server.py` — MCPServer(구 FastMCP) 메모리 서버. 도구 `namu_record`/`namu_recall`/`namu_search`/`namu_sync_setup` 노출, stdio 전송
- `namu-plugin/db.py` — `~/.namu/memory/learnings.yaml` ↔ SQLite 코어. 읽기 계열(recall/search)은 conn을 인자로 받고, 쓰기 계열(record/init_db/rebuild)은 함수 내부에서 conn을 열고 닫는다 (의도된 분리, 통일 금지)
- `namu-plugin/config.py` — 경로·`NAMU_MACHINE`(기기 식별)·**그릇 레지스트리(`BOWLS`)** 일원화. 데이터 루트는 `NAMU_DATA_ROOT = Path.home() / ".namu"` **고정 상수**다(namu-35: 이 repo에서 실행하든 설치형이든 구분 없음, 환경변수로 바꿀 수 없음 — 상세는 아래 "메모리 구조" 참고). `load_dotenv`도 여기서 호출(`NAMU_MACHINE` 등 잔여 환경변수용). **기록 시각은 반드시 `cfg.now()`로 찍는다**(namu-57 5단계) — 이유가 **둘**이고, 하나만 알면 예외를 만들게 된다. ① 여러 기기가 같은 파일에 쓰는 곳(log.md 등)에서 호스트 현지시각을 적으면 시각끼리 비교가 불가능해진다. ② 기기 사이에 섞이지 않는 파일(`db/sync.log`·`db/git_check.log` — git 추적 대상 아님)이라도, **한 기계 안에서 시간대가 갈리면 고장을 들여다볼 수 없다**: 웹 컨테이너의 시계는 UTC라 기억 기록은 한국시간·이 로그는 세계표준시로 9시간 어긋났고, 2026-08-16 무한 재시작 사고를 뒤쫓을 때 실제로 여기 걸렸다(v0.1.70에서 수정). 예외는 statusline 계열뿐이다 — config를 일부러 안 부르는 소비자이고 개인 PC에서만 돈다. `test_record_time.py`가 구문 트리로 `datetime.now()` 직접 호출을 막는다. 기준 시간대는 `NAMU_TZ`(기본 `Asia/Seoul`)
- `namu-plugin/memo.py` — memo 그릇(스틱노트, namu-56). **유일한 mutable 저장소**로, 떼면 파일에서 사라진다(tombstone 없음). 지식베이스(learnings) 오염 0이 이 그릇의 존재 이유다 — 그래서 검색 색인도 **교훈과 합치지 않고 자기 표를 따로 갖는다**(fts5-memo-tasks-index. namu-56이 금지한 것은 "교훈 색인에 섞이는 것"이지 색인을 갖는 것이 아니었다). 붙이기는 `namu_record(bowl='memo', text=...)`, 떼기는 전용 도구 `namu_memo_remove(id)`(기록과 다른 동사라 인자로 태우지 않는다)
- `namu-plugin/naite/` — 나이테. 세션 기록을 읽어 사용자가 AI를 되돌린 자리를 찾고(`naite.py`), 그것으로 주간 점검을 돌리며(`weekly_check.py`), 교훈 부류표(`lesson_classes.json`)와 사고 네 건이 여전히 잡히는지 보는 검사(`check_incidents.py`)를 함께 둔다 — 사고 발화 원문을 코드에 박아 판정 함수에 직접 넣으므로 대화 기록이 사라져도 결과가 같다(2026-09-25 리뷰 D: 대화 기록은 약 28일이면 지워져 네 건 중 세 건이 늘 '놓침'으로 나왔고, 규칙 고장과 원본 소실을 가를 수 없었다. `--기록`은 참고용 대조이며 그날 기록이 없으면 '기록 없음'). 도구 거절은 `user-rejected`만 세고 `automode-blocked`는 따로 보여준다(같은 날 실측: 주 대화 기록의 거절 표지 47건 중 30건이 자동 모드 차단이었다). 대화 기록을 훑을 때 `subagents/` 아래는 뺀다. 한 번의 거절이 거절·요청 중단 두 줄로 남는 짝은 한 건으로 세고, 선택지 창(AskUserQuestion)을 닫은 것은 거절로 세지 않는다. **주간 점검은 저장된 숫자가 아니라 지금 규칙으로 다시 잰 값을 쓰고, 어떤 근거(대화 기록·저장된 원문·저장값)로 쟀는지 출력에 밝힌다** — 판정 규칙을 고쳐도 옛 세션 숫자가 그대로 합산되던 것을 막는다(2026-09-25: 28일 값이 2.37에서 1.80으로 바뀌었다). **판정 규칙을 고쳤으면 반드시 `check_incidents.py`부터 돌린다** — 오탐을 줄이려다 사고를 놓치는 것이 이 도구의 가장 위험한 실패다. 자세한 것은 `namu-plugin/naite/README.md`.
- `namu-plugin/hooks/` — 훅 7종. **기억 계열 3종**과 **검사 계열 3종**, **측정 1종**으로 나뉜다. 검사 계열(2026-09-08 이식)은 원래 개인 설정(`~/.claude/hooks/`)에만 있어 그 기계에서만 돌았고, 그 폴더는 저장소가 아니라 백업도 없었다 — 그래서 플러그인으로 옮겨 설치된 모든 기계와 세 호스트(Claude Code·agy·Grok)에서 함께 돌게 했다. `repo_sync_check.py`(SessionStart와 PreToolUse — 코드 저장소가 원격보다 뒤처졌는지 보고, 파일을 고치기 직전에는 사용자에게 물어본다. 2026-09-08 실사고: 원격에 이미 있던 기능을 다시 만들었다. NotebookEdit의 `notebook_path`도 본다) / `version_drift_check.py`(SessionStart — 돌고 있는 컨테이너 판·저장소 원격 최신 태그·빌려 쓰는 본체 핀을 대조한다. 캐시는 일감 폴더별로 가른다. **감시 대상은 코드가 아니라 `~/.namu/config/version_targets.json`에 적고**, 그 파일이 없는 기계에서는 아무 말도 하지 않는다) / `weekly_review_check.py`(SessionStart — 마지막 `나무점검` 교훈에서 7일이 지났으면 알린다. 측정 도구는 **플러그인 안의 `naite/weekly_check.py`**다. 2026-09-09 이전에는 별도 저장소였고 기계마다 자리가 달라 세 자리를 뒤졌는데, 그러면 도구가 없는 기계에서는 점검이 아예 일어나지 않고 낡은 판이 있는 기계에서는 옛 판정 규칙으로 잰 숫자가 그대로 기억에 남았다 — 그래서 들여왔다). 기억 계열은 다음 셋이다. `session_recall.py`(SessionStart, 세션 브리핑 주입) / `closing_guard.py`(Stop, namu-62 ① — "마무리해"인데 이번 세션에 `[다음]` 줄이 없으면 한 번 block. namu-self-improvement-loop에서 **세션 측정도 여기서 한다** — 아래 측정 계열 참고. '종료'는 세션을 가리킬 때만 마무리로 보고 물음표로 끝나는 말은 마무리로 보지 않는다("테스트 끝내고 커밋해줘"가 막히던 오탐, 2026-09-25). 이어 연 긴 세션은 앞선 마무리 뒤 사람이 다시 말을 건 때 이후의 `[다음]`만 인정한다. Stop 훅 timeout은 90초 — 측정 올리기 최악 45초에 uv 준비 시간을 더했다) / `prompt_reminder.py`(UserPromptSubmit, namu-62 ② — `profile.yaml`에서 `상시` 태그(`cfg.PROFILE_ALWAYS_TAG`) 붙은 사실만 매 입력에 재주입). **이 가운데 다섯은 기록하지 않는다** — 알리고 막을 뿐이며, 판단과 `namu_record` 호출은 AI 몫이다(아래 "교훈 저장 규칙"의 훅 자동화 금지와 충돌하지 않는 이유). 측정 계열은 둘이고 **같은 함수(`session_end_naite.일하기`)를 부른다** — `session_end_naite.py`(SessionEnd)와 `closing_guard.py`가 마무리 선언을 알아본 자리다. 마무리 쪽을 더한 근거는 2026-09-12 실측이다: `/exit`로 끝낸 세션 2건은 둘 다 커밋만 남고 원격 올리기가 끊겼고(프로그램이 떼어낸 일꾼을 기다리지 않고 끝난다), 프로그램이 스스로 끝난 1건만 올리기까지 마쳤다. 마무리 시점은 세션이 살아 있어 끊기지 않는다. 두 자리에서 겹쳐 쌓이지 않는 것은 `sessions.already_recorded`(발화 수로 판정)가 막아 준다. "훅 자동화 금지"의 근거는 교훈에 관한 것이라(완료 시점이 기계적으로 모호하고 의미 있는 `reason`을 기계가 만들 수 없다) 이 훅에는 걸리지 않는다: 적는 것이 판단이 아니라 잰 숫자와 사람이 실제로 한 말의 원문이고, 시점도 세션이 끝나는 순간 하나뿐이다. 그래서 들어가는 그릇도 교훈이 아니라 따로 만든 세션 측정 그릇이며, 그 그릇은 `namu_record`로 아예 쓸 수 없다. **이 훅은 교훈을 적지 않는다** — 이 경계가 무너지면 원칙이 무의미해진다. 등록은 `hooks/hooks.json`(Claude Code와 Grok이 읽는다 — agy는 대응 이벤트 없음). Grok은 훅 입력 칸을 낙타 등 표기로 보내고 대화 기록 경로를 주지 않으므로 `hooks/hook_input.py`가 두 표기를 한 함수로 읽고, 마무리 검사는 Grok 세션 폴더의 `chat_history.jsonl`에서 사람이 친 마지막 말을 읽는다. Grok은 SessionStart 표준출력과 통과시킨 UserPromptSubmit의 `additionalContext`를 모델에 넣지 않으므로 브리핑과 상시 재알림이 자동으로 뜨지 않는다 — 브리핑은 스킬 `skills/namu/`(`/namu`)로 부른다. 세션 측정은 클로드 형식 대화 기록만 읽어 Grok에서는 아직 돌지 않는다
- `namu-plugin/memory_sync.py` — `~/.namu`의 선택적 git 자동 동기화(record 직후 auto push, 세션 시작 시 auto pull). `namu_sync_setup`으로 명시 활성화해야 동작. `.gitattributes`의 `merge=union` 라인은 하드코딩하지 않고 `config.BOWLS`에서 파생한다(namu-57 — 아래 "그릇 레지스트리" 참고). **멈춘 병합 뒷정리를 이 파일 한 벌로 모았다**(2026-09-25 리뷰 C) — 전에는 `startup_sync.startup_pull`만 멈춘 병합을 되돌렸고, `sync_pull`·`_push_steps`의 복구 pull·`sync_setup_report`의 병합은 실패를 로그만 남긴 채 충돌 표시(`<<<<<<<`)를 워킹트리에 두고 돌아갔다 — 다음 `namu_record`의 sync_push가 그것을 그대로 커밋해 원격에 올렸다(`memo.yaml`이 `merge=file`이라 두 PC가 메모만 붙여도 이 길로 들어간다). 지금은 네 경로 전부(`sync_pull`·`_push_steps` 복구 pull·`sync_setup_report` 병합·`startup_sync.startup_pull`)가 `merge_in_progress`/`abort_merge`/`settle_failed_merge` 공용 함수를 부르고, `_push_steps`와 `startup_sync.commit_pending`은 병합이 멈춘 채면 아예 커밋하지 않고 실패로 끝난다. 충돌이 **`memory/memo.yaml` 하나뿐**이면 `settle_failed_merge`가 되돌리지 않고 3-way id 병합으로 자동으로 푼다 — `git show :1:/:2:/:3:`으로 base/ours/theirs를 읽어 (ours ∪ theirs)에서 base에 있었는데 어느 한쪽이라도 뗀 id를 빼고, 같은 id가 양쪽에서 달라졌으면 ours를 쓰며, 결과는 id(ULID) 순으로 정렬한다 — memo는 붙이기·떼기만 있어 id 집합 연산으로 양쪽 의도가 다 표현된다. 그 밖의 경로가 걸리거나 형식이 깨지면 종전처럼 되돌린다. **`sync_setup_report()`가 구조화 반환**(`text`/`notes`/`fatal`/`network`)을 하면서 `deploy/namu_cloud_sync_setup.py`가 이것을 그대로 쓴다 — fetch/병합/push 같은 네트워크급 실패는 exit 0으로 넘기고 `~/.namu/db/startup_sync.json`에 경고만 남겨 세션 브리핑·`namu_recall`의 warnings로 뜨다가 pull이 실제로 성공하면 지워지고, init·원격 등록·마커·커밋 같은 로컬 wiring 실패만 치명(exit 1)이다 — GitHub 장애나 PAT 만료가 2026-08-16 무한 재시작 사고를 되풀이하는 것을 막기 위해서다. **`sync_setup`은 더 이상 `git add -A`를 쓰지 않는다** — `SETUP_COMMIT_TARGETS`(`.gitignore`·`.gitattributes`·`.namu_sync`·`memory/`·`tasks/`·`config/`)만 add한다. **개인 PC도 죽은 git 잠금을 청소한다**(`clear_stale_git_locks`, 컨테이너와 공용 함수) — 컨테이너 문턱은 1시간 그대로고, 개인 PC의 `sync_pull`은 10분(`PERSONAL_STALE_LOCK_AGE_SECONDS=600`)으로 더 짧다 — 이 모듈의 git 호출 타임아웃 중 가장 긴 것이 120초(첨부)라 10분 넘은 잠금은 살아 있는 git의 것일 수 없다고 본다. **`memory/.memo.lock`(memo.py의 프로세스 간 잠금)과 `db/`는 `.gitignore`가 아니라 `.git/info/exclude`에 넣는다**(`ensure_local_excludes`) — 이미 개통된 기기는 `sync_setup`을 다시 돌리지 않아 `.gitignore` 줄을 못 받고, 줄을 추가하면 새 기기가 독립 init으로 온보딩할 때 옛 판이 만든 원격과 add/add 충돌이 난다
- `namu-plugin/startup_sync.py` — **시작 동기화**(namu-entrypoint-pull-resilience). 클라우드 컨테이너가 뜰 때 잠금 청소 → 미커밋 변경 보존 커밋 → pull → 충돌 시 되돌리기를 한 번 돌린다. **받아오기 실패는 기동을 막지 않는다** — 2026-08-16 실사고에서 커밋 안 된 파일 2개가 pull을 막았고, 그때 `entrypoint.sh`가 `exit 1`로 끝내는 바람에 재시작 정책(`always`)과 맞물려 14회 무한 재시작·반나절 502가 났다(기억 읽기·쓰기 자체는 멀쩡했다). 대신 실패 사실은 `~/.namu/db/startup_sync.json`에 남아 **세션 브리핑 경고와 `namu_recall` 반환의 `warnings` 키**로 계속 뜨고, 받아오기가 실제로 성공할 때만 사라진다(`memory_sync.sync_pull` 성공 경로도 지운다). 커밋 안 된 변경은 **버리지 않고 커밋해 보존**한다 — `git reset --hard`는 남의 기억을 버리는 것이다. clone 실패는 종전대로 치명적이다(빈 서버가 뜨면 그 위에 쌓인 기록이 원격 이력과 갈라진다). 셸에 로직을 두지 않은 이유는 검사 때문이다 — `test_startup_sync.py`가 실제 임시 저장소(원격 bare + 클론 둘)로 사고를 재현한다. **멈춘 병합 되돌리기는 이제 `memory_sync`의 공용 함수**(`merge_in_progress`/`abort_merge`/`settle_failed_merge`)를 그대로 쓴다(2026-09-25 리뷰 C) — 이 파일에만 있던 되돌리기 로직이 `sync_pull`·`_push_steps`·`sync_setup_report`로도 번졌고, 원본은 그쪽으로 옮겨졌다. `commit_pending`도 병합이 멈춘 채면 add/commit 없이 사유만 돌려주고 미커밋 변경을 그대로 둔다 — 충돌 표시를 "보존"해 원격에 그대로 올리는 사고(검수 재현)를 막기 위해서다. 잠금 청소도 `memory_sync.clear_stale_git_locks` 공용 함수를 쓰며, 컨테이너 문턱은 여전히 1시간(`STALE_LOCK_AGE_SECONDS`)이다 — 개인 PC의 `sync_pull`은 10분으로 더 짧다(memory_sync.py 몫 참고)

## 설계 문서

- `docs/plan.md` — NAMU 전체 계획·결정 이력·로드맵
- `docs/mcp_memory_design.md` — MCP 메모리 서버 상세 설계 (스키마, SQLite 테이블, 도구 명세)
- `docs/memory_schema_v2.md` — **기억 구조 v2 (namu-65, 2026-07-31 완료 · v0.1.43)**. 모든 그릇 공통 3층(`summary`/`reason`/`body`), 입력 항목 19개→13개 통일. **현행 구조 설명서**이며 4장의 칸 표는 `config.FIELDS`에서 자동 생성된다(`python scripts/gen_field_docs.py`, 손으로 고치면 `test_field_docs.py` 실패) — 기록 관련 작업 전 반드시 읽을 것
- `docs/attach_files.md` — **첨부 파일 주고받기 (2026-08-07 완료 · 완료 보고서)**. 도구 일곱 개, 첨부 폴더 격리를 지키는 git 절차, 티켓(파일 몸통이 AI의 출력을 안 거치는 길), 설계서 2판에서 바뀐 것과 그 이유. 클라우드 몫은 `namu-cloud-routing/docs/namu_attach_files.md` — **첨부 관련 작업 전 반드시 읽을 것**(특히 "크기를 저장소에 물으면 격리가 뚫린다"는 되돌릴 수 없는 실수다)
- `docs/search_index_unify.md` — **검색 통일 (2026-08-08 구현 완료)**. 다섯 그릇을 모두 SQLite 색인으로 모은 6단계 계획과 그 결과. 앞선 웹 설계문서의 전제 반증 근거, 두 글자 우회가 필수인 이유, 첨부 기록 그릇 몫(9장), 작업 설명서(task.md)를 작업일지 검색에 넣은 몫(11장)을 담았다 — 검색 관련 작업 전 반드시 읽을 것
- `docs/new_project_rule.md` — **새 프로젝트 자리 규칙 (2026-08-14 · 1~5단계 전부 완료 — 4단계 옮기기는 `task_move.py` + `namu_task_move`)**. 새 작업이 들어갈 프로젝트는 부르는 쪽이 적어 넣는 값이 아니라 규칙으로 정한다 — 내 PC는 열려 있는 폴더, 웹은 `web-project` 한 곳. 확인 칸·질문·시간 문턱으로 검사하던 게이트를 두 판 만들어 두 판 다 뚫린 경위와, 그래서 검사 대신 자리 자체를 없앤 근거를 담았다 — **작업 생성 경로를 건드리기 전 반드시 읽을 것**

구현 작업 시 위 문서를 먼저 참조할 것.

## 메모리 구조

- **`~/.namu/memory/learnings.yaml`** = 진실의 원천. append-only, `namu_sync_setup`으로 준비한 사용자 개인 원격 repo로 PC 간 공유(선택 기능). 데이터 루트는 `NAMU_DATA_ROOT`(=`Path.home() / ".namu"`) 고정 상수이며, 어떤 프로젝트에서 실행하든(이 개발 repo 포함, 환경변수로도 우회 불가) 항상 이 한 경로다 — namu-35로 "개발 모드/설치 모드" 구분 자체가 폐지됐다.
- **SQLite(`~/.namu/db/namu.db`)** = **다섯 그릇 전부**를 인덱싱한 로컬 검색 캐시(fts5-memo-tasks-index). gitignore 대상(namu_sync_setup이 자동 추가)이며, 지워도 원본에서 다시 만들어진다. 교훈은 자기 표(`learnings` + `learnings_fts`)를 쓰고 나머지 넷은 같은 모양의 표(`bowl_<이름>` + `bowl_<이름>_fts`, trigram)를 나눠 쓴다. **"낡았나" 판정은 그릇마다 원본 파일의 크기·수정시각을 모은 서명 하나로 하며**(`db._bowl_signature`, 교훈만 종전대로 스키마+건수), 세션 시작·서버 부팅·pull 직후에 `db.ensure_indexes()`가 바뀐 그릇만 다시 만든다. 검색어는 다섯 그릇 모두 **낱말별 AND**이고, 세 글자 미만이 섞이면 색인을 건너뛰고 LIKE로 전수 조회한다(trigram은 두 글자를 원리상 못 찾는다 — LIKE는 `%`·`_`를 글자 그대로 찾도록 막는다). **다시 만들기는 트랜잭션 하나이고 서명을 원본보다 먼저 잰다**(2026-09-25 리뷰 B — 도중에 읽는 쪽이 빈 표를 보거나, 경합으로 색인이 "최신" 판정을 받은 채 낡는 일을 막는다). **시각 저장 형식은 그릇마다 다르다** — 작업일지(log.md)는 `YYYY-MM-DD HH:MM:SS`(공백 구분·시간대 없음), 나머지 넷은 `YYYY-MM-DDTHH:MM:SS…+09:00`. since/until은 어느 형식으로 줘도 그릇의 형식으로 맞춘 뒤 비교한다. **작업일지 색인은 `paths`를 안 본다** — 늘 이 프로세스 HOME의 `~/.namu/tasks` 풀이다(클라우드는 작업일지만 회원 폴더를 직접 훑는다).
- **tasks(개인 풀 `~/.namu/tasks/<basename(프로젝트 폴더)>/`, namu-34)** = 작업 상태. **방 이름 해석**(`task_resolve.project_key_for`, 2026-09-25 리뷰 B): 구분자(`/`·`\`)가 없는 값은 방 이름으로 보고 파일시스템을 보지 않은 채 그대로 쓰며(예전에는 현재 폴더 기준으로 풀려 `'naite'`가 저장소 방으로 샜다), 구분자가 있는 폴더 경로만 뿌리(`.git`)를 찾아 올라간다. 빈 값·`.`·`..`처럼 풀 밖을 가리키는 방은 `tasks_root_for`가 ValueError로 거절한다(마지막 방어선 — 입구 검사는 `project_policy`). `log.md`가 유일한 권위 기록이며 "다음 할 일"도 마지막 `[다음]` 태그 줄로 여기 남긴다(namu-57). **검색은 `log.md` 줄과 `task.md` 한 장을 같은 그릇에서 함께 돌려준다**(fts5-memo-tasks-index 11장, 2026-08-08) — 설명서는 문서 한 장이 결과 한 건이고 `tag`가 `설명서`다. 반대로 `task_resolve.journal()`(브리핑의 최근 활동·마무리 검사)에는 설명서를 **섞지 않는다**: 설명서는 활동이 아니라서, 섞으면 오늘 아무 일도 없던 작업 84개가 활동 목록에 나타난다. `context.<machine>.md`는 레거시 읽기 폴백. **작업을 닫는 말은 `[완료]`·`[중단]` 둘뿐이다** — `[종료]`·`[마무리]` 같은 유의어는 저장은 되지만 닫지 못해 조용히 열린 채로 남으므로 `namu_record`가 거절한다(namu-66, 실물 사고: namu-37이 `[종료]`로 적혀 기록상 미종결). **책갈피(namu-70)** — "다음엔 이것부터"는 log가 아니라 `~/.namu/tasks/<방>/.pin.<machine>` 한 장에 적는다(기기 이름은 ASCII 영숫자·`.`·`_`·`-` 1~64자 — `task_resolve.MACHINE_NAME_RE` 한 곳에서 정하고 config가 `NAMU_MACHINE`을 이 규칙으로 다듬어 들인다. 규칙 밖 이름의 파일은 책갈피로 읽지 않는다)(`namu_task_pin`/`namu_task_unpin`). log에 적으면 ①append-only라 뗐다 붙였다를 표현할 수 없고 ②그 task의 `last_ts`가 갱신돼 **순서가 두 경로로 흔들린다** — 이 작업이 없애려던 "기록을 건드려 화면 순서를 바꾸는" 짓과 결과가 같아진다. 파일을 기기마다 가르는 것이 git 충돌 0의 근거이며(각 기기는 제 파일에만 쓴다), 여러 개면 최근에 꽂은 순으로 앞에 선다. 닫힌 task를 가리키는 책갈피는 파일을 지우지 않고도 화면에서 사라진다. 닫을 때 `task.md`에 안 채운 완료조건이 남아 있으면 반환문에 경고가 붙는다(막지는 않는다 — 이관·범위 축소는 정당한 종결 사유). 저장 위치는 학습 기억(`NAMU_DATA_ROOT`)과 별개 산출 기준(프로젝트 폴더명 basename)으로 정해지지만, 물리적으로는 같은 `~/.namu` 계열에 모인다. **새 작업이 들어갈 프로젝트는 부르는 쪽이 정하지 않는다** — 내 PC는 지금 열려 있는 폴더(없는 이름을 직접 주면 거절), 웹은 이미 있는 방이나 `web-project`를 골라 줘야 하고 안 정해졌으면 방 목록을 돌려준다 — 어느 쪽이든 새 프로젝트는 안 생긴다(`namu-plugin/project_policy.py`, 근거는 `docs/new_project_rule.md`).
- **`~/.namu/memory/memo.yaml`(namu-56)** = 스틱노트. 위 그릇들과 **반대로 append-only가 아니다** — 떼면 그 항목이 사라진다. "영화 8시 20분" 같은 일회성 메모가 갈 곳이 없어 learnings.yaml로 밀려들어오던 문제를 끊기 위한 그릇이라, **교훈 색인에는 섞지 않고** 자기 표(`bowl_memo`)를 따로 갖는다(fts5-memo-tasks-index — `config.BOWLS`의 `cached=True`, 뗀 쪽지가 검색에 남지 않도록 낡음 판정은 파일 크기·수정시각 서명으로 한다). git은 `merge=union`이 아니라 파일 단위다(union은 삭제를 표현하지 못해 뗀 메모가 병합 때 되살아난다). 세션 브리핑 맨 앞과 `namu_recall` 반환의 `memo` 키로 다시 나타난다.
- **`~/.namu/memory/attachments.yaml`(namu-file-upload-download 4단계)** = 첨부 기록. 사용자 저장소 `attach_file/`에 올린 파일의 **이력**만 담는다(몸통은 여기 없고, 그 폴더는 각 PC에서 sparse-checkout으로 격리돼 안 내려온다). append-only라 고치거나 지울 수 없으므로 **"지금 살아 있는 파일 목록"은 `status`(올림/새 판/지움)를 훑어 계산한다**(`attachments.current_files`). `bytes` 칸이 필수인 이유가 이 그릇의 급소다 — 목록 도구가 크기를 저장소에 물으면 git이 크기를 알아내려고 빠진 파일 몸통을 전부 내려받아 격리가 뚫린다(2026-08-07 실측: 파일 2,548개에 7분 넘게 안 끝나 중단).
- **`~/.namu/memory/sessions.yaml`(namu-self-improvement-loop)** = 세션 측정. 세션이 끝날 때 세션 종료 훅이 나이테를 **그 세션 하나에만** 돌려 어긋남 건수·구조 표지 수와 **사람 발화 원문 전부**를 남긴다. 이 그릇이 필요한 이유는 대화 기록(`~/.claude/projects`)의 두 제약이다 — 동기화되지 않아 그 기계에서 연 세션만 있고(웹 세션은 아예 없다), 약 28일이 지나면 사라진다. 기억은 동기화되고 지워지지 않으므로 여기로 모으면 어느 기계에서 연 세션이든 한자리에서 합산된다(2026-09-11 검증: 세션마다 따로 재서 합산한 값과 전체를 한 번에 잰 값이 어긋남 158건·세션 51개·세션당 3.10으로 일치). 숫자만이 아니라 원문까지 담는 이유는 **판정 규칙을 고쳤을 때 지나간 세션을 다시 잴 수 있어야** 하기 때문이다(2026-09-09에 실제로 재측정해 오탐을 27%에서 19%로 줄였다). 한 달치가 약 39KB다. 다른 다섯 그릇과 두 가지가 다르다 — `web_exposed=False`(`namu_record`로 쓸 수 없다. 잰 값과 지어낸 값이 섞이면 주간 점검이 무엇을 믿을지 알 수 없다)이고 `cached=False`(검색 색인에 안 넣는다. 읽는 곳이 주간 점검 하나뿐이라 yaml을 그대로 훑는다). 합산하는 쪽은 **session_id마다 마지막 항목 하나만** 센다(`sessions.latest_by_session`) — `--resume`으로 이어 열면 항목이 또 붙기 때문이다. `denials`는 사람이 거절한 것(`user-rejected`)만 담고, 거절 종류 원본은 `denial_kinds`(`{at, kind, tool}`)에 남긴다 — 이것이 있으면 다시 잴 때 여기서 거절을 다시 가르고, `interrupts`는 모든 중단을 담아 짝 거두기는 판정 때 한다 — 2026-09-25부터이며, 그 전 항목의 `denials`에는 자동 모드 차단이 섞여 있어 다시 가를 수 없다. 주간 점검의 세션당 어긋남 분모는 같은 날부터 "사람이 한 마디라도 한 세션"이다(전에는 어긋남이 1건 이상인 세션만 세어 AI가 나아져도 숫자가 안 내려갔다 — 옛 정의 값을 한 줄 함께 보여 준다).
- **ID** = ULID — 시간순 정렬 + 오프라인 다중 PC git 머지 충돌 0.

### 그릇 레지스트리 (namu-57 3단계)

그릇(learnings / profile / tasks)의 성질은 `config.py`의 `BOWLS`에 한 번만 선언한다 — `Bowl(name, git_patterns, mutable, merge, cached, web_exposed)`. `git_patterns`는 `~/.namu` 기준 상대 패턴이며 경로 상수(`LEARNINGS_YAML_PATH` 등)를 참조하지 않는다(`.gitattributes`가 상대 패턴만 받고, 경로 상수는 테스트가 monkeypatch하는 대상이기 때문).

**새 그릇을 추가할 때는 `BOWLS`에 등록하는 것이 병합 정책 결정을 겸한다** — `memory_sync`가 `merge == "union" and not mutable`인 그릇의 패턴에서 `.gitattributes` union 라인을 파생하므로, 손으로 라인을 따라 붙이는 절차가 없다. 이 구조로 바꾼 계기는 namu-49로 profile 그릇을 만들 때 하드코딩 목록을 아무도 갱신하지 않아 `profile.yaml`이 병합 보호 없이 방치됐던 실제 버그다(오프라인 양쪽 PC에서 사실을 추가하면 CONFLICT — 실측 재현됨). `mutable=True`인 그릇은 union에서 제외된다: 파일 전체가 수시로 바뀌는 그릇에 줄 단위 병합을 걸면 삭제한 항목이 되살아난다.

`BOWLS`에서 파생되는 이름 목록은 **셋이고 뜻이 다르다**(namu-self-improvement-loop에서 갈랐다). `ALL_BOWL_NAMES`는 등록된 그릇 전부이고, `BOWL_NAMES`는 `namu_record`가 받는 그릇(`web_exposed=True`)이며, `INDEXED_BOWL_NAMES`는 검색 색인을 타는 그릇(`cached=True`)이다. `BOWL_NAMES`가 `mcp_server._VALID_RECORD_BOWLS`와, `INDEXED_BOWL_NAMES`가 `db._VALID_BOWLS`와 일치해야 하며, 어긋나면 `test_bowls.py`가 실패한다. **갈라 둔 이유**: 칸 배치표·거절 메시지·도구 설명문이 전부 `BOWL_NAMES`에서 파생되므로, 손으로 쓸 수 없는 그릇이 거기 섞이면 안내문이 쓸 수 없는 이름을 권하게 된다.

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
- MCP / MCPServer (`mcp[cli]>=2.1,<3`) — 메모리 서버 인터페이스. **표준 2026-07-28 판**(무상태 전환)을 말하며, 같은 서버가 옛 판(2025-11-25 이하, 첫 인사 왕복 방식) 클라이언트도 그대로 응대한다 — SDK 2.x가 두 방식을 함께 서비스한다
- SQLite + FTS5(trigram) — 검색 캐시 (3자 미만 쿼리는 LIKE 폴백)
- uv + PEP 723 inline 메타데이터 — 플러그인 의존성 자급
- `python-ulid` / `PyYAML` / `python-dotenv`
- GitHub — 메모리·상태 동기화

## 작업 오케스트레이션 규칙
- 멀티스텝 구현 작업은 `/namu-task` 절차(namu-plugin/skills/namu-task/SKILL.md)를 따른다.
- 검수 fail 시 자동 재실행 금지 — 반드시 사용자 게이트(재실행/통과/중단)를 거친다.
- recall/record는 오케스트레이터만 호출한다. 워커는 메모리에 직접 쓰지 않는다.
