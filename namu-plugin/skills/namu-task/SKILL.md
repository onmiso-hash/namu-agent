---
description: 멀티스텝 구현 작업을 오케스트레이션한다. /namu-task로 명시 호출하거나 여러 단계가 필요한 코딩 작업일 때 사용. recall→분할→코딩→검수→사용자 게이트→record 순서.
---

# NAMU 작업 오케스트레이션

**machine 이름** — `config.py`의 `NAMU_MACHINE` (`.env`에서 주입). 없으면 `unknown`.

**작업 루트** — `${NAMU_HOME:-.}/tasks/` (NAMU_HOME 환경변수가 설정된 경우 그 경로, 미설정 시 현재 디렉토리 기준).

---

## 진입 분기

`/namu-task <slug>` 호출 시 `${NAMU_HOME:-.}/tasks/<slug>/` 존재 여부로 경로가 갈린다.

---

## 신규 경로 (tasks/\<slug\>/ 없음)

**1. 폴더 + 3파일 생성**

사용자에게 목적(왜 하는가)·완료조건을 물어본다. 답을 받으면:

- `${NAMU_HOME:-.}/tasks/<slug>/task.md` — 아래 템플릿대로 작성 → 사용자 확인 후 확정
- `${NAMU_HOME:-.}/tasks/<slug>/context.<machine>.md` — 아래 템플릿으로 초기화
- `${NAMU_HOME:-.}/tasks/<slug>/log.md` — 아래 템플릿으로 초기화

**2. log `[시작]` 줄 append**

```
[시작] YYYY-MM-DD HH:MM:SS <machine> · 작업 생성, 목적·완료조건 확정
```

**3. recall** — `namu_recall`로 관련 과거 교훈 조회. 신규는 항상 실행.

**4. 작업 분할** — 코딩 워커에게 넘길 단위로 쪼갠다.

**5. 워커 명단 확인** — `${NAMU_HOME:-.}/namu_workers.yaml`을 읽는다. **파일이 없으면 engine=`native`로 간주하고 그대로 진행한다** (설치형 기본값 — 기본 워커는 현재 엔진의 네이티브 서브에이전트, 별도 설정 불필요). engine이 `native`면 지금 실행 중인 엔진의 서브에이전트 호출 도구를 쓴다:

- Claude Code: `Agent` 도구. `subagent_type`은 **호출명 폴백 규칙**을 따른다 — 사용 가능한 에이전트 목록에 명단의 `agent` 값(예: `namu-coder`)이 있으면 그대로 쓰고, 없으면 플러그인 네임스페이스 이름 `namu:<agent>`(예: `namu:namu-coder`)를 쓴다. (개발 repo에선 프로젝트 `.claude/agents/`의 비네임스페이스 이름이 우선 존재하고, 설치형에선 플러그인 동봉 정의라 `namu:` 접두사가 강제로 붙기 때문)
- agy(Antigravity): `invoke_subagent` (`TypeName` = 명단의 `agent` 값 그대로 — agy는 네임스페이스를 붙이지 않는다. 정의는 워크스페이스 `.agents/agents/<agent>/agent.md` 또는 플러그인 설치본 `agents/<agent>/agent.md`에서 자동 로드). 비동기이므로 서브에이전트의 `send_message` 수신까지 대기 후 다음 단계로.

engine이 `native`가 아니면 사용자에게 알리고 멈춘다.

**6. 코딩 위임** — namu-coder 서브에이전트에게 구현을 맡긴다.

**7. 검수 위임** — namu-reviewer 서브에이전트에게 검사를 맡긴다. pass/fail + 판정 이유 반환.

**8. 검수 게이트** (자동 재실행 금지)

fail이면 멈추고 사용자에게 보여준다:
- 검수 워커 판정 이유
- 선택: ① 재실행(횟수 입력) / ② 통과 처리 / ③ 중단
- 재실행이면 입력한 N회까지 6~7단계 반복, N회 소진 시 다시 게이트로.

> **중간 상태 저장** — 검수 게이트 통과 직후, 또는 작업을 끊을 때마다:
> - `context.<machine>.md` 덮어쓰기 ("▶ 다음" 갱신)
> - 결정·분담·막힘 발생 시 `log.md` append

**9. 기록 및 마무리**

- `namu_record`로 결과·판단 이유 저장. 사용자가 게이트를 통과시킨 경우 `verified_by: human`.
- `log.md`에 `[완료]` 또는 `[중단]` 줄 append.
- 완료조건이 모두 체크됐으면 `context.<machine>.md`의 "▶ 다음"을 `(완료)`로 갱신. 폴더는 그대로 둔다.

---

## 재진입 경로 (tasks/\<slug\>/ 있음)

**0. 다른 PC 흔적 확인 (안전장치)**

`${NAMU_HOME:-.}/tasks/<slug>/` 안에 `context.<other-machine>.md` (현재 machine이 아닌 파일)나 `log.md` 꼬리가
현재 `context.<machine>.md`보다 더 최신 타임스탬프로 보이면:
> "다른 PC 작업 흔적 있음 — git pull 했는지 확인하라" 안내 후 **멈춤**.

**1. 상태 복원**

- `${NAMU_HOME:-.}/tasks/<slug>/task.md` → 목적·완료조건 복원
- `${NAMU_HOME:-.}/tasks/<slug>/context.<machine>.md` → "▶ 다음"부터 읽기 (재진입 지점)
- `${NAMU_HOME:-.}/tasks/<slug>/log.md` 꼬리(최근 10줄) → 최근 흐름 파악

**2. recall (선택)**

맥락이 파일로 복원됐으므로 생략 가능. 진짜 막혔을 때만 `namu_recall` 호출.
(recall = 과거 교훈, context 복원 = 현재 상태. 별개 관심사다.)

**3. 이어가기**

"▶ 다음"이 가리키는 지점부터 신규 경로의 4~9단계를 이어간다.

---

## 파일 템플릿

### task.md (거의 안 바뀜 — 목적/완료조건)

```markdown
# <slug> — <한 줄 제목>
📅 생성 <YYYY-MM-DD> [<machine>] · 🔗 관련: __

## 목적
(왜 하는가 — 1~2줄)

## 완료조건
- [ ] ...

## 범위 밖 (선택)
- ...
```

### context.\<machine\>.md (덮어쓰기, ~한글 1500자)

```markdown
# context @ <machine> — <slug>
> 🔄 갱신 <YYYY-MM-DD HH:MM> [<machine>]

## ▶ 다음 (한 줄)
(재진입 시 여기부터)

## 지금 어디까지
- (사실만)

## 막힘·주의 (있으면)
- ...

## 만지는 중인 파일
- `path` — (왜)
```

### log.md (append만, 줄마다 machine 도장)

```markdown
# log — <slug>
(append만. context 꼬이면 이걸로 복원)

[시작] YYYY-MM-DD HH:MM:SS <machine> · 작업 생성, 목적·완료조건 확정
```

log 줄 형식: `[TAG] YYYY-MM-DD HH:MM:SS <machine> · 내용` (초단위 필수 — 멀티 PC "최신" 판별 신호).
log 태그 고정 5종: `[시작]` `[결정]` `[분담]` `[막힘]` `[완료]`. 필요하면 추가 허용.
옛 날짜-only 줄(`[TAG] YYYY-MM-DD <machine> · 내용`)은 그대로 두고 공존.
