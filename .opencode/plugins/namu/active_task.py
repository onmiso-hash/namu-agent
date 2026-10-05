#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1"]
# ///
"""OpenCode TUI 상태줄용 — namu_statusline.py의 task 판정만 빌린다.

Claude Code판 statusLine(namu_statusline.py)은 모델명·컨텍스트 사용률·rate limit처럼
OpenCode TUI Context에는 없는 호스트별 필드까지 한 줄에 섞어 찍는다. OpenCode 쪽에
필요한 건 그 중 "지금 이 작업 폴더에 핀 찍힌(또는 가장 최근) task가 뭔가" 하나뿐이라,
그 판정(task_resolve.resolve_active_task)만 떼어 와 깨끗한 JSON으로 돌려준다 —
한 줄짜리 혼합 문자열을 TUI 쪽에서 정규식으로 다시 쪼개는 건 더 깨진다.

폴더 칸과 나무 판 번호도 같은 판정(project_key_for · plugin.json)으로 함께 돌려준다 —
화면의 폴더 이름이 기록이 가는 방 이름과 어긋나지 않게 하기 위해서다.

stdin JSON: {"directory": "<TUI Context.location.directory>"}
stdout JSON: {"version": "...", "folder": "...", "slug": "...", "title": "..."}
             (작업이 없으면 slug·title 없음, 조회 실패면 "error": true)
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "namu-plugin"))


def _plugin_version() -> str:
    for candidate in (
        REPO_ROOT / "namu-plugin" / ".claude-plugin" / "plugin.json",
        REPO_ROOT / "namu-plugin" / "plugin.json",
    ):
        try:
            ver = json.loads(candidate.read_text(encoding="utf-8")).get("version")
            if ver:
                return str(ver)
        except Exception:
            pass
    return ""


def main() -> None:
    out: dict = {"version": _plugin_version()}
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        ws = data.get("directory") or ""

        import task_resolve

        out["folder"] = (task_resolve.project_key_for(ws) if ws else "") or "?"
        t = task_resolve.resolve_active_task(ws) if ws else None
        if t:
            out["slug"] = t[0]
            out["title"] = task_resolve.one_line(t[1], task_resolve.TITLE_LINE_LIMIT)
    except Exception:
        # 실패를 '없음'으로 위장하지 않는다 (namu_statusline.py와 같은 규칙).
        out["error"] = True
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
