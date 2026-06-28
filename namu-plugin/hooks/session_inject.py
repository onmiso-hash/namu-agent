# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0"]
# ///
"""PreInvocation 훅 — agy 세션 컨텍스트 자동 주입.

conversationId 기반 플래그 파일로 세션당 1회만 주입.
어떤 에러도 {} 출력 + exit 0 (세션 안 막음).
"""
import json
import sqlite3
import sys
import tempfile
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
        raw = sys.stdin.read()
        try:
            data = json.loads(raw)
        except Exception:
            print("{}")
            sys.exit(0)

        conversation_id = data.get("conversationId")
        if not conversation_id:
            print("{}")
            sys.exit(0)

        flag = Path(tempfile.gettempdir()) / f"namu_injected_{conversation_id}"
        if flag.exists():
            print("{}")
            sys.exit(0)

        import config as cfg
        from session_context import build_context_markdown

        _ensure_db(cfg)

        with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
            md = build_context_markdown(conn, cfg.NAMU_MACHINE)

        if md:
            print(json.dumps({"injectSteps": [{"ephemeralMessage": md}]}, ensure_ascii=False))
            flag.touch()
        else:
            print("{}")

    except Exception:
        print("{}")

    sys.exit(0)


if __name__ == "__main__":
    main()
