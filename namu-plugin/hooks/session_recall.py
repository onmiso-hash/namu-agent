#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1", "typing-extensions>=4.0"]
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
    """다섯 그릇의 검색 색인을 세션 시작 시점에 맞춘다.

    외부 터미널에서 git pull 후 CC를 시작하면 db가 낡아 있을 수 있다(07-10 실측:
    yaml 40건 vs db 37건). 교훈만 재생성하던 것을 `ensure_indexes` 한 번으로 넓혔다
    (fts5-memo-tasks-index 4단계) — 부르는 쪽이 그릇 목록을 알 필요가 없어야 여섯
    번째 그릇이 생겨도 이 배선이 새지 않는다. 안 낡았으면 stat 몇 번으로 끝난다.
    """
    import db

    db.ensure_indexes()


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

        # 같은 브리핑을 두 통로로 내보낸다(namu-64 결함B, 사용자 결정 2026-07-31).
        #   additionalContext → AI 컨텍스트에만 들어간다(화면에 안 뜬다)
        #   systemMessage     → 사용자 터미널에 표시된다
        # 예전에는 additionalContext 하나뿐이라, "사람이 읽기 좋게" 다듬은 브리핑을
        # 정작 사람이 한 번도 보지 못했다(사용자 지적: "브리핑 내역이 안떴어").
        # AI가 매 세션 옮겨 적는 규약으로 때우지 않은 이유는 그게 지켜진다는 보장이
        # 없기 때문이다 — 훅이 직접 내보내면 AI의 협조와 무관하게 항상 뜬다.
        print(
            json.dumps(
                {
                    "systemMessage": md,
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": md,
                    },
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
