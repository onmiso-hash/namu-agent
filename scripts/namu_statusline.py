#!/usr/bin/env python3
"""NAMU statusline — Claude Code & agy 공용. 한 줄 출력, 표준 라이브러리만.

⚠️ 이 repo 루트 사본은 개발 기기의 글로벌 `~/.claude/settings.json`(git 밖, 절대경로)이
직접 참조 중이라 이동·삭제 금지. 설치형 사용자용 동봉 사본은
`namu-plugin/scripts/namu_statusline.py`에 있다(namu-26) — import 경로 계산만 다르고
나머지 로직은 동일해야 한다. 한쪽을 고치면 반드시 다른 쪽도 맞출 것.

관측성: 매 렌더를 NAMU_HOME/db/statusline.log에 남긴다 — statusLine 미동기화
증상이 재발하면 이 로그와 화면을 대조해 "스크립트가 안 돎(하네스) vs 돌았는데
틀림(스크립트)"을 판정한다. 실패는 '진행 task 없음'으로 위장하지 않고
'⚠ task 조회 오류'로 구분 표시한다.
"""
import sys
import json
import os
import traceback
from datetime import datetime
from pathlib import Path

# namu-plugin을 path에 추가 — task_resolve는 stdlib only이므로 plain python3로 import 가능
sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))

from task_resolve import resolve_active_task, tasks_root_for

# cp949 파이프 안전망 — 호출 측이 -X utf8 없이 부르면 📌(비BMP 이모지) print가
# UnicodeEncodeError로 죽고, 한글만 있는 '진행 task 없음'은 살아남아
# "task만 안 뜨는" 무음 실패가 된다 (session_recall.py cp949 버그와 동일 패턴).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LOG_MAX_BYTES = 256_000  # 초과 시 최근 200줄만 유지
LOG_KEEP_LINES = 200


def _log_path(ws: str) -> Path | None:
    """렌더 로그 경로 — task 탐지와 같은 규칙(NAMU_HOME 우선, 없으면 ws)으로 계산."""
    root = os.environ.get("NAMU_HOME") or ws
    if not root:
        return None
    return Path(root) / "db" / "statusline.log"


def _append_log(ws: str, line: str) -> None:
    """렌더/오류 기록. 로깅 실패가 statusline 출력을 막으면 안 되므로 전예외 무음."""
    try:
        path = _log_path(ws)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {line}\n")
        if path.stat().st_size > LOG_MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()[-LOG_KEEP_LINES:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _resolved_tasks_dir(ws: str) -> Path | None:
    """렌더 로그 관측용 — tasks 저장 위치(namu-34, ~/.namu/tasks/<basename>/) 계산.

    실패해도 statusline 출력을 막으면 안 되므로 전예외 무음(None).
    """
    if not ws:
        return None
    try:
        return tasks_root_for(ws)
    except Exception:
        return None


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

    try:
        t = resolve_active_task(ws)
        task_part = f"📌 {t[0]} · {t[1]}" if t else "진행 task 없음"
    except Exception:
        # 실패를 '없음'으로 위장하지 않는다 — 화면에 구분 표시 + 로그에 물증
        task_part = "⚠ task 조회 오류"
        _append_log(ws, "ERROR | " + traceback.format_exc().strip().replace("\n", " ⏎ "))

    out = f"[{model}] {folder} | {task_part} | {ctx}"
    _append_log(ws, f"{out} | tasks_dir={_resolved_tasks_dir(ws)}")
    print(out)


if __name__ == "__main__":
    main()
