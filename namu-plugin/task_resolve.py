"""task_resolve — stdlib only, no dotenv/DB/network.

단일 출처(single source of truth): active task 찾기 로직.
  - scripts/namu_statusline.py (plain python3) 에서 직접 import
  - session_context.py (uv/namu env) 에서도 여기서 import해 재사용

tasks 저장 위치 규칙(namu-34)도 이 모듈에 단일 구현한다: 규칙 한 줄, 특례 0
(`tasks_root_for`) — config.py는 이를 위임 호출할 뿐 규칙을 다시 구현하지 않는다.
"""
import os
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


def tasks_root_for(project_dir: str | Path) -> Path:
    """tasks 저장 루트 = 개인 풀 `~/.namu/tasks/<basename(project_dir)>/` (namu-34).

    규칙 한 줄, 특례 0 — NAMU_HOME(교훈·db 전용)과는 무관하며 개발 모드(이 repo)도
    예외를 두지 않는다. tasks는 여전히 "프로젝트 귀속" 데이터지만 저장 위치만
    개인 풀로 통합해, PC 간 공유를 개인 전역 동기화에 편승시킨다(공개 repo에
    작업 기록이 노출되는 것도 원천 차단).

    Path.home()은 HOME 환경변수를 존중하므로(POSIX) 테스트는 monkeypatch로
    가짜 HOME을 주입해 실제 ~/.namu를 건드리지 않고 격리할 수 있다.
    """
    key = os.path.basename(str(project_dir).rstrip("/\\"))
    return Path.home() / ".namu" / "tasks" / key


def resolve_active_task(ws: str) -> tuple[str, str] | None:
    """statusline용: 현재 프로젝트(ws) 기준으로 tasks 루트 계산 후 active task 반환.

    tasks 저장 위치는 개인 풀(`tasks_root_for(ws)` = `~/.namu/tasks/<basename(ws)>/`,
    namu-34)이며, NAMU_HOME(메모리 루트)과는 무관하게 ws의 폴더명만 키로 쓴다
    (NAMU_HOME이 설정돼 있어도 무시 — statusLine은 항상 "지금 이 프로젝트"의 tasks를 본다).
    ws가 비어있을 때만 탐지 불가로 None을 반환하는 안전 폴백을 둔다.
    """
    if not ws:
        return None
    return find_active_task(tasks_root_for(ws))


_MARKER_FILENAME = ".project"


def _marker_path(tasks_root: Path) -> Path:
    return tasks_root / _MARKER_FILENAME


def _last_marker_path_for_machine(lines: list[str], machine: str) -> str | None:
    last: str | None = None
    for line in lines:
        m, sep, path = line.partition("=")
        if sep and m == machine:
            last = path
    return last


def record_project_marker(tasks_root: Path, machine: str, project_dir: str) -> None:
    """`<machine>=<project_dir 절대경로>` 줄을 append-only로 기록한다(namu-34 ②).

    키 폴더 하나(basename 충돌)를 여러 프로젝트가 같은 machine에서 사용하면
    이력이 남도록 기존 줄은 절대 수정·삭제하지 않는다. 단, 해당 machine의 마지막
    줄이 이미 같은 경로(realpath 비교)면 재기록하지 않는다(멱등 — 매 세션 호출
    가정이라 재기록하면 무한히 불어난다).
    """
    marker_path = _marker_path(tasks_root)
    resolved = os.path.realpath(str(project_dir))

    try:
        existing_lines = marker_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        existing_lines = []

    last_for_machine = _last_marker_path_for_machine(existing_lines, machine)
    if last_for_machine is not None and os.path.realpath(last_for_machine) == resolved:
        return

    try:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        with marker_path.open("a", encoding="utf-8") as f:
            f.write(f"{machine}={resolved}\n")
    except OSError:
        pass


def check_project_marker_conflict(
    tasks_root: Path, machine: str, project_dir: str
) -> tuple[str, str] | None:
    """현재 machine의 마지막 등록 경로 ≠ project_dir(realpath)이면 (등록경로, 현재경로) 반환.

    마커 파일이 없거나 해당 machine 줄이 아직 없으면 충돌 없음(None). 감지·보고
    전용이며 자동 조치(수정·병합 등)는 하지 않는다.
    """
    marker_path = _marker_path(tasks_root)
    try:
        lines = marker_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    last_for_machine = _last_marker_path_for_machine(lines, machine)
    if last_for_machine is None:
        return None

    current = os.path.realpath(str(project_dir))
    if os.path.realpath(last_for_machine) == current:
        return None
    return (last_for_machine, current)


def has_legacy_tasks(project_dir: str | Path) -> bool:
    """`project_dir/tasks/*/log.md`가 남아있으면 True(namu-34 이전 구 위치, ⑤).

    이관 여부만 감지하며 자동 이동은 하지 않는다 — 호출자가 안내 문구를 붙인다.
    """
    try:
        return any(Path(project_dir).glob("tasks/*/log.md"))
    except OSError:
        return False
