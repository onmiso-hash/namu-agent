#!/usr/bin/env python3
"""SessionStart 훅 — 세션 컨텍스트(작업 상태 + 교훈) 자동 주입.

세션 시작 시 실행돼 build_context_markdown() 결과를 Claude Code 컨텍스트에 주입한다.
어떤 에러가 나도 exit 0 (훅이 세션 시작을 막으면 안 됨).
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _ensure_db(cfg) -> None:
    import db

    if not cfg.NAMU_DB_PATH.exists():
        db.init_db()
        if cfg.LEARNINGS_YAML_PATH.exists():
            db.rebuild_from_yaml()


def main() -> None:
    try:
        import config as cfg
        from session_context import build_context_markdown

        _ensure_db(cfg)

        with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
            md = build_context_markdown(conn, cfg.NAMU_MACHINE)

        if md is None:
            sys.exit(0)

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": md,
                    }
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
