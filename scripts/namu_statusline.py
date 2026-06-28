#!/usr/bin/env python3
"""NAMU statusline — Claude Code & agy 공용. 한 줄 출력, 표준 라이브러리만."""
import sys
import json
import os
from pathlib import Path

# namu-plugin을 path에 추가 — task_resolve는 stdlib only이므로 plain python3로 import 가능
sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))

from task_resolve import resolve_active_task


def main() -> None:
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
        t = resolve_active_task(ws, machine)
        if t:
            task_part = f"📌 {t[0]} · {t[1]}"
    except Exception:
        pass

    print(f"[{model}] {folder} | {task_part} | {ctx}")


if __name__ == "__main__":
    main()
