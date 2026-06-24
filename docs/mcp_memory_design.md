# NAMU MCP 메모리 서버 설계 메모

> 📅 작성: 2026-06-24 | 갱신: 2026-06-24 (db.py 읽기계열 recall/search 구현 완료) | 구현용 청사진
> 목표: NAMU의 메모리/학습 코어(C층)를 MCP 서버로 노출 → 어떤 AI(Claude Code/agy/Cursor)든 같은 기억 공유

---

## 🎯 왜 MCP인가

- **포터블** = MCP 서버 하나면 모든 MCP 클라이언트가 붙음 (벤더 중립 = NAMU 핵심 가치)
- Hook/Skill/CLAUDE.md는 Claude Code 전용 글루라 포터블 아님 → 메모리만큼은 반드시 MCP로
- 한 번 만들면 재사용: Claude Code용 글루, agy용 글루가 전부 같은 MCP 서버를 바라봄

---

## 🛠️ 노출할 도구 3개 (MVP)

> **recall vs search 역할 분리 (2026-06-24 확정):** 둘 다 query를 받지만 목적이 다르다.
> - **recall = 작업 시작 전 "맥락 로딩"** → 뭐라도 돌려줌(관련 부족하면 최신순 폴백)
> - **search = 판단 중 "패턴 분석"** → 정확히 매칭되는 것만, 없으면 빈 결과 + 항상 경향 요약 첨부
> - 내부 FTS 로직은 private 헬퍼(`_fts_query`)로 공유하되, 폴백·요약 동작으로 차별화

### 1. `namu_recall` — 과거 맥락 조회 (작업 시작 전 맥락 로딩)
세션 시작 시 또는 작업 착수 전에 관련 기억을 불러온다. "뭐라도 준다"가 핵심.

| 항목 | 내용 |
|------|------|
| 입력 | `query`(str, 선택): 주제 키워드 / `task_type`(str, 선택): 필터 / `limit`(int, 기본 10) |
| 출력 | 관련 learning 항목 리스트 (시각, 작업유형, 결과, **판단 이유**, 태그) |
| 동작 | query 있으면 FTS 관련도순 → 결과 부족하면 최신순 폴백. query 없으면 `ORDER BY id DESC` 최신 N개 |

### 2. `namu_record` — 결과 + 이유 기록 (자가학습 핵심)
작업이 끝나면 결과뿐 아니라 **판단 이유**까지 append-only로 저장.

| 항목 | 내용 |
|------|------|
| 입력 | `task`(str) / `outcome`(str): success/failure/partial / `reason`(str, **필수**) / `task_type`(str) / `verified_by`(str) / `tags`(list, 선택) |
| 출력 | 기록된 항목 ID(ULID) |
| 동작 | **learnings.yaml에 먼저 append** (삭제·수정 금지) → SQLite INSERT (트리거가 FTS 채움) |
| 자동 채움 | `id`(ULID) / `timestamp`(UTC) / `machine`(.env) 은 서버가 생성, 호출자는 안 넘김 |
| ⚠️ 원칙 | `reason` 빈 값이면 `ValueError`. 이유 없는 데이터 → 엉뚱한 패턴 도출 위험 |

### 3. `namu_search` — 패턴 검색 (판단 중 분석적 조회)
누적된 기록에서 패턴/유사 사례를 찾는다 (자가발전 기반). "정확한 것만 + 요약"이 핵심.

| 항목 | 내용 |
|------|------|
| 입력 | `query`(str): 검색어 / `outcome_filter`(str, 선택): 성공/실패만 / `limit`(int) |
| 출력 | 매칭 항목 + **경향 요약**(`{success: N, failure: M, partial: K}`) |
| 동작 | query 3자+ → FTS5 MATCH + bm25 정렬 / 2자 이하 → `LIKE` 폴백. 매칭 없으면 빈 결과(폴백 없음) |

---

## 🗂️ 데이터 흐름

```
[작업 중인 AI]
   │  recall ───→ 과거 맥락 받아 작업 시작
   │  record ───→ 결과+이유 저장
   ▼
[MCP 메모리 서버] ──→ learnings.yaml (append-only, git 동기화 = 진짜 기억)
                 └─→ SQLite (로컬 캐시, 빠른 검색/패턴, gitignore)
```

- **learnings.yaml** = source of truth, git으로 PC간 공유
- **SQLite** = learnings.yaml를 인덱싱한 로컬 캐시. git pull 후 자동 재생성

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

## 🗃️ learnings 스키마 (확정)

```
{
  id,           # ULID — 시간순 정렬되는 유니크 ID (다중 PC 머지 충돌 방지)
  timestamp,    # ISO 8601 UTC (PC별 타임존 차이로 정렬 꼬임 방지)
  task,         # str — 무슨 작업
  task_type,    # code/doc/analysis/other (권장값, free-form 허용)
  outcome,      # success/failure/partial (enum 고정)
  reason,       # str, 필수 — 왜 그렇게 판단했나 (자가학습의 심장)
  machine,      # samsung/hp/home — .env의 NAMU_MACHINE에서 주입 (자동감지 X)
  verified_by,  # human/ai/unverified — Human-in/on-the-loop 전환의 핵심 구분자
  tags          # JSON 배열 문자열 '["mcp","sqlite"]'
}
```

**설계 결정 근거:**
- `id` = **ULID**. auto-increment 정수는 오프라인 PC들이 같은 번호를 만들어 git 머지 충돌 → ULID로 회피
- `machine` = ID에 박지 않고 **독립 컬럼**. ID는 ULID로 깔끔히, 머신 통계는 `GROUP BY machine`으로. `.env`(이미 gitignore)에 PC별 `NAMU_MACHINE` 값 한 번만 설정
- `verified_by` = append-only라 나중에 백필 불가 → 처음부터 기록. "사람이 검증한 성공 사례만" 뽑아 판단 기준 도출하려면 필수
- `tags` = JSON 문자열 1컬럼. 정규화(별도 테이블)보다 가벼움. trigram FTS가 JSON 내부 태그까지 검색해줌. 정밀 필터 필요 시 `json_each()`로 확장. ⚠️ `json.dumps(tags, ensure_ascii=False)` — 한글 이스케이프 방지

---

## 🗄️ SQLite 테이블 설계 (확정)

> 핵심: 메인 테이블에만 INSERT, FTS는 트리거로 자동 동기화. append-only라 구조 단순.

```sql
-- 메인 구조화 저장소
CREATE TABLE learnings (
    id          TEXT PRIMARY KEY,        -- ULID (TEXT PK라 내부 rowid 별도 존재 → FTS 연결용)
    timestamp   TEXT NOT NULL,           -- ISO 8601 UTC
    task        TEXT NOT NULL,
    task_type   TEXT,                    -- code/doc/analysis/other
    outcome     TEXT NOT NULL CHECK(outcome IN ('success','failure','partial')),
    reason      TEXT NOT NULL,           -- 심장
    machine     TEXT,                    -- samsung/hp/home (.env 주입)
    verified_by TEXT CHECK(verified_by IN ('human','ai','unverified')),
    tags        TEXT                     -- JSON 배열 문자열
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

**한글 전문검색 — trigram 채택 (검증 완료):**
- 기본 `unicode61` 토크나이저는 공백 구분 어절만 매칭 → 한글 부분검색 불가
- `trigram`(SQLite 3.34.0+ 내장)은 3바이트 시퀀스로 CJK 부분검색 네이티브 지원
- ⚠️ **함정:** trigram은 최소 3글자(CJK 9바이트) 필요 → 한글 2글자 검색어("버그","검색" 등) 인덱스 미적용
- → **대응:** `namu_search`에서 **2글자 이하는 `LIKE '%..%'` 폴백**으로 처리
- 외부확장 `better-trigram`(2글자/CJK 개선)은 `.so` 컴파일 필요 → 다중 PC 배포 부담으로 보류. 내장 trigram + LIKE 폴백이 "어디서나 가볍게" 원칙에 부합
- ⚠️ 배포 전 확인: 두 PC 모두 `sqlite3.sqlite_version` ≥ 3.34 & FTS5 활성 (Python 3.12면 거의 충족하나 실측 권장)

**도구별 쿼리 매핑:**

| 도구 | 쿼리 방식 |
|------|-----------|
| `namu_record` | `learnings`에 INSERT (트리거가 FTS 채움) + learnings.yaml에 append |
| `namu_recall` | `SELECT … ORDER BY id DESC LIMIT ?` (+ task_type 필터). ULID 정렬로 최신순 공짜 |
| `namu_search` | `learnings_fts MATCH ?` → `learnings` 조인, `ORDER BY bm25()`. 2글자 이하 `LIKE` 폴백. `GROUP BY outcome COUNT(*)`로 성공/실패 경향 요약 |

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

- **id/timestamp/machine** = record 호출 시 서버가 자동 생성 (호출자 안 넘김)
- **reason** = 한 줄이면 평문, 여러 줄이면 `|` 블록 스칼라로 자동 처리됨
- **tags** = YAML 리스트. 한글 태그도 이스케이프 없이 저장됨 (`allow_unicode=True`)
- **outcome** = success/failure/partial 중 하나만 (CHECK 제약)
- ⚠️ 빈 문서(None)는 rebuild 시 필터링 (파일 끝 trailing `---` 대비)

---

## ✅ 진행 체크리스트

1. [x] Python MCP SDK 최신 버전·설치법 확인 → `mcp[cli]>=1.28,<2`, FastMCP 사용 (2026-06-24)
2. [x] learnings 항목 스키마 확정 → ULID + machine + verified_by 추가 (2026-06-24)
3. [x] SQLite 테이블 설계 (FTS 포함) → trigram + LIKE 폴백, INSERT 트리거 동기화 (2026-06-24)
4. 🔶 `db.py` 구현
   - [x] 쓰기 계열: `init_db` / `record`(yaml-first, reason 필수) / `rebuild_from_yaml` — 검증 완료, 커밋 `08afc69` (2026-06-24)
   - [x] 읽기 계열: `recall`(맥락 로딩+폴백) / `search`(FTS+LIKE 폴백+경향 요약) — 검증 완료, 커밋 `d191a7d` (2026-06-24)
5. [ ] `mcp_server.py` — FastMCP로 도구 3개 노출 + stdio
6. [ ] MCP Inspector 테스트 → Claude Code에 stdio 서버 등록
7. [ ] git pull 후 SQLite 자동 재생성 배선

**환경 확인 완료:** HP `sqlite3` 3.45.1 + FTS5/trigram OK / `python-ulid`,`PyYAML` 설치됨 / `.env`에 `NAMU_MACHINE=hp`
**다음 PC(삼성) 설정 시:** `.env`에 `NAMU_MACHINE=samsung`

---

## 💭 열린 질문 (나중에 논의)

- recall을 SessionStart 훅에서 자동 호출할지, AI가 필요할 때 부르게 할지
- record를 Stop 훅에서 자동 기록할지, AI가 명시적으로 부르게 할지 (자동 = 누락 없음 / 수동 = 노이즈 적음)
- 패턴 분석을 SQLite 쿼리로 할지, 별도 분석 단계를 둘지
