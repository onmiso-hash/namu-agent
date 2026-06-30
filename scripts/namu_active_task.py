#!/usr/bin/env python3
"""NAMU active task resolver — Claude Code & agy `/namu` 스킬 공용. 단일 출처에서 slug 출력."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))
from task_resolve import resolve_active_task

def main() -> None:
    ws = os.environ.get("NAMU_HOME") or os.getcwd()
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
