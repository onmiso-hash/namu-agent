#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1"]
# ///
"""OpenCode 플러그인용 마무리 검사 도우미 — closing_guard.py의 판정만 빌린다.

stdin JSON: {"since_epoch_ms": <세션 시작(또는 일이 다시 시작된 때) epoch ms>}
stdout JSON: {"touched": ["방/task", ...], "satisfied": ["방/task", ...]}

`since` 이후 개인 풀 전체의 작업일지에 `[다음]`/`[완료]`/`[중단]` 줄이 하나라도
들어갔으면 satisfied에 담는다. 방으로 좁히지 않고 기계 도장으로 좁히는 규칙은
closing_guard._lines_since와 같다. 막지 않고 결과만 돌려준다 — 막을지 말지는
부르는 쪽(OpenCode 프롬프트 훅)이 정한다.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = os.environ.get("NAMU_REPO_ROOT") or str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(REPO_ROOT) / "namu-plugin"))

_SATISFYING_TAGS = ("다음", "완료", "중단")


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        since_ms = int(data.get("since_epoch_ms") or 0)

        import config as cfg
        import task_resolve

        tz = cfg.local_tz()
        dt = datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc)
        if tz is not None:
            dt = dt.astimezone(tz)
        since_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        machine = cfg.NAMU_MACHINE

        touched: list[str] = []
        satisfied: list[str] = []
        for entry in task_resolve.journal(project=None, since=since_ts):
            line_machine = entry.get("machine")
            if machine and line_machine and line_machine != machine:
                continue
            slug = entry.get("task_slug") or ""
            if not slug:
                continue
            where = f"{entry.get('project') or '?'}/{slug}"
            if where not in touched:
                touched.append(where)
            if entry.get("tag") in _SATISFYING_TAGS and where not in satisfied:
                satisfied.append(where)
        print(json.dumps({"touched": touched, "satisfied": satisfied}, ensure_ascii=False))
    except Exception:
        print(json.dumps({"touched": [], "satisfied": []}))


if __name__ == "__main__":
    main()
