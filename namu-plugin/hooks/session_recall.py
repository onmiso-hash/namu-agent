#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "typing-extensions>=4.0"]
# ///
"""SessionStart 훅 — 세션 컨텍스트(작업 상태 + 교훈) 자동 주입.

세션 시작 시 실행돼 build_context_markdown() 결과를 Claude Code 컨텍스트에 주입한다.
어떤 에러가 나도 exit 0 (훅이 세션 시작을 막으면 안 됨).
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _project_dir_from_stdin() -> str:
    """SessionStart 훅 stdin JSON에서 현재 프로젝트 경로(cwd)를 얻는다.

    Claude Code 훅 input JSON은 공통 필드로 session_id/transcript_path/cwd/
    hook_event_name을 담아 보낸다(SessionStart는 추가로 source도 포함).
    tasks는 프로젝트 로컬 저장소라, 브리핑도 statusLine과 동일하게 "지금 이
    프로젝트"의 tasks/를 봐야 한다(namu-26 이원화 통일).
    stdin이 비었거나 JSON 파싱 실패, cwd 필드 부재 시 os.getcwd()로 폴백한다.
    """
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    return data.get("cwd") or os.getcwd()


def _ensure_db(cfg) -> None:
    import db

    if not cfg.NAMU_DB_PATH.exists():
        db.init_db()
        if cfg.LEARNINGS_YAML_PATH.exists():
            db.rebuild_from_yaml()
    elif db.cache_is_stale(cfg.LEARNINGS_YAML_PATH, cfg.NAMU_DB_PATH):
        # 외부 터미널에서 git pull 후 CC를 시작한 경우 db가 낡아 있을 수 있음
        # (07-10 실측: yaml 40건 vs db 37건) — 세션 브리핑이 최신 교훈을 반영하도록 재생성.
        db.rebuild_from_yaml()


def main() -> None:
    try:
        # 네이티브 Windows 파이프 stdout은 cp949라 이모지 출력 시 UnicodeEncodeError로
        # 무음 삼켜짐(#16 statusLine, session_inject.py와 동일 패턴)
        sys.stdout.reconfigure(encoding="utf-8")

        project_dir = _project_dir_from_stdin()

        import config as cfg
        import memory_sync
        from session_context import build_context_markdown

        # 활성화(marker)돼 있으면 다른 PC에서 쌓인 교훈을 먼저 당겨온다 — pull로
        # yaml이 갱신되면 아래 _ensure_db의 cache_is_stale 판정이 db를 재생성한다.
        # 비활성/실패는 무음(memory_sync.sync_pull이 보장) — 세션 시작을 막지 않는다.
        memory_sync.sync_pull()
        _ensure_db(cfg)

        with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
            md = build_context_markdown(conn, cfg.NAMU_MACHINE, project_dir)

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
