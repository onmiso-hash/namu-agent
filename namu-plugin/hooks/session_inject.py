# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "typing-extensions>=4.0"]
# ///
"""PreInvocation 훅 — agy 세션 컨텍스트 자동 주입.

conversationId 기반 플래그 파일로 세션당 1회만 주입.
어떤 에러도 {} 출력 + exit 0 (세션 안 막음).
"""
import json
import os
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
    # 네이티브 Windows 파이프 stdout은 cp949라 이모지 출력 시 UnicodeEncodeError (#16 statusLine과 동일 패턴)
    sys.stdout.reconfigure(encoding="utf-8")
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

        # agy 플러그인 훅의 cwd는 플러그인 설치 폴더 → 워크스페이스 .env를 못 찾음.
        # config가 find_dotenv(usecwd=True)로 .env를 찾기 전에 워크스페이스로 이동한다.
        workspace_paths = data.get("workspacePaths") or []
        if workspace_paths:
            try:
                os.chdir(workspace_paths[0])
            except OSError:
                pass

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
