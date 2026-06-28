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


def find_active_task(machine: str) -> Path | None:
    """tasks/ 아래에서 가장 최근에 수정된 진행 중 task 폴더 반환. 없으면 None.

    머신별 context 파일만 대상으로 함 — 다른 PC 파일의 mtime 오염 구조적 차단.
    """
    import config as cfg

    result = _resolve_task(machine, cfg.TASKS_DIR)
    if result is None:
        return None
    return cfg.TASKS_DIR / result[0]


# --- DEBUG START ---
def _build_debug_block(machine: str) -> str:
    import config as cfg

    namu_machine = cfg.NAMU_MACHINE
    namu_home = str(cfg.NAMU_HOME)
    config_file = str(Path(cfg.__file__).resolve())
    glob_pattern = str(cfg.TASKS_DIR / f"*/context.{machine}.md")

    try:
        candidates = sorted(
            cfg.TASKS_DIR.glob(f"*/context.{machine}.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        candidates = []

    candidate_paths = [str(p) for p in candidates]

    decisions: list[str] = []
    for ctx_path in candidates:
        try:
            body = _extract_next_section(ctx_path.read_text(encoding="utf-8"))
            if body is None:
                decisions.append(f"{ctx_path.parent.name}: ▶다음 섹션 없음 → 탈락")
            elif body.strip() == "(완료)":
                decisions.append(f"{ctx_path.parent.name}: ▶다음이 (완료) → 탈락")
            else:
                preview = repr(body.strip())[:40]
                decisions.append(f"{ctx_path.parent.name}: 미완료={preview} → 채택")
        except OSError as e:
            decisions.append(f"{ctx_path.parent.name}: OSError({e}) → 탈락")

    lines = [
        "\n--- DEBUG START ---",
        f"1. NAMU_MACHINE = {namu_machine!r}",
        f"2. NAMU_HOME = {namu_home!r}",
        f"3. config.__file__ = {config_file!r}",
        f"4. glob pattern = {glob_pattern!r}",
        f"5. 후보 파일 = {candidate_paths!r}",
        "6. 채택/탈락 판정:",
    ]
    for d in decisions:
        lines.append(f"   - {d}")
    if not decisions:
        lines.append("   (후보 없음)")
    lines.append("--- DEBUG END ---")
    return "\n".join(lines)
# --- DEBUG END ---


def build_context_markdown(conn, machine: str) -> str | None:
    """세션 컨텍스트 마크다운 조립. 내용이 없으면(task도 교훈도 0) None 반환."""
    import db

    active = find_active_task(machine)
    parts: list[str] = ["## 🌳 NAMU — 세션 컨텍스트 자동 로딩\n"]

    if active:
        title = _extract_task_title(active / "task.md")

        try:
            ctx_text = (active / f"context.{machine}.md").read_text(encoding="utf-8")
            next_body = _extract_next_section(ctx_text)
        except OSError:
            next_body = None

        log_snippet = _extract_log_tail(active / "log.md")
        learnings = db.recall(conn, query=title, limit=3)

        parts.append(f"### 📌 진행 중: {title}")
        if next_body:
            parts.append(f"- **다음 할 일:** {next_body}")
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
    parts.append(_build_debug_block(machine))  # --- DEBUG ---
    return "\n".join(parts)
