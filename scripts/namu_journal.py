#!/usr/bin/env python3
"""NAMU 작업 이력 시간순 뷰 — Claude Code & agy `/namu` 스킬 공용(stdlib 전용).

여러 task의 `log.md`를 **task 경계를 넘어** 시간순으로 합쳐 출력한다(namu-57 1-1).
"어제 무슨 일이 있었나"가 활성 task 추측 없이 답된다.

  python scripts/namu_journal.py [--limit N] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                 [--machine hp] [--task namu-57] [--project namu-agent]
                                 [--json]

`--project`를 생략하면 현재 폴더(cwd) 프로젝트만 본다(브리핑 기본값). `--project all`
이면 개인 풀의 모든 프로젝트를 합친다.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))
from task_resolve import journal


def main() -> None:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--machine")
    ap.add_argument("--task")
    ap.add_argument("--project", default=None, help="생략=현재 프로젝트, 'all'=전체")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.project == "all":
        project = None
    else:
        project = args.project or os.getcwd()

    try:
        rows = journal(
            project=project,
            since=args.since,
            until=args.until,
            machine=args.machine,
            task=args.task,
            limit=args.limit,
        )
    except Exception:
        # 브리핑 보조 기능 — 실패 시 조용히 빈 출력(세션 시작을 막지 않는다)
        rows = []

    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
        return
    for r in rows:
        machine = r["machine"] or "-"
        print(f"{r['ts'][:16]} {machine} {r['task_slug']} [{r['tag']}] {r['text']}")


if __name__ == "__main__":
    main()
