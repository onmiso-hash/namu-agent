"""task_resolve — stdlib only, no dotenv/DB/network.

단일 출처(single source of truth): active task 찾기 로직.
  - scripts/namu_statusline.py (plain python3) 에서 직접 import
  - session_context.py (uv/namu env) 에서도 여기서 import해 재사용
"""
from pathlib import Path
import os


def _extract_next_section(text: str) -> str | None:
    """'## ▶ 다음' 헤더 아래 본문 추출. 다음 ## 또는 EOF까지, strip."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        if line.startswith("## ▶"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            body.append(line)
    if not in_section:
        return None
    return "\n".join(body).strip() or None


def _extract_task_title(task_md_path: Path) -> str:
    """task.md 첫 번째 # 헤더에서 제목 추출. 실패 시 폴더명 폴백."""
    try:
        for line in task_md_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return task_md_path.parent.name


def find_active_task(machine: str, tasks_dir: Path) -> tuple[str, str] | None:
    """tasks_dir에서 가장 최근에 수정된 진행 중 task의 (폴더명, 제목) 반환. 없으면 None."""
    try:
        candidates = sorted(
            tasks_dir.glob(f"*/context.{machine}.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    for ctx_path in candidates:
        try:
            body = _extract_next_section(ctx_path.read_text(encoding="utf-8"))
            if body is None:
                continue
            if body.strip() == "(완료)":
                continue
            task_dir = ctx_path.parent
            title = _extract_task_title(task_dir / "task.md")
            return (task_dir.name, title)
        except OSError:
            continue
    return None


def resolve_active_task(ws: str, machine: str) -> tuple[str, str] | None:
    """statusline용: NAMU_HOME 환경변수(없으면 ws)에서 tasks_dir 계산 후 active task 반환."""
    namu_home = os.environ.get("NAMU_HOME") or ws
    if not namu_home:
        return None
    return find_active_task(machine, Path(namu_home) / "tasks")
