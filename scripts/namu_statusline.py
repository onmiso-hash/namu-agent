#!/usr/bin/env python3
"""NAMU statusline — Claude Code & agy 공용. 한 줄 출력, 표준 라이브러리만.

⚠️ 이 repo 루트 사본은 개발 기기의 글로벌 `~/.claude/settings.json`(git 밖, 절대경로)이
직접 참조 중이라 이동·삭제 금지. 설치형 사용자용 동봉 사본은
`namu-plugin/scripts/namu_statusline.py`에 있다(namu-26) — import 경로 계산만 다르고
나머지 로직은 동일해야 한다. 한쪽을 고치면 반드시 다른 쪽도 맞출 것.

관측성: 매 렌더를 ~/.namu/db/statusline.log에 남긴다(namu-35: 데이터 루트 고정, 환경변수
NAMU_HOME 폐지) — statusLine 미동기화 증상이 재발하면 이 로그와 화면을 대조해
"스크립트가 안 돎(하네스) vs 돌았는데 틀림(스크립트)"을 판정한다. 실패는
'진행 task 없음'으로 위장하지 않고 '⚠ task 조회 오류'로 구분 표시한다.
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
    """렌더 로그 경로 — namu-35: 데이터 루트가 `Path.home()/".namu"` 고정이라
    ws와 무관하게 항상 이 경로다(환경변수 NAMU_HOME은 더 이상 참조하지 않는다).
    """
    return Path.home() / ".namu" / "db" / "statusline.log"


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


def _window_used_pct(data: dict, claude_key: str, agy_suffix: str) -> int | None:
    """statusLine 꼬리용 '쓴 %'. Claude(rate_limits.<claude_key>.used_percentage) 우선,
    없으면 agy(quota.<group>-<agy_suffix>.remaining_fraction) 폴백. 둘 다 없으면 None(namu-39).

    Claude와 agy는 stdin 스키마 자체가 다르고 한 도구는 자기 키만 보내므로(rate_limits와
    quota는 상호배타) 둘 다 뒤져봐도 충돌하지 않는다. agy의 remaining_fraction은 "남은"
    비율(0.0~1.0)로 Claude의 "쓴 %"와 극성이 반대라 (1 - remaining) * 100으로 통일해
    출력 형식을 하나로 맞춘다("쓴 %" 기준). 활성 모델 그룹(gemini vs 3p)은
    model.display_name에 "gemini" 포함 여부로 고르되, 우선 그룹에 데이터가 없으면
    다른 그룹으로 폴백한다.
    """
    rate_limits = data.get("rate_limits") or {}
    claude_val = (rate_limits.get(claude_key) or {}).get("used_percentage")
    if isinstance(claude_val, (int, float)):
        return round(claude_val)

    quota = data.get("quota") or {}
    model_name = (data.get("model") or {}).get("display_name") or ""
    groups = ["gemini", "3p"] if "gemini" in model_name.lower() else ["3p", "gemini"]
    for group in groups:
        entry = quota.get(f"{group}-{agy_suffix}")
        remaining = (entry or {}).get("remaining_fraction")
        if isinstance(remaining, (int, float)):
            return round((1 - remaining) * 100)
    return None


def _plugin_version() -> str | None:
    """자기 namu 플러그인의 설치 버전을 읽는다(설치본·개발 사본 모두 대응).

    스크립트 자기 위치(parent.parent) 기준으로 plugin.json을 찾으므로, 이 스크립트를
    실행하는 그 호스트의 실제 설치 버전을 그대로 반영한다(claude=.../namu/<ver>/,
    agy=~/.gemini/config/plugins/namu/, repo 개발 사본 포함) — 호스트 간 버전
    드리프트가 화면에 그대로 보인다. 실패해도 statusline 출력을 막으면 안 되므로
    전예외 무음(None).
    """
    base = Path(__file__).parent.parent
    for candidate in (
        base / ".claude-plugin" / "plugin.json",  # 설치본(claude/agy)·namu-plugin/
        base / "plugin.json",                      # 루트 plugin.json 폴백
        base / "namu-plugin" / ".claude-plugin" / "plugin.json",  # repo 루트 동봉 사본
    ):
        try:
            if candidate.exists():
                ver = json.loads(candidate.read_text(encoding="utf-8")).get("version")
                if ver:
                    return str(ver)
        except Exception:
            pass
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
    ver = _plugin_version()
    namu_badge = f"[Namu {ver}] " if ver else ""
    pct = (data.get("context_window") or {}).get("used_percentage")
    ctx = f"{round(pct)}%" if isinstance(pct, (int, float)) else "?"

    # 5시간/주간 rate limit — Claude(rate_limits.five_hour/seven_day.used_percentage) 또는
    # agy(quota.<group>-5h/weekly.remaining_fraction) 중 보내온 쪽을 쓴다(namu-39, 상세는
    # _window_used_pct 참고). 두 필드/각 윈도우는 독립적으로 부재 가능(비구독자·세션 첫
    # 응답 전) — 부재 시 조용히 생략한다(ctx의 "?" 폴백과 달리 오류 표시 없음, 하위 호환 유지).
    tail_parts = [ctx]
    five = _window_used_pct(data, "five_hour", "5h")
    if five is not None:
        tail_parts.append(f"5h {five}%")
    seven = _window_used_pct(data, "seven_day", "weekly")
    if seven is not None:
        tail_parts.append(f"7d {seven}%")
    tail = " · ".join(tail_parts)

    try:
        t = resolve_active_task(ws)
        if t:
            slug, title = t[0], t[1]
            # task.md 제목 관례가 "<slug> — <설명>"이라 제목이 이미 slug로 시작하면
            # 중복 표시를 피한다(namu-37).
            task_part = f"📌 {title}" if title.startswith(slug) else f"📌 {slug} · {title}"
        else:
            task_part = "진행 task 없음"
    except Exception:
        # 실패를 '없음'으로 위장하지 않는다 — 화면에 구분 표시 + 로그에 물증
        task_part = "⚠ task 조회 오류"
        _append_log(ws, "ERROR | " + traceback.format_exc().strip().replace("\n", " ⏎ "))

    out = f"{namu_badge}[{model}] {folder} | {task_part} | {tail}"
    _append_log(ws, f"{out} | tasks_dir={_resolved_tasks_dir(ws)}")
    print(out)


if __name__ == "__main__":
    main()
