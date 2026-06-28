# NAMU #16 — "세션 브리핑"(`/namu`) 구현 지시서 (v3 · 즉시 구현용)

> 📅 2026-06-28 · 설계 대화창(Opus) → **수행: HP Claude Code(Sonnet)**
> v2 **폐기·대체.** 변경 이유: `/namu`의 "어느 task가 최신이냐" 선정은 **시각**에 전적으로 의존하는데, 현재 `log.md`는 **날짜(YYYY-MM-DD)뿐**이라 같은 날 멀티 PC 작업을 못 가린다. 토대(시각 정밀도)를 먼저 세우지 않고 `/namu`를 얹으면 다음 작업 때 `/namu` 선정 로직을 다시 열어야 한다. → **순서를 바로잡음: PHASE 1(타임스탬프 초단위) → PHASE 2(`/namu`).**
> **새 설계 결정이 필요하면 멈추고 보고.**

---

## ✅ 실제 구현 결과 · 정정 (2026-06-28 라이브 완료 후 추가)

> 아래 본문은 **구현 전 지시서 원본**이다(보존). 실제로 해보며 달랐던 점을 여기 위에 남긴다 — "지시 → 실제" 차이가 다음 작업의 학습거리다.

**결과: 양쪽 1:1 라이브 통과. 커밋·푸시 완료.** Claude Code `/namu` = agy `/namu` 동일 형식(📌 task · 🕘 log 꼬리[옛 날짜-only + 새 초단위 공존] · ▶ 머신 라벨 · 💡 `namu_recall` 교훈). PHASE 1 초단위(`07:35:51`) 실물 확인.

**본문과 달랐던 점 (정정):**
1. **🔴 agy 스킬 경로 = 폴더 형태 전용.** 본문 §4는 `.agents/skills/namu.md`(플랫) 또는 폴더 둘 다 되는 듯 적었으나, **agy 바이너리 실측 결과 `{workspace}/.agents/skills/<name>/SKILL.md`(폴더+SKILL.md)만 인식.** 플랫 `.agents/skills/namu.md`는 `/namu → No matches`. → **최종 위치 = `.agents/skills/namu/SKILL.md`.** (Claude Code는 본문대로 `.claude/commands/namu.md` 플랫 파일로 정상.)
2. **🟠 `.agents/`가 통째로 gitignore됨 → 정책 수정 필요했음.** 본문엔 없던 단계. `.agents/`를 통으로 막던 `.gitignore`를, **PC별 파일만 콕 집어 막도록**(`.agents/hooks.json`·`.agents/mcp_config.json`·`.agents/hooks/*.log`) 변경해 `.agents/skills/`는 추적 가능으로 열었다. 검증 = `git check-ignore .agents/skills/namu/SKILL.md` 빈 출력.
3. **🟡 `/namu-task` 슬래시 직접 호출 불가.** PHASE 1 검증을 `/namu-task` 재진입으로 하려 했으나 `Unknown command: /namu-task`. → log 줄을 **자연어로 직접 append**해 초단위 형식·옛 줄 공존을 검증(우회 성공).
4. **🟢 STEP 0 "예상"이 전부 "확정"으로.** §1의 항목들(namu_recall=교훈만 / log 형식 / .claude/commands 부재 / check-ignore 비-0=정상 / 더미 존재)은 모두 실측 통과. SKILL.md 템플릿의 "적힌 형식"과 "실제 찍히는 형식"이 따로 놀던 것도 발견해 v3 목표 형식으로 통일.

**최종 커밋 파일(1커밋):** `namu-plugin/skills/namu-task/SKILL.md` · `.claude/commands/namu.md` · `.agents/skills/namu/SKILL.md` · `.gitignore` · `tasks/namu-16-live-verify/log.md`. (`mcp_server.py`는 더미 제거 후 HEAD 동일 → 미커밋.)

---

## 0. 작업 규칙

- 너(Claude Code)는 **파일 작성 + diff 제시까지만.** 커밋·푸시는 사용자 직접. **자율 커밋 금지.**
- 시작 전 `git pull`. 권한 "Yes, this time only".
- 막히면 멈추고 **간결 보고 + 로그/스크린샷** 요청. 추측 금지.
- `/namu` 두 마크다운엔 **절대경로·머신 고유값 금지**(데이터는 `tasks/` 글롭·`namu_recall`로만).
- **`session_context.py` / `session_recall.py` / `task_resolve.py`(auto-inject·statusLine 경로)는 건드리지 말 것.** 이번 작업은 그 경로와 독립.

---

## 1. 이미 확정된 사실 (STEP 0 일부 — 재실측 불필요)

이번 세션 HP 관측으로 닫힌 것들:

- ✅ `namu_recall` = **교훈(learnings)만** 반환(task 정보 없음). → `/namu`의 task 부분은 `tasks/` 파일에서 직접 읽어야 함.
- ✅ `log.md` 실제 한 줄 형식 = **`[TAG] YYYY-MM-DD <머신> · 내용`** (TAG 먼저, 그 뒤 날짜, 그 옆 공백으로 머신 도장, ` · ` 뒤 내용). **현재 시:분:초 없음, 날짜뿐.**
- ✅ `.claude/commands/` 디렉터리 **현재 없음**(작성 시 `mkdir -p`).
- ✅ `git check-ignore .claude/commands/namu.md` → 비-0 종료(= **ignore 안 됨 = 추적 가능, 정상**). Claude Code가 "거부"로 표시하지만 그게 정상 결과.
- ✅ `namu_brief_test` 더미(`@mcp.prompt`, 미커밋)가 **HP에 실제 존재**(`/` 목록에 `/plugin:namu:namu-memory:namu_brief_test (MCP)` 노출 확인). → 제거 대상 확정.
- ✅ 활성 task = `namu-16-live-verify`, `context.hp.md`만 존재(samsung 없음), `log.md`에 `[시작]` 줄 있음.

---

## 2. STEP -1 — 더미 제거 (먼저)

- `namu-plugin/mcp_server.py`의 **`namu_brief_test`(`@mcp.prompt` 함수) 제거.**
- `git diff`로 그 함수만 빠졌는지 확인 후 보고. (커밋은 사용자.)

---

## 3. PHASE 1 — 토대: `log.md` 타임스탬프를 **초단위**로 (먼저 단단히)

> 멀티 PC에서 "최신"을 가르는 신호가 시각뿐이므로, **초(`%S`)까지** 박아 같은-분/같은-초 모호성을 원천 차단한다(사용자 확정).

### 3-1. 바꿀 곳 찾기
- `namu-plugin/skills/namu-task/SKILL.md`에서 **log 줄을 기록(append)할 때 타임스탬프를 만드는 지시**를 찾는다(현재 `date +"%Y-%m-%d"` 또는 그에 준하는 날짜-only 생성으로 추정 — **실제 문구를 직접 확인**할 것).
- 동시에 `grep -rn "%Y-%m-%d\|date +\|strftime" namu-plugin/` 로 **log 타임스탬프를 만들거나 파싱하는 다른 코드가 있는지** 점검. 있으면 보고. (statusLine `task_resolve.py`는 context mtime 기반이라 무관할 것으로 예상하나 **실측 확인**.)

### 3-2. 변경
- 타임스탬프 생성 포맷을 **`%Y-%m-%d %H:%M:%S`** 로 변경.
- 결과 줄 형식: **`[TAG] YYYY-MM-DD HH:MM:SS <머신> · 내용`** (머신 도장·` · ` 구분자 위치는 그대로 유지, 날짜와 머신 사이에 시:분:초만 추가).
- ⚠️ **과거 줄은 손대지 말 것**(append-only). 옛 날짜-only 줄은 그대로 둔다. (PHASE 2 파서가 폴백 처리.)

### 3-3. 검증
1. `date +"%Y-%m-%d %H:%M:%S"` 실행 → `2026-06-28 21:05:33` 같은 형식 눈으로 확인.
2. SKILL.md 변경 diff 제시 → 사용자 검토.
3. (선택·권장) `/namu-task namu-16-live-verify` 재진입해 이 변경 자체를 기록하는 `[결정]` 줄 하나를 스킬이 append하게 하고, 그 줄이 **`[결정] 2026-06-28 HH:MM:SS hp · …`** 로 초까지 박히는지 실물 확인. (append-only라 안전·정당한 기록.)
4. 통과·diff 보고 후 PHASE 2로. (커밋은 PHASE 2까지 끝내고 사용자가 한 번에.)

---

## 4. PHASE 2 — `/namu` 두 파일

| # | 엔진 | 위치(repo 루트) | 호출 |
|---|------|-----------------|------|
| A | Claude Code | `.claude/commands/namu.md` | `/namu` |
| B | agy | `.agents/skills/namu.md` | `/namu` |

본문 동일, 프론트매터(봉투)만 엔진별. **읽기 전용**(파일 수정·생성 금지).

### 설계 원칙 (v2에서 유지 — context 살림)
- **context 유지.** 핸드오프 후 "현재 상태"는 *마지막 작업 머신*의 context일 수 있으므로, 머신별 `## ▶ 다음`을 **라벨 달아 함께** 표시.
- **진행이력 = `log.md` 꼬리**(양쪽 PC가 다 쌓임).
- **선정(어느 task) = task 중심**, `log.md` 마지막 줄의 **시각(초단위)** 비교. 파일 mtime 금지(git pull이 망가뜨림).

### 공통 동작 (모델이 하는 일)
1. **활성 task 선정:** `tasks/*/log.md` 각 파일의 **마지막 줄에서 일시**를 파싱한다.
   - 새 형식 `[TAG] YYYY-MM-DD HH:MM:SS …` → 날짜+시:분:초로 비교.
   - **폴백:** 옛 형식 `[TAG] YYYY-MM-DD <머신> …`(시각 없음) → 시각을 `00:00:00`으로 간주.
   - 그 task의 `context.*.md` `## ▶ 다음`이 **전부 `(완료)`면 제외.**
   - 남은 것 중 **일시가 가장 최근**인 폴더 = 활성. 없으면 "진행 중 task 없음".
   - ⚠️ 파일 mtime 절대 사용 금지. 반드시 log 줄 안의 일시.
2. **보여주기(선정 task 폴더):**
   - `task.md` → 제목/목적 1줄.
   - `log.md` 마지막 **3~5줄** = 최근 이력.
   - 각 `context.<machine>.md`의 `## ▶ 다음` 본문을 **머신 라벨 달아** 나열(`(완료)`는 생략). 핸드오프 후 다른 PC 라벨이 최신일 수 있음 — 정상.
3. **교훈:** `namu_recall` `limit=5` 호출.
4. 활성 task 없으면 "📌 진행 중 task 없음" + 교훈만.
5. **아래 형식 외 잡담 금지.**

### 출력 형식 (공통)
```
🌳 NAMU 세션 브리핑
📌 진행 중: <slug> · <task.md 제목>
🕘 최근 이력 (log.md):
   <마지막 3~5줄>
▶ 다음:
   · (hp) <context.hp.md의 ## ▶ 다음 본문>
   · (samsung) <context.samsung.md의 ## ▶ 다음 본문>
💡 최근 교훈:
   - <[outcome] task — reason>
상세가 필요하면 "recall로 상세 보여줘"라고 하세요.
```

---

### A. `.claude/commands/namu.md` (Claude Code)

```markdown
---
description: NAMU 세션 브리핑 — 진행 중 task의 진행이력·다음 할 일·최근 교훈을 보여준다
---
NAMU "세션 브리핑"을 출력한다. 아래 순서대로 수행하고 마지막에 정해진 형식으로만 보여줘라. 파일을 수정·생성하지 말 것(읽기 전용).

1. 활성 task 선정 (task 중심):
   - 작업 루트의 `tasks/*/log.md`를 모두 본다. 각 파일 **마지막 줄에서 일시**를 읽는다.
     · 형식 `[TAG] YYYY-MM-DD HH:MM:SS <머신> · 내용` → 날짜+시:분:초로 비교.
     · 시각이 없는 옛 줄 `[TAG] YYYY-MM-DD <머신> · 내용` → 시각을 00:00:00으로 본다.
   - ⚠️ 파일 수정시각(mtime) 쓰지 마라. 반드시 log 줄 안의 일시로 비교.
   - 그 task의 `context.*.md`의 `## ▶ 다음`이 전부 `(완료)`면 제외.
   - 남은 것 중 일시가 가장 최근인 폴더가 활성 task. 없으면 "진행 중 task 없음".
2. 선정된 task 폴더에서:
   - `task.md` → 제목/목적 1줄.
   - `log.md` → 마지막 3~5줄.
   - 각 `context.<machine>.md` → `## ▶ 다음` 본문(머신 라벨 붙여 나열, `(완료)` 생략).
3. `namu_recall`을 `limit=5`로 호출해 최근 교훈을 받는다.
4. 아래 형식으로만 출력(이 외 잡담 금지):

   🌳 NAMU 세션 브리핑
   📌 진행 중: <slug> · <제목>
   🕘 최근 이력 (log.md):
      <마지막 3~5줄>
   ▶ 다음:
      · (<machine>) <그 머신 context의 ▶ 다음 본문>
   💡 최근 교훈:
      - <[outcome] task — reason>
   상세가 필요하면 "recall로 상세 보여줘"라고 하세요.
```

> 메모(CC): 본문은 `/namu` 입력 시 모델에 전달되는 프롬프트. `namu_recall` 권한은 그때 "Yes, this time only"(allowed-tools로 미리 안 엶).

---

### B. `.agents/skills/namu.md` (agy)

```markdown
---
name: namu
description: NAMU 세션 브리핑. 사용자가 /namu를 부를 때만 사용한다. 진행 중 task의 진행이력·다음 할 일·최근 교훈을 정해진 형식으로 보여준다.
---
NAMU "세션 브리핑"을 출력한다. 아래 순서대로 수행하고 마지막에 정해진 형식으로만 보여줘라. 파일을 수정·생성하지 말 것(읽기 전용).

1. 활성 task 선정 (task 중심):
   - 작업 루트의 `tasks/*/log.md`를 모두 본다. 각 파일 **마지막 줄에서 일시**를 읽는다.
     · 형식 `[TAG] YYYY-MM-DD HH:MM:SS <머신> · 내용` → 날짜+시:분:초로 비교.
     · 시각 없는 옛 줄 → 00:00:00으로 본다.
   - ⚠️ 파일 mtime 쓰지 마라. log 줄 안의 일시로 비교.
   - 그 task의 `context.*.md`의 `## ▶ 다음`이 전부 `(완료)`면 제외.
   - 남은 것 중 일시 가장 최근인 폴더가 활성 task. 없으면 "진행 중 task 없음".
2. 선정된 task 폴더에서:
   - `task.md` → 제목/목적 1줄.
   - `log.md` → 마지막 3~5줄.
   - 각 `context.<machine>.md` → `## ▶ 다음` 본문(머신 라벨 붙여 나열, `(완료)` 생략).
3. `namu_recall`을 `limit=5`로 호출해 최근 교훈을 받는다.
4. 아래 형식으로만 출력(이 외 잡담 금지):

   🌳 NAMU 세션 브리핑
   📌 진행 중: <slug> · <제목>
   🕘 최근 이력 (log.md):
      <마지막 3~5줄>
   ▶ 다음:
      · (<machine>) <그 머신 context의 ▶ 다음 본문>
   💡 최근 교훈:
      - <[outcome] task — reason>
   상세가 필요하면 "recall로 상세 보여줘"라고 하세요.
```

> 메모(agy): `description`이 자동 트리거도 겸하므로 "**/namu를 부를 때만**" 명시. agy엔 CC의 `!`bash·`$ARGUMENTS` 인라인 확장이 **없으니** 위처럼 지시문으로만 동작하게 쓴다.

---

## 5. 참고: 확정 포맷

- `log.md` 한 줄(변경 후): `[TAG] YYYY-MM-DD HH:MM:SS <머신> · 내용`. 태그 5종 `[시작][결정][분담][막힘][완료]` + 필요시 추가. **append-only**, 옛 날짜-only 줄 공존.
- `context.<machine>.md`: 첫 줄 `## ▶ 다음`, 완료 시 `(완료)`. 현재 스냅샷만(~1500자).
- `namu_recall`: `limit=5`면 최신 교훈 N개(교훈만).

---

## 6. 라이브 검증 — ⭐ 핸드오프 + 초단위 둘 다

1. **Claude Code(HP):** 새 세션 → `/namu` → 형식대로, 📌 task·🕘 양쪽 이력·▶ 머신 라벨·💡 교훈. `namu_recall` 호출 권한 승인.
2. **agy(HP):** 새 세션 → `/namu` → 같은 task·이력·교훈, 같은 형식.
3. **초단위·핸드오프 미니 테스트:** 한 task의 `log.md`에 **다른 머신 도장 + 새 초단위 일시**로 한 줄을 (직접 또는 삼성→push→HP pull로) 추가 → `/namu` → 그 task가 활성으로 잡히고 이력에 보이는가? **mtime 아닌 log 일시로, 초까지 구분해 골랐는지** 여기서 드러난다. 옛 날짜-only 줄과 섞여도 폴백이 동작하는지도 확인.
4. 양쪽 **스크린샷 2장** 1:1 대조 보고.
5. ⚠️ 깨지면 멈추고 ① `namu_recall` 실제 반환 ② `tasks/*/log.md` 마지막 줄들 ③ 어느 task를 왜 골랐는지 출력 보고. (추측 수정 금지.)

---

## 7. 끝나고 (사용자 영역)

- 커밋 대상: `namu-plugin/skills/namu-task/SKILL.md`(PHASE 1) + `.claude/commands/namu.md` + `.agents/skills/namu.md` + `mcp_server.py`(더미 제거).
- 커밋 메시지 예시(영문 conventional, 2개로 나눠도 좋음):
  - `feat(namu-task): log timestamps to second precision`
  - `feat(namu): add read-only /namu session briefing for both engines`
- 푸시·커밋은 **사용자 직접**.

---

## 8. 이후 (이번 범위 아님)

- 🔜 `/namu` 선정 로직을 작은 stdlib 헬퍼로 굳히기(지금은 모델이 log 일시 비교).
- 🔜 statusLine(`find_active_task`, 머신 중심) ↔ `/namu`(task 중심) 선정 통합 여부 결정.
- 🔜 잔재 청소(구식 DEBUG·smoke·`agy_*.log`) · agy 플러그인 승격.

---

### 한 줄 요약
**순서 교정:** PHASE 1 토대 먼저 — `/namu-task` log 타임스탬프를 **`%Y-%m-%d %H:%M:%S`(초단위)**로(멀티 PC 최신 판별의 유일 신호라 토대 먼저). 그 위에 PHASE 2 — **읽기 전용 `/namu`**(context 유지·머신 라벨 / 이력=log 꼬리 / 선정=log 일시 초단위, 옛 날짜-only 폴백 / `namu_recall` 교훈). `session_context.py` 등 auto-inject 경로는 불가침. STEP -1 더미 제거 → PHASE 1 → PHASE 2 → 핸드오프·초단위 라이브 대조.
