---
description: statusLine(화면 하단 한 줄) 원클릭 셋업. /namu:statusline-setup으로 명시 호출하거나 사용자가 statusLine이 안 보인다고 할 때 사용.
---

# NAMU statusLine 셋업

이 스킬의 base directory 기준 `../../scripts/namu_setup_statusline.py`가 셋업 스크립트다
(표준 라이브러리만 사용, plain python으로 실행 가능).

Claude Code와 agy(Antigravity CLI)를 모두 지원한다(#39) — 스크립트가 두 호스트의 등록부를
자동으로 훑어 **설치가 감지된 호스트만** 셋업한다(둘 다 설치돼 있으면 둘 다, 한쪽만
설치돼 있으면 그쪽만). 호출 측에서 호스트를 지정할 필요는 없다.

## 실행

OS에 맞는 인터프리터로 그대로 실행한다(추가 인자 없이 먼저 시도):

- Windows: `python -X utf8 <base directory>/../../scripts/namu_setup_statusline.py`
- 그 외(macOS/Linux): `python3 <base directory>/../../scripts/namu_setup_statusline.py`

## 결과 처리

출력은 감지된 호스트마다 `[claude]`/`[agy]` 라벨을 붙여 한 줄씩 나온다. 여러 호스트가
동시에 처리된 경우 아래 판단을 호스트별로 각각 적용한다.

- **성공(exit 0)** — 출력된 안내(신규 설정/자동 갱신/변경 없음)를 그대로 사용자에게
  보여주고, 변경이 실제로 일어난 호스트에 한해 **재시작해야 반영됨**을 안내한다(문구는
  스크립트가 "Claude Code를 재시작하면 반영됩니다." / "agy를 재시작하면 반영됩니다." /
  "Claude Code/agy를 재시작하면 반영됩니다."처럼 대상 호스트에 맞춰 출력한다).
- **양쪽 다 미설치 오류(exit≠0, "설치돼 있지 않습니다")** — 출력된 안내를 그대로 보여주고
  멈춘다. 재실행 전에 플러그인 설치부터 안내한다(Claude Code 또는 agy 중 하나는 설치돼
  있어야 한다).
- **타 statusLine 감지로 거부(exit≠0, "이미 다른 statusLine 설정이 있습니다")** — 어느
  호스트에서 거부됐는지(`[claude]`/`[agy]` 라벨) 확인하고, 출력에 포함된 기존 설정 내용을
  사용자에게 그대로 보여주고 NAMU statusLine으로 교체할지 물어본다. 사용자가 승인한
  경우에만 `--force` 옵션을 붙여 재실행한다(`--force`는 감지된 모든 호스트에 동일하게
  적용된다 — 거부된 호스트만 골라 교체하는 옵션은 없음):
  - Windows: `python -X utf8 <경로> --force`
  - 그 외: `python3 <경로> --force`

  승인 없이 `--force`를 먼저 시도하지 않는다.

update(플러그인 버전 갱신) 후 statusLine 표시가 조용히 사라진 경우에도 이 스킬을 그대로
재실행하면 새 버전 경로로 다시 연결된다.
