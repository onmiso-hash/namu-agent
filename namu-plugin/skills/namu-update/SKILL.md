---
name: namu-update
description: 다중호스트(claude, agy) 원클릭 업데이트. /namu:update로 명시 호출하거나 사용자가 플러그인을 최신 버전으로 업데이트 해달라고 할 때 사용.
---

# NAMU 원클릭 업데이트

이 스킬의 base directory 기준 `../../scripts/namu_update.py`가 업데이트 스크립트다.

Claude Code와 agy(Antigravity CLI)를 모두 지원하며 설치된 호스트를 자동 감지해 업데이트를 수행한다.

## 실행

OS에 맞는 인터프리터로 그대로 실행한다:

- Windows: `python -X utf8 <base directory>/../../scripts/namu_update.py`
- 그 외(macOS/Linux): `python3 <base directory>/../../scripts/namu_update.py`

## 결과 처리

스크립트는 설치된 각 호스트별로 이전/이후 버전을 출력하고 업데이트를 진행하며, 업데이트가 끝나면 자동으로 `namu_setup_statusline.py`를 호출하여 상태줄 경로까지 맞춰준다. 미설치된 호스트는 조용히(안내 후) skip한다. 출력된 결과를 그대로 사용자에게 요약해주면 된다.
