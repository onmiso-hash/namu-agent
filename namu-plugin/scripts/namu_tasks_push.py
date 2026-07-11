#!/usr/bin/env python3
"""namu_tasks_push — task 파일 갱신 시점 push 전용 CLI(namu-34 ③-b).

⚠️ 이 파일은 repo 루트 `scripts/namu_tasks_push.py`의 동봉용 사본이다(namu-26 statusline
동봉 관례와 동일) — import 경로 계산(아래 sys.path 라인)만 다르고 나머지 로직은
동일해야 한다. 한쪽을 고치면 반드시 다른 쪽도 맞출 것.

`/namu-task` 절차(오케스트레이터)가 task 3파일(task.md/context.<machine>.md/log.md)을
갱신한 직후 호출하는 push 경로다. 대상은 항상 `Path.home()/".namu"`다(namu-35 이후로는
cfg.NAMU_DATA_ROOT와 동일 경로). tasks는 저장 위치가 개인 풀로 통합됐고(namu-34 ①),
memory_sync.sync_enabled()의 마커 파일 게이트와는 무관하게 이 CLI는 대상(`~/.namu`)
자체가 git repo이고 origin 원격을 가졌는지만 본다(tasks_pool_git_ready).

동작: ~/.namu가 git repo이고 origin 원격이 있으면 tasks/(+memory/) add → 변경
있으면 commit → push. 아니면(신규 sync 미개통 등) 조용히 no-op. 어느 경로든 항상
종료코드 0 — 이 스크립트의 실패가 작업 절차 자체를 막으면 안 된다(다른 무음 실패
헬퍼들과 동일 원칙). git 호출 자체는 memory_sync.push_tasks_pool()에 위임한다
(타임아웃 5~10초·sync.log 기록 패턴 재사용 — 새 무제한 git 호출 코드를 만들지 않는다).
"""
import sys
from pathlib import Path

# 이 파일은 namu-plugin/scripts/ 아래에 있으므로 parent.parent가 이미 namu-plugin이다
# (repo 루트 scripts/ 버전은 parent.parent가 repo 루트라 "namu-plugin"을 덧붙였다 — 계산 기준이 다름)
sys.path.insert(0, str(Path(__file__).parent.parent))

import memory_sync as ms


def main() -> int:
    home = Path.home() / ".namu"
    if not ms.tasks_pool_git_ready(home):
        return 0
    ms.push_tasks_pool(home, "tasks: sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
