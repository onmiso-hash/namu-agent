# NAMU MCP 메모리 서버 설계 메모

> 📅 작성: 2026-06-24 | 갱신: 2026-06-24 (db.py 읽기계열 recall/search 구현 완료) | 갱신: 2026-07-18 (#49 2그릇 메모리 — profile.yaml + kind 라우팅 반영) | 구현용 청사진
> 목표: NAMU의 메모리/학습 코어(C층)를 MCP 서버로 노출 → 어떤 AI(Claude Code/agy/Cursor)든 같은 기억 공유

---

## 🎯 왜 MCP인가

- **포터블** = MCP 서버 하나면 모든 MCP 클라이언트가 붙음 (벤더 중립 = NAMU 핵심 가치)
- Hook/Skill/CLAUDE.md는 Claude Code 전용 글루라 포터블 아님 → 메모리만큼은 반드시 MCP로
- 한 번 만들면 재사용: Claude Code용 글루, agy용 글루가 전부 같은 MCP 서버를 바라봄

---

## 🛠️ 노출할 도구 3개 (MVP)

> **세 그릇, 도구는 여전히 3개 (#49 두 그릇 → namu-57 2단계에서 세 그릇으로 확장,
> 2026-07-25):** 메모리는 learnings.yaml(교훈/대화기록)·profile.yaml(사실·선호)·
> tasks(작업 로그, `~/.namu/tasks/<project>/*/log.md`) 세 그릇으로 나뉘지만, 도구 개수는
> 3개에서 늘리지 않는다 — `namu_record`가 `bowl`(또는 하위호환용 `kind`) 파라미터로 세
> 그릇에 라우팅하고, `namu_search`가 `bowl` 파라미터로 세 그릇을 같은 축 집합
> (project/task/machine/via/since/until)으로 조회한다. **이건 claude.ai 커넥터의 플랫폼
> 제약이 아니라 스코프 결정이었다** — 요약이 옮겨 적히며 "웹 3-도구 제약"으로 둔갑했던
> 표현을 여기서 바로잡는다(namu-57 실측 확인, 상세는 `docs/remote_mcp_design.md` §8).
> 상세는 아래 "🧠 두 그릇 구조" 절도 참고(명칭은 #49 시절 그대로 두 그릇으로 남아있으나
> 세 번째 그릇 tasks는 SQLite 캐시가 없는 log.md 자체가 원본이라 성격이 또 다르다).

> **recall vs search 역할 분리 (2026-06-24 확정):** 둘 다 query를 받지만 목적이 다르다.
> - **recall = 작업 시작 전 "맥락 로딩"** → 뭐라도 돌려줌(관련 부족하면 최신순 폴백)
> - **search = 판단 중 "패턴 분석"** → 정확히 매칭되는 것만, 없으면 빈 결과 + 항상 경향 요약 첨부
> - 내부 FTS 로직은 private 헬퍼(`_fts_query`)로 공유하되, 폴백·요약 동작으로 차별화

### 1. `namu_recall` — 과거 맥락 조회 (작업 시작 전 맥락 로딩)
세션 시작 시 또는 작업 착수 전에 관련 기억을 불러온다. "뭐라도 준다"가 핵심.

| 항목 | 내용 |
|------|------|
| 입력 | `query`(str, 선택): 주제 키워드 / `task_type`(str, 선택): 필터, learnings에만 적용 / `limit`(int, 기본 5, learnings에만 적용) / `project`(str, 선택, namu-57 2단계 보완): 열린 task를 볼 프로젝트 — `namu_search(bowl='tasks')`와 동일 규칙(stdio는 생략 시 현재 프로젝트, 웹은 생략 시 전체 프로젝트 합침, `'*'`는 양쪽 모두 명시적 전체) |
| 출력 | **세 그릇 dict** — `{"profile": [...활성 fact 전부, limit 없음...], "learnings": [...검색결과: 시각, 작업유형, 결과, **판단 이유**, kind, 태그...], "tasks": [...열린 task 전부, 최근 활동순: {"project","slug","title","last_ts","next"}...]}` (namu-57 2단계 보완, 2026-07-25 — 기존 `profile`/`learnings` 키는 형태·내용 100% 하위호환, `tasks`는 신규 추가) |
| 동작 | `profile`은 항상 `profile.active()`로 전체 반환(작아서 필터·limit 없음). `learnings`는 query 있으면 FTS 관련도순 → 결과 부족하면 최신순 폴백, query 없으면 `ORDER BY id DESC` 최신 N개(kind=lesson/note 모두 포함). `tasks`는 `task_resolve.open_tasks_briefing()`이 `find_open_tasks`+`next_note`를 조합해 산출 — `next`는 그 task의 마지막 `[다음]` 로그 줄 **전문**(자르지 않음, 없으면 `None`)이라 이것만 보고 바로 이어 작업할 수 있다. 최근 활동 스크롤백(로그 줄 나열)은 이 도구가 아니라 `namu_search(bowl='tasks')` 몫이다(토큰 절약) |
| 웹 사용 이유 (namu-57 2단계 보완) | 웹(claude.ai 커넥터)엔 세션 훅이 없어 로컬처럼 브리핑이 자동 주입되지 않는다 — "남은 작업/다음 작업 뭐야"류 질문에 웹 AI가 이 도구를 먼저 부르도록 docstring이 유도한다(훅이 없는 환경에서 유일한 유도 수단) |

### 2. `namu_record` — 결과+이유 기록, `bowl`(또는 `kind`)로 세 그릇 라우팅 (자가학습 핵심)
작업이 끝나면 결과뿐 아니라 **판단 이유**까지, 또는 프로젝트 작업 로그 한 줄을
append-only로 저장한다. `bowl`(learnings/tasks/profile, 생략 시 `kind`에서 유도)에 따라
쓸 그릇이 갈린다(#49 두 그릇 → namu-57 2단계에서 tasks 추가, 2026-07-25).

| 항목 | 내용 |
|------|------|
| 공통 입력 | `bowl`(str, 선택): `learnings`\|`tasks`\|`profile` — 생략하면 `kind`에서 유도(fact→profile, lesson/note→learnings, 기존 호출 100% 하위호환). 명시한 `bowl`이 `kind`와 모순되면(예: `bowl='learnings'`+`kind='fact'`) 즉시 `ValueError` |
| `learnings` 전용 입력 (`kind=lesson`\|`note`, 기본 `lesson`) | `task`(str) / `outcome`(str, 선택): success/failure/partial — lesson은 필수, note는 생략 가능 / `reason`(str, **필수**) / `task_type`(str) / `tags`(list, 선택) |
| `profile` 전용 입력 (`kind=fact`) | `subject`(str, free-form 권장값 user/environment/preference) / `statement`(str) / `source`(str, **필수** — "왜 이걸 믿나/어떻게 알았나") / `supersedes`(str, 선택 — 정정 대상 옛 fact id) |
| `tasks` 전용 입력 | `project`(str): 프로젝트 폴더명 — stdio는 생략 시 "현재 프로젝트", 웹은 **필수**(cwd 개념이 없음, `'*'`는 기록에 못 씀) / `task`(str): task 슬러그(폴더명 완전일치 우선, 없으면 `namu-57`처럼 접두일치 — 후보 0개/2개+면 열린 task 목록·후보를 곁들여 `ValueError`(0개 케이스는 `create=True` 안내 문구도 곁들임), `create=False`(기본) 상태에선 **새 폴더를 만들지 않음** |
| `tasks`, `create=True` 전용 입력 (namu-57 2단계 보완 신규) | 새 task 폴더를 만든다(웹은 로컬 `/namu-task` 스킬이 없어 이게 유일한 생성 경로). `project`(str, 위와 동일 규칙) / `task`(str, **새** 슬러그 — 폴더명 안전 문자만 허용: 영문/숫자/하이픈/언더스코어, 첫 글자 영문/숫자, `/`·`\`·`..` 등 경로 조작 문자는 `ValueError`) / `purpose`(str, **필수** — 목적 없는 task는 나중에 아무도 못 읽음, 빈 값이면 `ValueError`) / `title`(str, 선택, 생략 시 슬러그) / `done_when`(list[str], 선택 — 완료조건 체크박스로 렌더링) |
| 출력 | 기록된 항목 ID(ULID) — tasks는 ID가 없으므로 **실제로 append된 log.md 한 줄**(문자열). `create=True`는 사람이 읽을 수 있는 요약 문자열(생성 경로 + append된 `[시작]` 줄) |
| 동작 | learnings → **learnings.yaml에 먼저 append** → SQLite INSERT(트리거가 FTS 채움, 기존 경로). profile → **profile.yaml에 append**(profile.record_fact, SQLite 관여 없음). tasks(기존 슬러그) → 해당 task의 `log.md`에 `[tag] YYYY-MM-DD HH:MM:SS <machine> · text` 한 줄 append(`via`가 있으면 끝에 ` (via <라벨>)`) — git `merge=union`이라 여러 곳에서 동시 append해도 충돌이 0이다. tasks `create=True` → 이미 존재하면 `ValueError`(덮어쓰기 금지, task.md는 불변 목적·log.md는 append-only), 없으면 `task.md`+`log.md` 2파일을 SKILL.md '파일 템플릿' 형식대로 새로 쓰고(`context.<machine>.md`는 만들지 않음 — namu-57 신규 생성 중단) `[시작]` 줄을 append한 뒤 `memory_sync.sync_push` |
| 자동 채움 | learnings/profile: `id`(ULID)/`timestamp`(UTC)/`machine`. tasks: 실제 현지시각(`datetime.now()`)·`machine` — 지어 쓰면 멀티 PC 간 선후가 뒤집힌다 |
| ⚠️ 원칙 | learnings: `reason` 빈 값이면 `ValueError`. profile: `source` 빈 값이면 `ValueError`. tasks: `text` 빈 값, `]`·개행이 든 `tag`면 `ValueError`. tasks `create=True`: `purpose` 빈 값, 슬러그 경로조작 문자, 기존 슬러그 재사용 모두 `ValueError`. 이유/근거 없는 데이터 → 엉뚱한 패턴 도출 위험. **`tasks`의 `[완료]`/`[중단]` 태그는 task 전체 종료 신호다** — 중간 진행 보고에 쓰면 브리핑의 열린 task 목록에서 사라진다(실제 사고 2건, 오용 금지는 경고일 뿐 코드로 강제하지 않음) |

**저장 트리거 정책 — kind/bowl별 (#49 + namu-57 2단계 tasks 추가):**

| kind/bowl | 저장 트리거 | 강제 방식 |
|------|-------------|-----------|
| `lesson` | AI가 일반화할 교훈이라 스스로 판단해 호출 (현행 유지) | 코드 강제 없음 — AI 자율 판단 |
| `fact` | AI가 "이거 기억해둘까요?"라고 **제안 → 사용자 동의** 후 저장 | **소프트 정책, 코드로 강제되지 않음** — `record_fact`엔 "물어봤는지"를 판별할 단서가 없어 `source` 필수(ValueError)처럼 하드하게 막을 수 없다. 권장 동작일 뿐 강제가 아니라는 한계를 정직하게 인지할 것 |
| `note` | 사용자가 명시적으로 "이 대화 기억해줘"라고 요청할 때만 | 코드 강제 없음. 원문 그대로가 아니라 **"결론+근거+핵심 인용"으로 정제한 기록**을 남긴다 |
| `tasks`(bowl) | 진행 중 언제든 자유 append(작업 로그이므로 lesson처럼 "일반화 가치" 판단 불필요) | 코드 강제 없음 — 단 `[완료]`/`[중단]` 태그 오용(진짜 종료가 아닌데 붙임)은 경고만 하고 막지 않는다 |

### 3. `namu_search` — 축 필터 조회 (판단 중 분석적 조회, namu-57 2단계로 3그릇 확장)
learnings/tasks/profile 세 그릇을 같은 축 집합으로 정밀 조회한다. "정확한 것만(+
learnings는 경향 요약)"이 핵심 — 뭐라도 돌려주는 `namu_recall`과는 반대 성격.

| 항목 | 내용 |
|------|------|
| 입력 | `bowl`(str, 기본 `learnings`): `learnings`\|`tasks`\|`profile` / `query`(str, **선택** — 생략하면 축만으로 필터링, 예: "어제 hp에서 뭐 했지"=`bowl='tasks', machine='hp', since=...`) / `project`(str, **tasks 전용**): 프로젝트 폴더명 — 생략 시 stdio는 "현재 프로젝트", 웹은 "전체 프로젝트 합침"(cwd 개념이 없음), `'*'`는 양쪽 모두 명시적 전체 조회 / `task`(str): learnings는 부분일치, tasks는 슬러그 완전/접두일치 / `machine`/`via`(str, 정확 일치) / `since`/`until`(str, 날짜 또는 날짜+시각, until은 날짜만 주면 그날 포함) / `outcome_filter`(str, learnings 전용) / `limit`(int, 기본 10) |
| 출력 | `{"bowl", "results": [...], "count": N}` — learnings만 `"summary": {success: N, failure: M, partial: K}` 추가 |
| 동작 | learnings: query 3자+ → FTS5 MATCH+bm25 / 2자 이하 `LIKE` 폴백, 매칭 없으면 빈 결과(폴백 없음). tasks: `task_resolve.journal()`로 여러 프로젝트/task의 `log.md`를 시간순 병합(SQLite 인덱싱 없음 — log.md가 권위), query는 text/tag/task_slug 부분일치를 limit 적용 **전**에 거른다. profile: `profile.active()`(supersede 제외) 로드 후 파이썬 필터 |
| ⚠️ | tasks의 `timestamp`는 PC 현지시각, learnings는 UTC — 그릇 간 `since`/`until` 값을 그대로 재사용하면 시간대만큼 어긋날 수 있다(저장 형식 통일은 이번 범위 밖) |

---

## 🧠 두 그릇 구조 (#49, 2026-07-18)

메모리는 "저장 성격 + 접근 패턴"이 다른 두 그릇으로 나뉜다. 하나로 합치지 않는 이유는 하나가
**검색 대상 컬렉션**(누적되며 늘어나고, FTS로 찾아야 하는 데이터)인 반면 다른 하나는
**작아서 통째로 들고 다녀도 되는 요약본**이기 때문이다.

| | **learnings.yaml** | **profile.yaml** |
|---|---|---|
| 담는 것 | 교훈(`kind=lesson`) + 대화기록(`kind=note`) | 사실·선호(fact) |
| 접근 패턴 | 검색 컬렉션 — query로 FTS 매칭해 관련도순/최신순으로 일부만 꺼냄 | 통째 로딩 — 항상 활성 항목 전체를 반환 |
| SQLite 캐시 | 있음 (`~/.namu/db/namu.db`, git pull 후 카운트 불일치 시 자동 재생성) | **없음** — 파일이 작아 인덱싱 이득보다 별도 캐시 유지 비용이 큼 |
| 정정 방식 | append-only. 옛 항목은 그대로 두고 새 항목만 쌓임(수정할 개념 자체가 없음 — 각 lesson/note는 독립 사실) | append-only + **`supersedes` forward pointer**. 사실이 바뀌면 옛 레코드를 고치지 않고 새 항목이 `supersedes: <옛 id>`를 달고 append됨 |
| "활성" 판정 | 없음(모든 항목이 대등) | **다른 어떤 항목의 `supersedes` 대상으로도 지목되지 않은 것**만 활성 — `recall`이 이 집합을 계산해 반환(`profile.active()`) |

**대화기록(`note`) 정제 방침** — note는 대화 원문을 그대로 붙여넣지 않는다. "결론 + 근거 +
핵심 인용"만 추려 `reason`에 담는다(원문 전체 저장은 검색 캐시를 노이즈로 채워 recall/search
품질을 떨어뜨림).

**`supersedes` 활성 계산 예시** — fact A(`id=X`)가 나중에 fact B(`id=Y, supersedes=X`)로
정정되면, X는 "Y의 supersedes 대상"이므로 비활성, Y만 활성으로 `namu_recall`이 반환한다. X는
파일에서 지워지지 않고 이력으로 남는다(append-only 원칙 유지).

---

## 🗂️ 데이터 흐름

```
[작업 중인 AI]
   │  recall ───→ 두 그릇(profile 전체 + learnings 검색결과) 받아 작업 시작
   │  record(kind=lesson/note) ───→ learnings.yaml + SQLite
   │  record(kind=fact)        ───→ profile.yaml (SQLite 캐시 없음)
   ▼
[MCP 메모리 서버] ──→ learnings.yaml (append-only, git 동기화 = 진짜 기억)
                 ├─→ SQLite (learnings 전용 로컬 캐시, 빠른 검색/패턴, gitignore)
                 └─→ profile.yaml (append-only, git 동기화, 캐시 없이 통째 로딩)
```

- **learnings.yaml** = source of truth (lesson/note), git으로 PC간 공유
- **SQLite** = learnings.yaml를 인덱싱한 로컬 캐시. git pull 후 자동 재생성. **profile.yaml은 이 캐시 대상이 아니다**
- **profile.yaml** = source of truth (fact), git으로 PC간 공유. 작아서 캐시 없이 매 호출 통째 로딩 + `supersedes` 기반 활성 필터링

---

## 🔧 기술 선택 (2026-06-24 확정)

- **언어:** Python 3.12 (기존 코드베이스와 통일)
- **MCP SDK:** 공식 `mcp` 패키지. 최신 안정판 **1.28.0** (2026-06-16, PyPI 검증). Python 3.10+ 요구 → 3.12 OK
  - ⚠️ **v2가 코앞** — 공식 저장소가 beta 2026-06-30 / 안정 v2 2026-07-27 목표 발표. v2는 전송 계층을 크게 바꿈
  - → **반드시 상한 핀:** `requirements.txt`에 `mcp[cli]>=1.28,<2` 로 고정
  - `[cli]` extra = `mcp` 명령어 + MCP Inspector(디버깅 툴) 동봉
- **고수준 API:** SDK 내장 FastMCP 사용 → `from mcp.server.fastmcp import FastMCP`, `@mcp.tool()` 데코레이터로 도구 정의
- **전송 방식:** stdio (로컬 실행) 우선, 추후 HTTP 고려
- **ID 생성:** ULID (`python-ulid`) — 시간순 정렬 + 다중 PC 충돌 0. recall 최신순과 궁합 좋음

---

## 🗃️ learnings 스키마 (확정, #49로 `kind` 필드 추가)

```
{
  id,           # ULID — 시간순 정렬되는 유니크 ID (다중 PC 머지 충돌 방지)
  timestamp,    # ISO 8601 UTC (PC별 타임존 차이로 정렬 꼬임 방지)
  task,         # str — 무슨 작업
  task_type,    # code/doc/analysis/other (권장값, free-form 허용)
  outcome,      # success/failure/partial — kind=lesson은 필수, kind=note는 생략(None) 가능
  reason,       # str, 필수 — 왜 그렇게 판단했나 / 왜 이 대화가 중요한가 (자가학습의 심장)
  machine,      # samsung/hp/home — .env의 NAMU_MACHINE에서 주입 (자동감지 X)
  verified_by,  # human/ai/unverified — Human-in/on-the-loop 전환의 핵심 구분자
  tags,         # JSON 배열 문자열 '["mcp","sqlite"]'
  kind          # lesson/note (기본 lesson, #49 신설) — 교훈 vs 정제된 대화기록 구분
}
```

**설계 결정 근거:**
- `id` = **ULID**. auto-increment 정수는 오프라인 PC들이 같은 번호를 만들어 git 머지 충돌 → ULID로 회피
- `machine` = ID에 박지 않고 **독립 컬럼**. ID는 ULID로 깔끔히, 머신 통계는 `GROUP BY machine`으로. `.env`(이미 gitignore)에 PC별 `NAMU_MACHINE` 값 한 번만 설정
- `verified_by` = append-only라 나중에 백필 불가 → 처음부터 기록. "사람이 검증한 성공 사례만" 뽑아 판단 기준 도출하려면 필수
- `tags` = JSON 문자열 1컬럼. 정규화(별도 테이블)보다 가벼움. trigram FTS가 JSON 내부 태그까지 검색해줌. 정밀 필터 필요 시 `json_each()`로 확장. ⚠️ `json.dumps(tags, ensure_ascii=False)` — 한글 이스케이프 방지
- `kind`(#49) = 같은 컬렉션(learnings.yaml/SQLite) 안에서 교훈과 대화기록을 구분하는 태그. 별도 테이블/파일로 안 쪼갠 이유는 둘 다 "검색 컬렉션" 접근 패턴(FTS 대상)이 같아서다 — 접근 패턴이 다른 fact만 profile.yaml로 분리했다(아래 profile 스키마 참고)

---

## 🧾 profile 스키마 (신설, #49 · 2026-07-18)

```
{
  id,           # ULID — 서버가 자동 생성
  timestamp,    # ISO 8601 UTC — 서버가 자동 생성
  subject,      # str, free-form (권장값: user/environment/preference) — 무엇/누구에 대한 사실인가
  statement,    # str — 사실/선호 그 자체
  source,       # str, 필수 — 왜/어떻게 이걸 사실로 아는가 (learnings의 reason에 대응하는 자리)
  supersedes,   # str, 옵션 — 이 항목이 정정하는 옛 fact의 id (없으면 None/생략)
  machine,      # samsung/hp/home — 서버가 자동 생성
  verified_by,  # human/ai/unverified
  tags          # 리스트
}
```

**설계 결정 근거:**
- `id`/`timestamp`/`machine` = learnings와 동일하게 서버가 자동 채움 — 호출자가 넘기지 않는다
- `source`가 필수인 이유 = learnings의 `reason`과 같은 역할. 근거 없는 fact는 나중에 "이거 왜 저장했지?"를 답할 수 없어 신뢰도 판단이 불가능해진다
- `supersedes` = append-only 원칙 아래 "사실은 시간이 지나면 바뀐다"를 표현하는 유일한 수단. 옛 항목을 고치거나 지우지 않고, 새 항목이 옛 id를 가리키는 forward pointer로 append된다
- SQLite 캐시가 없는 이유 = 두 그릇 구조 절 참고 — 파일이 작아 통째 로딩 비용이 인덱싱 이득보다 낮다고 판단

---

## 🗄️ SQLite 테이블 설계 (확정, #49로 `kind` 컬럼 추가·outcome nullable 완화)

> 핵심: 메인 테이블에만 INSERT, FTS는 트리거로 자동 동기화. append-only라 구조 단순.
> **profile.yaml은 이 SQLite에 없다** — 두 그릇 중 learnings(lesson/note)만 캐시 대상이고,
> profile(fact)은 작아서 캐시 없이 매 호출 통째 로딩한다(위 "두 그릇 구조" 절 참고).

```sql
-- 메인 구조화 저장소
CREATE TABLE learnings (
    id          TEXT PRIMARY KEY,        -- ULID (TEXT PK라 내부 rowid 별도 존재 → FTS 연결용)
    timestamp   TEXT NOT NULL,           -- ISO 8601 UTC
    task        TEXT NOT NULL,
    task_type   TEXT,                    -- code/doc/analysis/other
    outcome     TEXT CHECK(outcome IS NULL OR outcome IN ('success','failure','partial')),  -- #49: nullable — kind=note는 outcome 생략 가능
    reason      TEXT NOT NULL,           -- 심장
    machine     TEXT,                    -- samsung/hp/home (.env 주입)
    verified_by TEXT CHECK(verified_by IN ('human','ai','unverified')),
    tags        TEXT,                    -- JSON 배열 문자열
    kind        TEXT                     -- #49 신설: lesson/note (앱 레이어에서 검증, SQL CHECK 없음)
);

CREATE INDEX idx_learnings_type    ON learnings(task_type);
CREATE INDEX idx_learnings_outcome ON learnings(outcome);

-- 전문검색용 (한글 부분검색 위해 trigram)
CREATE VIRTUAL TABLE learnings_fts USING fts5(
    task, reason, tags,
    content='learnings',
    content_rowid='rowid',
    tokenize='trigram'
);

-- INSERT 시 FTS 자동 채움 (append-only → INSERT 트리거 하나면 충분)
CREATE TRIGGER learnings_ai AFTER INSERT ON learnings BEGIN
  INSERT INTO learnings_fts(rowid, task, reason, tags)
  VALUES (new.rowid, new.task, new.reason, new.tags);
END;
```

**outcome nullable로 완화한 이유(#49):** 기존엔 `NOT NULL CHECK(outcome IN (...))`로 항상
success/failure/partial 중 하나를 강제했다. `kind=note`(대화기록)는 "성공/실패" 개념이 없는
데이터라 이 제약을 그대로 두면 note를 못 넣는다 → `outcome IS NULL OR outcome IN (...)`로
완화하되, `kind=lesson`은 애플리케이션 레이어(`db.record`)에서 여전히 outcome을 강제한다(SQL
CHECK만으로는 kind별 조건부 필수를 표현할 수 없어 검증을 Python으로 옮김).

**`kind` 컬럼에 SQL CHECK를 안 둔 이유:** `namu_record`가 `kind='fact'`를 받으면 애초에 이
테이블에 INSERT하지 않고 profile.yaml로 라우팅하므로, 이 테이블에 실제로 들어오는 값은
lesson/note뿐이다. 검증은 `db.record()`의 `_VALID_KINDS` 체크로 충분하다고 판단해 SQL
CHECK는 생략했다.

**한글 전문검색 — trigram 채택 (검증 완료):**
- 기본 `unicode61` 토크나이저는 공백 구분 어절만 매칭 → 한글 부분검색 불가
- `trigram`(SQLite 3.34.0+ 내장)은 3바이트 시퀀스로 CJK 부분검색 네이티브 지원
- ⚠️ **함정:** trigram은 최소 3글자(CJK 9바이트) 필요 → 한글 2글자 검색어("버그","검색" 등) 인덱스 미적용
- → **대응:** `namu_search`에서 **2글자 이하는 `LIKE '%..%'` 폴백**으로 처리
- 외부확장 `better-trigram`(2글자/CJK 개선)은 `.so` 컴파일 필요 → 다중 PC 배포 부담으로 보류. 내장 trigram + LIKE 폴백이 "어디서나 가볍게" 원칙에 부합
- ⚠️ 배포 전 확인: 두 PC 모두 `sqlite3.sqlite_version` ≥ 3.34 & FTS5 활성 (Python 3.12면 거의 충족하나 실측 권장)

**도구별 쿼리 매핑 (#49로 namu_record/namu_recall이 두 그릇을 다루도록 갱신):**

| 도구 | 쿼리 방식 |
|------|-----------|
| `namu_record` (`kind=lesson`/`note`) | `learnings`에 INSERT (트리거가 FTS 채움) + learnings.yaml에 append |
| `namu_record` (`kind=fact`) | `profile.record_fact` → profile.yaml에 append (SQLite 관여 없음) |
| `namu_recall` | learnings: `SELECT … ORDER BY id DESC LIMIT ?` (+ task_type 필터, ULID 정렬로 최신순 공짜) / profile: `profile.active()`가 yaml 통째 로딩 후 supersedes 필터링 — 두 결과를 `{"profile":…, "learnings":…}`로 합쳐 반환 |
| `namu_search` | `learnings_fts MATCH ?` → `learnings` 조인, `ORDER BY bm25()`. 2글자 이하 `LIKE` 폴백. `GROUP BY outcome COUNT(*)`로 성공/실패 경향 요약 (이 행은 #49 시점 스냅샷 — **→ namu-57 2단계에서 개정:** `db.search_bowl()`이 신설돼 `namu_search`가 `bowl` 파라미터로 tasks/profile도 조회할 수 있게 됐다. "profile은 search 대상 아님"이라는 원래 전제는 무효. 상세는 위 "🛠️ 노출할 도구 3개" 절 참고) |

**db.py conn 처리 두 패턴 (의도된 분리 — 통일하지 말 것):**
- **읽기 계열(`recall`, `search`)**: `conn`을 인자로 받음 → `:memory:` 주입으로 단위 테스트 용이 (검증 스크립트가 이 패턴 활용)
- **쓰기 계열(`record`, `init_db`, `rebuild_from_yaml`)**: 함수 내부에서 conn을 열고 닫음 → YAML-first → SQLite 트랜잭션 경계를 함수 안에서 완결

**재생성(rebuild) 방식:** git pull로 learnings.yaml 최신화 후 → `.db` 파일 통째 삭제 → `safe_load_all()` 로 파싱하며 전체 재INSERT (트리거가 FTS 자동 재구축). DELETE/UPDATE 트리거 불필요.

---

## 📄 learnings.yaml entry 포맷 (확정 · 구현 검증됨)

> source of truth. record가 쓰고 rebuild가 읽는 **짝**. YAML 멀티 문서(`---` 구분).
> `yaml.safe_dump(allow_unicode=True)` 로 쓰고 `yaml.safe_load_all()` 로 읽는다.

```yaml
---
id: 01KVW827WN0NYS6V0TF0PCJHQB
machine: hp
outcome: success
reason: trigram 토크나이저가 한글 3글자 이상 부분검색을 네이티브 지원함. 2글자 이하는 LIKE 폴백 필요.
tags:
- sqlite
- fts5
- 한글검색
task: SQLite FTS5 trigram 인덱스 설계
task_type: code
timestamp: '2026-06-24T07:21:12.341335+00:00'
verified_by: human
```

> ⚠️ 위 예시는 `kind` 필드 도입(#49) 이전에 실제 기록된 항목이라 `kind`가 없다. #49 이후 신규
> 항목은 `kind: lesson`(기본값)이 항상 함께 저장된다. `kind: note` 항목은 아래처럼 `outcome`이
> 없을 수 있다:

```yaml
---
id: 01K...NOTE
kind: note
machine: hp
outcome:
reason: 사용자가 "이 대화 기억해줘"라고 명시 요청 — 결론+근거만 정제해 저장(원문 전체 아님)
tags:
- 설계논의
task: (kind=note는 task도 대화 요지 요약으로 채움)
task_type: other
timestamp: '2026-07-18T00:00:00.000000+00:00'
verified_by: human
```

- **id/timestamp/machine** = record 호출 시 서버가 자동 생성 (호출자 안 넘김)
- **reason** = 한 줄이면 평문, 여러 줄이면 `|` 블록 스칼라로 자동 처리됨
- **tags** = YAML 리스트. 한글 태그도 이스케이프 없이 저장됨 (`allow_unicode=True`)
- **outcome** = success/failure/partial 중 하나만(CHECK 제약) — **단 `kind: note`는 생략 가능**(None으로 저장, #49)
- **kind**(#49) = `lesson`(기본) / `note`. `fact`는 이 파일이 아니라 profile.yaml로 라우팅되므로 여기 나타나지 않는다
- ⚠️ 빈 문서(None)는 rebuild 시 필터링 (파일 끝 trailing `---` 대비)

---

## 📄 profile.yaml entry 포맷 (신설, #49 · 구현 검증됨)

> source of truth. `profile.record_fact`가 쓰고 `profile.load_all`/`profile.active`가 읽는
> **짝**. learnings.yaml과 같은 YAML 멀티 문서(`---` 구분) + `safe_dump(allow_unicode=True)` /
> `safe_load_all()` 관례를 그대로 따른다. **SQLite 대응 파일이 없다** — 이 yaml이 유일한 저장소.

```yaml
---
id: 01K...FACT1
machine: hp
source: 사용자가 세션 중 직접 말함 — "나는 항상 WSL bash를 쓴다"
statement: hp 기기는 WSL bash 환경을 사용한다
subject: environment
supersedes:
tags:
- 기기환경
timestamp: '2026-07-18T00:00:00.000000+00:00'
verified_by: human
```

정정 예시 — 옛 사실이 바뀌면 새 항목이 옛 id를 `supersedes`로 가리키며 append된다(옛 항목은
그대로 남되 비활성 처리됨):

```yaml
---
id: 01K...FACT2
machine: hp
source: 사용자가 새 PC로 교체하며 정정
statement: hp 기기는 이제 WSL2 Ubuntu 24.04를 사용한다
subject: environment
supersedes: 01K...FACT1
tags:
- 기기환경
timestamp: '2026-08-01T00:00:00.000000+00:00'
verified_by: human
```

- **id/timestamp/machine** = record_fact 호출 시 서버가 자동 생성
- **source** = 필수(learnings의 reason에 대응) — 빈 값이면 `ValueError`
- **supersedes** = 옵션. 값이 있으면 그 id를 가진 옛 항목이 "활성" 집합에서 빠진다(`profile.active()`가 이 계산을 수행)
- **subject** = free-form이나 `user`/`environment`/`preference` 권장

---

## ✅ 진행 체크리스트

1. [x] Python MCP SDK 최신 버전·설치법 확인 → `mcp[cli]>=1.28,<2`, FastMCP 사용 (2026-06-24)
2. [x] learnings 항목 스키마 확정 → ULID + machine + verified_by 추가 (2026-06-24)
3. [x] SQLite 테이블 설계 (FTS 포함) → trigram + LIKE 폴백, INSERT 트리거 동기화 (2026-06-24)
4. 🔶 `db.py` 구현
   - [x] 쓰기 계열: `init_db` / `record`(yaml-first, reason 필수) / `rebuild_from_yaml` — 검증 완료, 커밋 `08afc69` (2026-06-24)
   - [x] 읽기 계열: `recall`(맥락 로딩+폴백) / `search`(FTS+LIKE 폴백+경향 요약) — 검증 완료, 커밋 `d191a7d` (2026-06-24)
5. [x] `mcp_server.py` — FastMCP로 도구 3개 노출 + stdio — 검증 완료, 커밋 `573ae33` (2026-06-24)
6-a. [x] MCP Inspector stdio 실호출 검증 (완료)
6-b. [x] Claude Code에 stdio 서버 등록 (local 스코프, namu-memory)
     └ 세션 /mcp 라이브 호출(namu_recall) 검증은 사용자가 새 세션에서 확인
7. [x] git pull 후 SQLite 자동 재생성 배선 — 카운트 비교(yaml id 수 vs db COUNT) 방식, 부팅 시 _ensure_db()에서 판정. 커밋 7e81906 (2026-06-26)
8. [x] 2그릇 메모리(#49) — `profile.yaml`(fact, SQLite 캐시 없음) 신설, `namu_record`에 `kind`(lesson/fact/note) 라우팅, `namu_recall` 출력이 `{"profile":…, "learnings":…}` dict로 변경, learnings `outcome` nullable 완화(kind=note). 코드 구현·테스트 완료(`namu-plugin/profile.py`, `test_profile.py`, `test_db_kind.py`), 이 문서는 2026-07-18 사후 반영

**환경 확인 완료:** HP `sqlite3` 3.45.1 + FTS5/trigram OK / `python-ulid`,`PyYAML` 설치됨 / `.env`에 `NAMU_MACHINE=hp`
**다음 PC(삼성) 설정 시:** `.env`에 `NAMU_MACHINE=samsung`

---

## 💭 열린 질문 (나중에 논의)

- recall을 SessionStart 훅에서 자동 호출할지, AI가 필요할 때 부르게 할지
- record를 Stop 훅에서 자동 기록할지, AI가 명시적으로 부르게 할지 (자동 = 누락 없음 / 수동 = 노이즈 적음)
- 패턴 분석을 SQLite 쿼리로 할지, 별도 분석 단계를 둘지
