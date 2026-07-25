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
    존재하면 True.

    ⚠️ context.*.md가 있는 task에서는 더 이상 이 함수가 단독으로 닫힘을 결정하지
    않는다(_is_closed 참고) — context 파일이 없는 **레거시 task 전용 폴백**이다.
    이유(namu-50 실물 사례): `[완료]` 태그는 진짜 종료뿐 아니라 유닛/마일스톤
    완료에도 흔히 쓰인다("[완료] 코어 이음새 완료" 등). 그래서 이 태그의
    "구간 내 존재 여부"만으로 판정하면, 열심히 작업해 마일스톤 [완료]가 쌓인
    진행 중 task일수록 오히려 "닫힘"으로 오판된다. `## ▶ 다음`의 `(완료)`는
    `/namu-task` 절차가 진짜 종료 시점에만 박는 신호라 더 신뢰할 수 있으므로,
    context가 있으면 그쪽을 권위로 쓴다.

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
    """닫힘 판정 권위: context가 있으면 context, 없으면(레거시) log 폴백.

    (namu-50 개정) 예전엔 log의 [완료]가 단독으로 닫힘을 결정했으나(_log_says_closed
    참고), [완료] 태그가 마일스톤 완료에도 쓰여 과부하됐다 — 마일스톤 [완료]가
    쌓인 진행 중 task일수록 "닫힘"으로 오판되는 버그가 있었다. `## ▶ 다음`의
    `(완료)`는 `/namu-task` 절차가 모든 완료조건이 충족된 진짜 종료 시점에만
    박는 신호이고 마일스톤은 이걸 건드리지 않으므로, context 파일이 있으면
    이쪽을 유일한 권위로 쓴다. context 파일이 하나도 없는 레거시 task만
    log 폴백을 쓴다.
    """
    if list(task_dir.glob("context.*.md")):
        return _all_contexts_done(task_dir)
    return _log_says_closed(task_dir / "log.md")


def find_active_task(tasks_dir: Path) -> tuple[str, str] | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 진행 중 task의 (폴더명, 제목) 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if not _is_closed(task_dir):
            title = _extract_task_title(task_dir / "task.md")
            return (task_dir.name, title)

    return None


def find_open_tasks(tasks_dir: Path) -> list[Path]:
    """tasks_dir의 '열린'(닫히지 않은) task 폴더 전부를 최근 활동순으로 반환.

    `find_active_task`는 이 목록의 첫 번째만 뽑아 "진행 중 1개"로 단정했는데,
    실측상 열린 task가 6개인데도 1개만 보이는 게 브리핑이 계속 빗나간 원인이었다
    (namu-57 증상 A). 목록을 그대로 넘겨 호출자가 전부 보여주게 한다.
    """
    return [d for d in _sorted_task_dirs(tasks_dir) if not _is_closed(d)]


def next_note(task_dir: Path) -> str | None:
    """해당 task의 "다음 할 일" 한 줄. 없으면 None.

    권위는 log.md의 마지막 `[다음]` 태그 줄이다(namu-57 1-4) — 별도 파일
    관리 없이 append-only 로그 한 곳에만 남기면 되므로 실제로 기록된다.
    `context.<machine>.md`의 `## ▶ 다음`은 **읽기 폴백**으로만 남긴다(기존 40개
    호환, 신규 생성은 중단). `(완료)` 표기는 다음 할 일이 아니므로 제외한다.
    """
    entries = []
    try:
        lines = (task_dir / "log.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        parsed = _parse_log_line(line)
        if parsed is not None and parsed["tag"] == "다음" and parsed["text"]:
            entries.append(parsed["text"])
    if entries:
        return entries[-1]

    try:
        context_files = sorted(task_dir.glob("context.*.md"))
    except OSError:
        return None
    for ctx_path in context_files:
        try:
            body = _extract_next_section(ctx_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if body and body.strip() != "(완료)":
            return body.strip()
    return None


def open_tasks_briefing(projects: list[str] | None = None) -> list[dict[str, str | None]]:
    """열린 task 전부 + 재진입 지점(next)을 project와 함께 묶어 최근 활동순으로 반환한다.

    (namu-57 2단계 보완) 웹에는 세션 훅이 없어 로컬 브리핑 코드(scripts/
    namu_active_task.py `_collect`가 하던 일)를 도구(namu_recall)로도 그대로
    내보내야 한다 — 로직 이중 구현을 피하려고 이 함수 하나에 모았다.

    `projects`가 None이면 개인 풀의 모든 프로젝트(`list_projects()`)를 합친다
    (namu_search bowl='tasks'의 project=None/웹 기본값과 같은 "전체 합침" 의미).
    항목이 하나뿐인 리스트를 주면 그 프로젝트 하나만 본다(stdio 기본값 등).

    반환 항목: `{"project", "slug", "title", "last_ts", "next"}`. `next`는
    자르지 않은 전문이다(잘리면 재진입 지점 의미가 없어진다) — 없으면 None.
    """
    if projects is None:
        projects = list_projects()

    rows: list[dict[str, str | None]] = []
    for project in projects:
        tasks_dir = tasks_root_for(project)
        project_name = tasks_dir.name
        for task_dir in find_open_tasks(tasks_dir):
            ts = _latest_log_ts(task_dir / "log.md")
            rows.append(
                {
                    "project": project_name,
                    "slug": task_dir.name,
                    "title": _extract_task_title(task_dir / "task.md"),
                    "last_ts": f"{ts[0]} {ts[1]}" if ts else None,
                    "next": next_note(task_dir),
                }
            )

    rows.sort(key=lambda r: r["last_ts"] or "", reverse=True)
    return rows


def find_latest_closed_task(tasks_dir: Path) -> Path | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 '닫힌' task 폴더 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if _is_closed(task_dir):
            return task_dir

    return None


def tasks_root_for(project_dir: str | Path) -> Path:
    """tasks 저장 루트 = 개인 풀 `~/.namu/tasks/<basename(project_dir)>/` (namu-34).

    규칙 한 줄, 특례 0 — 메모리 데이터 루트(cfg.NAMU_DATA_ROOT, 교훈·db 전용)와는
    무관하며 개발 repo(이 repo)도 예외를 두지 않는다. tasks는 여전히 "프로젝트 귀속"
    데이터지만 저장 위치만
    개인 풀로 통합해, PC 간 공유를 개인 전역 동기화에 편승시킨다(공개 repo에
    작업 기록이 노출되는 것도 원천 차단).

    Path.home()은 HOME 환경변수를 존중하므로(POSIX) 테스트는 monkeypatch로
    가짜 HOME을 주입해 실제 ~/.namu를 건드리지 않고 격리할 수 있다.
    """
    key = os.path.basename(str(project_dir).rstrip("/\\"))
    return Path.home() / ".namu" / "tasks" / key


def _tasks_pool_root() -> Path:
    """모든 프로젝트의 tasks가 모이는 개인 풀 루트 `~/.namu/tasks/`."""
    return Path.home() / ".namu" / "tasks"


def list_projects() -> list[str]:
    """개인 풀에 tasks가 쌓인 프로젝트 이름 목록(`~/.namu/tasks/` 하위 폴더명, 정렬)."""
    try:
        return sorted(p.name for p in _tasks_pool_root().iterdir() if p.is_dir())
    except OSError:
        return []


# `[태그] YYYY-MM-DD [HH:MM:SS] [<machine> ·] <내용>`
# 실물 log.md는 시각·machine이 빠진 변주가 섞여 있어(namu-51: 시각만, namu-39: machine 생략)
# 뒤쪽 두 조각은 선택이다. 형식을 강제하는 대신 관대하게 읽고, 없는 값은 None으로 둔다.
_LOG_LINE_RE = re.compile(
    r"^\[(?P<tag>[^\]]*)\]\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+(?P<time>\d{2}:\d{2}:\d{2}))?"
    r"(?:\s+(?P<rest>.*))?$"
)

# machine으로 인정할 토큰: 공백 없는 짧은 낱말(hp, samsung, web …).
# 본문에도 `·`가 흔히 쓰이므로, 앞 조각이 이 모양일 때만 machine으로 본다
# (`[완료] ... 코어 · 이음새` 같은 줄에서 "코어"를 machine으로 오인하지 않기 위함).
_MACHINE_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


def _split_machine(rest: str) -> tuple[str | None, str]:
    """log 줄의 타임스탬프 뒤 나머지에서 (machine, text)를 분리."""
    head, sep, tail = rest.partition("·")
    if sep and _MACHINE_RE.match(head.strip()):
        return (head.strip(), tail.strip())
    return (None, rest.strip())


# 본문 끝의 `(via <라벨>)` 꼬리표 — 2단위에서 웹이 log에 남길 형식(namu-50):
# `[결정] 2026-07-25 15:40:00 web · 내용 (via claude)`. 라벨은 machine과 같은
# 폭의 짧은 낱말 패턴을 쓰되 웹 클라이언트명(예: chatgpt-web)까지 감안해 40자로 둔다.
_VIA_RE = re.compile(r"\(via\s+([A-Za-z0-9._-]{1,40})\)\s*$")


def _split_via(text: str) -> tuple[str | None, str]:
    """본문 끝의 `(via <라벨>)` 꼬리표를 분리해 (via, 나머지 text)로 반환.

    꼬리표가 없으면 (None, text 그대로)."""
    match = _VIA_RE.search(text)
    if not match:
        return (None, text)
    return (match.group(1), text[: match.start()].rstrip())


def _parse_log_line(line: str) -> dict[str, str | None] | None:
    """log.md 한 줄 → {ts, tag, machine, via, text}. 날짜가 없는 줄이면 None.

    ts는 항상 `YYYY-MM-DD HH:MM:SS`로 정규화한다(시각 누락은 00:00:00) — 문자열
    사전순 비교가 곧 시간순이 되어 정렬·범위 필터가 파싱 없이 성립한다.

    via는 본문 끝의 `(via <라벨>)` 꼬리표에서 뽑는다(namu-50, 어느 AI/클라이언트가
    남겼는지 구분하는 축). 꼬리표가 없으면 None이고, text에서는 꼬리표가 제거된다.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None
    time_str = match.group("time") or "00:00:00"
    machine, text = _split_machine(match.group("rest") or "")
    via, text = _split_via(text)
    return {
        "ts": f"{match.group('date')} {time_str}",
        "tag": match.group("tag"),
        "machine": machine,
        "via": via,
        "text": text,
    }


def _normalize_bound(value: str, *, end: bool) -> str:
    """since/until 인자를 ts와 같은 폭(`YYYY-MM-DD HH:MM:SS`)으로 맞춘다.

    날짜만 준 경우 since는 그날 00:00:00, until은 그날 23:59:59로 확장한다 —
    `until='2026-07-25'`가 그날 기록을 잘라내지 않도록(사용자 직관 우선).
    """
    value = value.strip()
    if len(value) <= 10:
        return f"{value} 23:59:59" if end else f"{value} 00:00:00"
    return value


def _task_matches(slug: str, task: str) -> bool:
    """task 필터: 폴더명 완전 일치 또는 `namu-49`처럼 앞부분(슬러그 접두)만 지목."""
    return slug == task or slug.startswith(f"{task}-")


def journal(
    project: str | None = None,
    since: str | None = None,
    until: str | None = None,
    machine: str | None = None,
    task: str | None = None,
    via: str | None = None,
    limit: int | None = None,
) -> list[dict[str, str | None]]:
    """모든 log.md의 날짜 붙은 줄을 합쳐 시간순(최신 우선) 통합 뷰로 반환한다.

    반환 항목: `{ts, project, task_slug, tag, machine, via, text}`.

    via는 본문 끝 `(via <라벨>)` 꼬리표에서 뽑은 출처 라벨(namu-50, 어느 AI가
    남겼는지 구분하는 축)이다. via를 주면 그 라벨과 정확히 일치하는 줄만 남긴다.

    파일은 손대지 않고 **읽을 때 합친다**(log.md가 권위, 원칙 #2). task 경계를 넘어
    시간순으로 세우므로 "어제 무슨 일이 있었나"가 추측 없이 답된다.

    project를 생략하면 개인 풀의 모든 프로젝트를 합친다(웹에서 프로젝트를 몰라도
    조회 가능). 값을 주면 basename만 키로 쓰므로 이름(`namu-agent`)이든 경로든
    동일하게 동작한다(`tasks_root_for`와 같은 규칙, 특례 0).

    stdlib 전용 유지 — statusline(plain python3)과 공유하는 모듈이다.
    """
    if project is None:
        targets = [(name, _tasks_pool_root() / name) for name in list_projects()]
    else:
        root = tasks_root_for(project)
        targets = [(root.name, root)]

    since_bound = _normalize_bound(since, end=False) if since else None
    until_bound = _normalize_bound(until, end=True) if until else None

    entries: list[dict[str, str | None]] = []
    for project_name, tasks_root in targets:
        try:
            log_files = list(tasks_root.glob("*/log.md"))
        except OSError:
            continue

        for log_path in log_files:
            task_slug = log_path.parent.name
            if task is not None and not _task_matches(task_slug, task):
                continue
            try:
                lines = log_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for line in lines:
                parsed = _parse_log_line(line)
                if parsed is None:
                    continue
                ts = parsed["ts"]
                if since_bound is not None and ts < since_bound:
                    continue
                if until_bound is not None and ts > until_bound:
                    continue
                if machine is not None and parsed["machine"] != machine:
                    continue
                if via is not None and parsed["via"] != via:
                    continue
                entries.append(
                    {
                        "ts": ts,
                        "project": project_name,
                        "task_slug": task_slug,
                        "tag": parsed["tag"],
                        "machine": parsed["machine"],
                        "via": parsed["via"],
                        "text": parsed["text"],
                    }
                )

    entries.sort(key=lambda e: (e["ts"], e["project"], e["task_slug"]), reverse=True)
    if limit is not None:
        entries = entries[:limit]
    return entries


def resolve_active_task(ws: str) -> tuple[str, str] | None:
    """statusline용: 현재 프로젝트(ws) 기준으로 tasks 루트 계산 후 active task 반환.

    tasks 저장 위치는 개인 풀(`tasks_root_for(ws)` = `~/.namu/tasks/<basename(ws)>/`,
    namu-34)이며, 메모리 루트(cfg.NAMU_DATA_ROOT)와는 무관하게 ws의 폴더명만 키로 쓴다
    (namu-35: NAMU_HOME 환경변수 자체가 폐지됐으므로 설정해도 애초에 아무 효과가 없다
    — statusLine은 항상 "지금 이 프로젝트"의 tasks를 본다). ws가 비어있을 때만
    탐지 불가로 None을 반환하는 안전 폴백을 둔다.
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
