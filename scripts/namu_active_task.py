#!/usr/bin/env python3
"""NAMU active task resolver — Claude Code & agy `/namu` 스킬 공용. 단일 출처에서 slug 출력."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))
from task_resolve import resolve_active_task

def main() -> None:
    # tasks는 프로젝트 로컬 저장소(namu-26 이원화) — NAMU_HOME(메모리 루트)과
    # 무관하게 항상 현재 프로젝트 폴더(cwd) 기준으로 찾는다. statusLine/브리핑
    # 훅과 동일 규칙(resolve_active_task는 ws만 본다).
    ws = os.getcwd()
    try:
        t = resolve_active_task(ws)
        if t:
            print(t[0])
            return
    except Exception:
        pass
    print("")

if __name__ == "__main__":
    main()
