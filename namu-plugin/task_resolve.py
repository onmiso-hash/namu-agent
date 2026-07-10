"""task_resolve — stdlib only, no dotenv/DB/network.

단일 출처(single source of truth): active task 찾기 로직.
  - scripts/namu_statusline.py (plain python3) 에서 직접 import
  - session_context.py (uv/namu env) 에서도 여기서 import해 재사용
"""
import re
from pathlib import Path


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


def _parse_log_ts(line: str) -> tuple[str, str] | None:
    """log.md 한 줄에서 (날짜, 시간) 튜플 추출."""
    match = re.search(r"^\[.*?\]\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}:\d{2}))?(?:\s|$)", line)
    if not match:
        return None
    date_str = match.group(1)
    time_str = match.group(2) or "00:00:00"
    return (date_str, time_str)


def _latest_log_ts(log_path: Path) -> tuple[str, str] | None:
    """log.md에서 가장 마지막으로 파싱 성공한 타임스탬프 반환."""
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    
    for line in reversed(lines):
        ts = _parse_log_ts(line)
        if ts is not None:
            return ts
    return None


_TAG_RE = re.compile(r"^\[(.*?)\]")


def _line_tag(line: str) -> str | None:
    """log.md 한 줄 앞의 [태그]를 추출. 없으면 None."""
    match = _TAG_RE.match(line.strip())
    return match.group(1) if match else None


def _log_says_closed(log_path: Path) -> bool:
    """log.md 마지막 [시작] 태그 줄 이후 구간(없으면 전체)에 [완료]/[중단] 태그 줄이
    존재하면 True (log=권위 판정).

    "마지막 줄이 [완료]인가"로 구현하면 [완료] 뒤에 [정정]처럼 후속 기록이 붙는
    실물 패턴(tasks/namu-25-usage-guide/log.md)에서 도로 유령(오탐지)이 된다.
    반드시 구간 내 존재 판정이어야 한다. [완료] 뒤에 새 [시작]이 붙으면(재개) 그
    이후 구간만 보므로 다시 열림으로 판정된다.
    """
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    last_start_idx = None
    for i, line in enumerate(lines):
        if _line_tag(line) == "시작":
            last_start_idx = i

    scope = lines[last_start_idx + 1:] if last_start_idx is not None else lines
    return any(_line_tag(line) in ("완료", "중단") for line in scope)


def _all_contexts_done(task_dir: Path) -> bool:
    """해당 task의 모든 context.*.md 파일의 '## ▶ 다음' 섹션이 '(완료)'인지 확인.
    context 파일이 없으면 False(아직 진행 중) 반환.
    """
    try:
        context_files = list(task_dir.glob("context.*.md"))
    except OSError:
        return False
        
    if not context_files:
        return False
        
    for ctx_path in context_files:
        try:
            body = _extract_next_section(ctx_path.read_text(encoding="utf-8"))
            if body is None or body.strip() != "(완료)":
                return False
        except OSError:
            return False
            
    return True


def _sorted_task_dirs(tasks_dir: Path) -> list[Path]:
    """tasks_dir 아래 각 task 폴더를 log 최신 타임스탬프 내림차순으로 정렬해 반환."""
    try:
        log_files = list(tasks_dir.glob("*/log.md"))
    except OSError:
        return []

    task_ts_list = []
    for log_path in log_files:
        ts = _latest_log_ts(log_path)
        if ts is not None:
            task_ts_list.append((ts, log_path.parent))

    task_ts_list.sort(key=lambda x: x[0], reverse=True)
    return [task_dir for _, task_dir in task_ts_list]


def _is_closed(task_dir: Path) -> bool:
    """log=권위 판정(주) + context 전부 (완료) 판정(보조)."""
    return _log_says_closed(task_dir / "log.md") or _all_contexts_done(task_dir)


def find_active_task(tasks_dir: Path) -> tuple[str, str] | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 진행 중 task의 (폴더명, 제목) 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if not _is_closed(task_dir):
            title = _extract_task_title(task_dir / "task.md")
            return (task_dir.name, title)

    return None


def find_latest_closed_task(tasks_dir: Path) -> Path | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 '닫힌' task 폴더 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if _is_closed(task_dir):
            return task_dir

    return None


def resolve_active_task(ws: str) -> tuple[str, str] | None:
    """statusline용: 현재 프로젝트(ws) 기준으로 tasks_dir 계산 후 active task 반환.

    tasks는 프로젝트 로컬 데이터이므로 NAMU_HOME(메모리 루트)과는 무관하게 ws만 본다
    (NAMU_HOME이 설정돼 있어도 무시 — statusLine은 항상 "지금 이 프로젝트"의 tasks를 본다).
    ws가 비어있을 때만 탐지 불가로 None을 반환하는 안전 폴백을 둔다.
    """
    if not ws:
        return None
    return find_active_task(Path(ws) / "tasks")
