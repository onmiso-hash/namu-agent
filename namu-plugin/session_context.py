"""공유 세션 컨텍스트 헬퍼 — session_recall.py(Claude Code)와 session_inject.py(agy)가 공동 호출.

conn은 호출자가 열고 닫는다. 예외는 삼키지 않고 호출자가 처리.
단, 개별 파일 파싱 실패는 해당 파일만 스킵하고 진행.
"""
from pathlib import Path
from task_resolve import _extract_next_section, _extract_task_title
from task_resolve import find_active_task as _resolve_task


def _extract_log_tail(log_path: Path, n: int = 5) -> str:
    """log.md 마지막 n개 비어있지 않은 줄(헤더 제외)."""
    try:
        lines = [
            ln.strip()
            for ln in log_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("# ")
        ]
        tail = lines[-n:]
        return "\n  ".join(tail)
    except OSError:
        return ""


def find_active_task() -> Path | None:
    """tasks/ 아래에서 가장 최근에 진행 중인 task 폴더 반환. 없으면 None."""
    import config as cfg

    result = _resolve_task(cfg.TASKS_DIR)
    if result is None:
        return None
    return cfg.TASKS_DIR / result[0]


def build_context_markdown(conn, machine: str) -> str | None:
    """세션 컨텍스트 마크다운 조립. 내용이 없으면(task도 교훈도 0) None 반환."""
    import db

    active = find_active_task()
    parts: list[str] = ["## 🌳 NAMU — 세션 컨텍스트 자동 로딩\n"]

    if active:
        title = _extract_task_title(active / "task.md")

        next_items = []
        try:
            for ctx_file in active.glob("context.*.md"):
                # context.hp.md -> hp
                ctx_machine = ctx_file.name.split(".")[1]
                body = _extract_next_section(ctx_file.read_text(encoding="utf-8"))
                if body and body.strip() != "(완료)":
                    next_items.append(f"({ctx_machine}) {body}")
        except OSError:
            pass

        log_snippet = _extract_log_tail(active / "log.md")
        learnings = db.recall(conn, query=title, limit=3)

        parts.append(f"### 📌 진행 중: {title}")
        if next_items:
            parts.append("- **다음 할 일:**")
            for item in next_items:
                indented = item.replace("\n", "\n    ")
                parts.append(f"  - {indented}")
        if log_snippet:
            parts.append(f"- **최근 로그:**\n  {log_snippet}")
        parts.append("")

        if learnings:
            parts.append("### 💡 관련 교훈")
            for it in learnings:
                parts.append(f"- [{it['outcome']}] {it['task']}: {it['reason']}")
    else:
        learnings = db.recall(conn, limit=5)
        if not learnings:
            return None

        parts.append("### 💡 최근 교훈")
        for it in learnings:
            parts.append(f"- [{it['outcome']}] {it['task']}: {it['reason']}")

    parts.append("\n---\n※ 새 교훈이 생기면 namu_record 도구로 저장하세요.")
    return "\n".join(parts)
