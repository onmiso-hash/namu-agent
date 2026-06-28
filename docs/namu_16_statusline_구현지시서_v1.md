# NAMU #16 구현지시서 — statusLine 양쪽(Claude Code · agy) 가시성

📅 2026-06-28 작성 · 설계 창(Opus)에서 HP Claude Code(Sonnet)로 인계
대상 머신: HP (WSL Ubuntu, `~/project/namu-agent`)

---

## ⚠️ 먼저 읽을 것 (작업 모드)

- 이건 **구현 작업**이다. 진단 아님.
- 단, **수정·스테이징·커밋·푸시는 절대 하지 마라.** 변경은 diff로만 보여주고, 사용자가 직접 검토 후 커밋한다.
- 작업 시작 전 `git pull`로 시작.
- 권한 요청은 항상 "Yes, this time only"로 처리되니, 그에 맞게 동작.
- 검증 안 된 코드는 라이브 통과 후에만 커밋 대상. 지금은 전부 미커밋 상태로 둔다.
- 막히면 가설을 쌓지 말고, 관측 지점(print)을 넣어 실제 값을 본 뒤 보고.

---

## 0. 한 줄 목표

Claude Code와 agy **양쪽** 모두, 터미널 하단 status line에
`[모델] 폴더 | 📌 진행중-task · 제목 | 컨텍스트%` 형태를 **항상 보이게** 한다.

## 1. 배경 (왜 이 방식인가 — 이미 검증됨)

- #16에서 "📌task가 화면에 안 뜬다"던 진짜 원인은 NAMU 코드 버그가 아니라,
  **Claude Code 2.1.0부터 SessionStart 훅의 `additionalContext`를 화면에 표시하지 않고
  모델 컨텍스트로만 주입하는 사양**이다. (공식 docs + GitHub #9591/#32221 확인)
- 따라서 v12 노트의 "다음 수 1번(print를 직접 stdout)"은 **건너뛴다.**
  → SessionStart는 plain stdout도 화면 억제됨이 확인됨(#15174/#32221). 시도 불필요.
- **statusLine은 SessionStart 훅과 완전히 별개인 화면 전용 기능**이다.
  Claude Code·agy **둘 다** 지원하며, 둘 다 stdin으로 JSON을 주고 stdout 첫 줄을 하단에 렌더한다.
- 두 엔진 모두 stdin JSON에 `cwd` / `workspace.current_dir`를 주므로,
  **task 찾기 스크립트는 하나로 공용** 가능. 등록 설정만 엔진별로 다르다.
- 기존 `additionalContext` 주입 코드는 **그대로 둔다**(모델 컨텍스트엔 유용).
  statusLine은 그 위에 "사람 눈에 보이는 층"만 추가하는 것이다.

> 보너스: statusLine은 settings.json이 가리키는 **경로를 직접 실행**한다(플러그인 캐시 경유 X).
> 즉 예전에 우릴 괴롭힌 "캐시 갱신 2단계" 문제와 무관하게, repo 작업본을 바로 가리키면 된다.

---

## 2. 작업 범위 (3파트)

### 파트 A — 공용 task 해석 함수 (표준 라이브러리 전용)

목표: cwd만 받으면 active task의 `(id, title)`을 돌려주는 **가볍고 의존성 없는** 함수.

1. 먼저 기존 정본 로직 `find_active_task`를 찾아 읽어라
   (v12 기준 `session_recall.py` / `session_context.py` 부근).
2. 판단:
   - **(a)** 그 함수가 속한 모듈이 `dotenv` 등 외부 의존을 **import하지 않으면** → 그대로 import해서 재사용.
   - **(b)** 모듈 상단이 `from dotenv import load_dotenv` 등을 import해서 plain `python3`로 import 시
     `ModuleNotFoundError`가 날 상황이면 → **정본 로직을 표준 라이브러리만 쓰는 별도 모듈로 추출**
     (예: `namu/task_resolve.py`)하고, 기존 훅도 거기서 import하도록 바꿔
     **단일 출처(single source of truth)**를 유지하라.
3. 머신 값은 `os.environ.get("NAMU_MACHINE", "unknown")`에서 읽는다
   (v11에서 `.bashrc`에 export 완료됨 — config.py의 .env 경로 버그 우회).
4. 이 함수는 **DB·네트워크·uv·dotenv를 절대 건드리면 안 된다.** 파일 읽기(`context.<machine>.md`)만.
   (statusLine은 자주 실행되므로 무겁거나 느리면 안 됨.)

> 어느 쪽(a/b)을 택했는지, 그 이유를 보고에 명시할 것.

### 파트 B — statusline 스크립트 (양쪽 공용, repo에 위치)

위치: repo 안 (git 동기화 대상). 예: `scripts/namu_statusline.py`
실행: 플레인 `python3` (외부 의존 0 → uv 불필요, 양 OS 공통).

요구 동작:
- stdin에서 JSON을 읽되, **비어있거나 깨져도 죽지 말 것**(빈 dict로 폴백).
- 아래 필드를 양쪽 엔진 공통 키로 추출(없으면 `?` 폴백):
  - 모델: `model.display_name`
  - 폴더: `basename(workspace.current_dir or cwd)`
  - 컨텍스트%: `context_window.used_percentage` (숫자 아닐 때 `?`, 첫 응답 전 null 가능 주의 → 폴백 필수)
- 파트 A 함수로 active task 조회 → 있으면 `📌 {id} · {title}`, 없으면 `진행 task 없음`.
- **출력은 정확히 한 줄.** (statusLine은 stdout 첫 줄만 사용)
- **전체를 try/except로 감싸 어떤 경우에도 한 줄은 출력**되게 하라(빈 출력 → 바가 비거나 멈춤).

출력 형식(확정):
```
[Sonnet] namu-agent | 📌 namu-16-live-verify · 양쪽 1:1 라이브 검증 | 12%
```
task 없을 때:
```
[Sonnet] namu-agent | 진행 task 없음 | 8%
```

시작점 스켈레톤(조정 가능):
```python
#!/usr/bin/env python3
"""NAMU statusline — Claude Code & agy 공용. 한 줄 출력, 표준 라이브러리만."""
import sys, json, os

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    model = (data.get("model") or {}).get("display_name") or "?"
    ws = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or ""
    folder = os.path.basename(ws.rstrip("/\\")) or "?"
    pct = (data.get("context_window") or {}).get("used_percentage")
    ctx = f"{round(pct)}%" if isinstance(pct, (int, float)) else "?"

    task_part = "진행 task 없음"
    try:
        machine = os.environ.get("NAMU_MACHINE", "unknown")
        # 파트 A 함수 사용: cwd→repo root→active task (id, title)
        t = resolve_active_task(ws, machine)   # 없으면 None
        if t:
            task_part = f"📌 {t[0]} · {t[1]}"
    except Exception:
        pass  # task 못 찾아도 바는 떠야 한다

    print(f"[{model}] {folder} | {task_part} | {ctx}")

if __name__ == "__main__":
    main()
```
> ANSI 색은 선택 사항(예: 📌 부분만 노란색). 넣되 터미널 호환 안전하게, 안 넣어도 무방.

### 파트 C — 양쪽 엔진 등록 (머신-로컬 설정, repo 아님)

스크립트의 **절대경로**를 두 설정 파일에 각각 등록. (상대경로 금지)

**Claude Code** — `~/.claude/settings.json`
```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /home/<user>/project/namu-agent/scripts/namu_statusline.py",
    "padding": 0
  }
}
```

**agy** — `~/.gemini/antigravity-cli/settings.json`
```json
{
  "statusLine": {
    "type": "",
    "command": "python3 /home/<user>/project/namu-agent/scripts/namu_statusline.py",
    "enabled": true
  }
}
```
주의:
- 키는 반드시 `statusLine`(camelCase). `statusline`(소문자)이면 무시됨.
- agy는 `"enabled": true` 필수, `type`은 빈 문자열로 둠.
- 기존 settings.json에 다른 키가 있으면 **덮어쓰지 말고 statusLine 블록만 병합**.
- 실제 사용자 홈 경로로 `<user>` 치환. `echo $HOME`로 확인.

---

## 3. 검증 (구현 후)

각 단계의 성공 기준을 명시해 보고할 것.

1. **단독 테스트** (엔진 없이):
   ```bash
   echo '{"model":{"display_name":"Sonnet"},"workspace":{"current_dir":"/home/x/project/namu-agent"},"context_window":{"used_percentage":12}}' | python3 /절대경로/namu_statusline.py
   ```
   - 성공: `[Sonnet] namu-agent | 📌 namu-16-live-verify · ... | 12%` 한 줄 출력.
   - 실패 시: 출력이 비면 파트 A import/경로 문제 → 그 자리에서 print로 machine·repo·task 값 관측.
2. **Claude Code 라이브**: 새 세션 시작 → 하단 status line에 위 한 줄이 뜨는지 관측(스크린샷).
   - 안 뜨면: `~/.claude/settings.json` 트러스트 수락 여부, 경로, `chmod +x` 불필요(python3 직접 실행이라).
3. **agy 라이브**: agy 재시작(설정 메모리 캐시 때문에 완전 종료 후 재실행) → 하단 status line 관측(스크린샷).
   - 안 뜨면: `/statusline`로 상태, settings.json 경로·`enabled:true`·camelCase 확인.
4. 양쪽 출력이 **동일 형식·동일 task**를 가리키는지 1:1 대조.

---

## 4. 보고 형식

- 변경 파일별 diff (커밋 금지, diff만).
- 파트 A에서 (a)재사용 / (b)추출 중 무엇을 택했고 왜인지.
- 위 검증 1~4의 결과 스크린샷(특히 2·3의 하단 바).
- 막힌 지점이 있으면 관측한 실제 값과 함께.

## 5. 손대지 말 것

- 기존 `additionalContext` 주입 코드 (그대로 유지).
- `plan.md` (이 설계 창에서만 갱신).
- 커밋·푸시 (사용자 담당).
- task 해석 함수에 DB/네트워크/uv/dotenv 끌어들이기 (속도·이식성 깨짐).
