# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp[cli]>=1.28,<2", "python-ulid>=3.0.0", "PyYAML>=6.0", "python-dotenv>=1.0.0", "tzdata>=2024.1"]
# ///
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import config as cfg
import memory_sync
import profile
import task_resolve
from mcp.server.fastmcp import Context, FastMCP
from db import init_db, rebuild_from_yaml, record, cache_is_stale
from db import recall as _recall
from db import search_bowl as _search_bowl

mcp = FastMCP("namu-memory")


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(cfg.NAMU_DB_PATH)


def _ensure_db() -> None:
    if not cfg.NAMU_DB_PATH.exists() or cache_is_stale(cfg.LEARNINGS_YAML_PATH, cfg.NAMU_DB_PATH):
        rebuild_from_yaml()


def _ensure_tasks_gitattributes() -> None:
    """기존 개통분(hp·samsung)의 `~/.namu/.gitattributes`에 tasks union 라인을
    멱등 ensure한다(namu-34 ③-c). 신규 개통은 namu_sync_setup이 이미 챙기므로,
    이건 "sync_setup을 다시 부르지 않는 기존 사용자"를 위한 보정이다.

    대상은 항상 `Path.home()/".namu"`다(tasks 개인 풀 규칙과 동일 근거, namu-34 ①
    — namu-35 이후로는 cfg.NAMU_DATA_ROOT와도 같은 경로). `.git`이 없으면(미개통)
    완전 스킵하고, 그 외 모든 실패도 서버 부팅을 절대 막으면 안 되므로 전예외
    무해 처리한다.
    """
    try:
        home = Path.home() / ".namu"
        if (home / ".git").exists():
            memory_sync.ensure_gitattributes_union(home)
    except Exception:
        pass


_ensure_db()
_ensure_tasks_gitattributes()


_VIA_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

_VIA_ERROR_MSG = (
    "출처(client) 식별값이 없거나 형식이 올바르지 않습니다 — 주소 끝에 "
    "?client=<AI 이름>을 붙이고, 사용하는 AI 이름을 정확히 넣으세요. "
    "예: claude, chatgpt, gemini, cursor, copilot. 애칭·약칭도 되지만, 나중에 "
    "'그 AI가 남긴 기억'을 조회하려면 입력했던 값과 똑같이 넣어야 찾을 수 있습니다 "
    "(claude 와 cld 는 서로 다른 값으로 저장됨).  |  Missing/invalid 'client': "
    "append ?client=<your-ai-name> (e.g. claude, chatgpt, gemini). Use the exact "
    "same value later to look up that AI's memories."
)


def _resolve_via(ctx: Context | None) -> str | None:
    """URL 쿼리(`?client=`)에서 출처(via) 태그를 읽어 검증한다(namu-50).

    stateless HTTP(웹) 경로에서만 request가 도달하므로, req가 None이면(stdio/직접
    호출/테스트) 검증을 완전히 면제하고 None을 반환한다 — 기존 로컬 동작을 절대
    바꾸지 않기 위함이다.
    """
    if ctx is None:
        return None
    req = getattr(getattr(ctx, "request_context", None), "request", None)
    if req is None:
        return None
    client = (req.query_params.get("client") or "").strip()
    if not _VIA_RE.match(client):
        raise ValueError(_VIA_ERROR_MSG)
    return client


def _is_web_request(ctx: Context | None) -> bool:
    """stateless HTTP(웹) 요청인지 판별. request가 도달하면 웹, None이면 stdio/
    직접호출/테스트다 — `_resolve_via`가 쓰는 것과 같은 판정 기준을 재사용한다
    (namu-57 2단계 2단위: project 기본값을 stdio/웹으로 분기하는 데 쓴다)."""
    if ctx is None:
        return False
    req = getattr(getattr(ctx, "request_context", None), "request", None)
    return req is not None


def _default_search_project(ctx: Context | None) -> str | None:
    """namu_search(bowl='tasks')에서 project 생략 시 기본값(namu-57 2단계 2단위).

    stdio(로컬 CC/agy)는 "지금 이 프로젝트"를 묻는 게 자연스러우므로 cwd 폴더명을
    쓴다. 웹은 cwd 개념이 없으므로 None을 그대로 유지해 전체 프로젝트를 합친다
    (task_resolve.journal의 기존 동작).
    """
    if _is_web_request(ctx):
        return None
    return cfg.tasks_dir_for().name


def _resolve_recall_project(project: str | None, ctx: Context | None) -> str | None:
    """namu_recall(bowl='tasks' 부분)용 project 기본값 — namu_search와 완전히 같은
    규칙(_default_search_project 재사용)이다(namu-57 2단계 보완). 조회 경로라
    project='*'를 명시 전체 조회로 허용한다(_resolve_record_project과 다른 점).
    """
    if project == "*":
        return None
    if project is None:
        return _default_search_project(ctx)
    return project


def _resolve_record_project(project: str | None, ctx: Context | None) -> str:
    """namu_record(bowl='tasks')용 project 정규화. 기록은 반드시 프로젝트 하나에
    쓰므로(namu-57 2단계 2단위) '*'(전체)는 허용하지 않는다 — 조회(namu_search)와
    다른 점.
    """
    if project == "*":
        raise ValueError(
            "project='*'는 기록에 쓸 수 없습니다 — 기록은 프로젝트 하나를 명시해야 합니다"
        )
    if project is not None:
        return project
    if _is_web_request(ctx):
        raise ValueError(
            "웹에서 tasks 기록은 project를 명시해야 합니다(cwd 개념이 없습니다). "
            "예: project='namu-agent'"
        )
    return cfg.tasks_dir_for().name


def _resolve_task_slug(project: str, task: str | None) -> str:
    """task 인자를 폴더명(슬러그)으로 정규화한다. 폴더명 완전일치 우선, 없으면
    `namu-57`처럼 앞부분만 준 접두 일치로 찾는다(task_resolve._task_matches와
    같은 규칙). 없는 슬러그로 폴더를 새로 만들지 않는다 — task.md(목적) 없이
    log만 생기면 유령 task가 된다.
    """
    if not task or not task.strip():
        raise ValueError("task(슬러그)는 필수입니다")
    task = task.strip()

    tasks_root = task_resolve.tasks_root_for(project)
    try:
        candidates = sorted(d.name for d in tasks_root.iterdir() if d.is_dir())
    except OSError:
        candidates = []

    exact = [c for c in candidates if c == task]
    if exact:
        return exact[0]

    prefix = [c for c in candidates if c.startswith(f"{task}-")]
    if len(prefix) == 1:
        return prefix[0]

    open_slugs = [d.name for d in task_resolve.find_open_tasks(tasks_root)]
    hint = f" (열린 task: {', '.join(open_slugs)})" if open_slugs else " (열린 task 없음)"
    if not prefix:
        raise ValueError(
            f"프로젝트 {project!r}에서 task {task!r}를 찾을 수 없습니다{hint}"
            " — 새로 만들려면 create=True와 purpose를 함께 주세요"
        )
    raise ValueError(
        f"task {task!r}가 여러 후보와 일치합니다: {', '.join(prefix)}{hint} — 더 구체적으로 지정하세요"
    )


def _validate_task_tag_text(tag: str | None, text: str | None) -> tuple[str, str]:
    """tag/text 입력 정리: strip, 빈 값 거절, tag에 ']'·개행 금지, text 개행은
    공백으로 접어 한 줄로 만든다(log.md는 줄 단위 파일이라 여러 줄이 들어가면
    파싱이 깨진다). tag 생략(None) 시 기본값 '기록'.
    """
    tag = "기록" if tag is None else tag.strip()
    text = (text or "").strip()
    if not tag:
        raise ValueError("tag는 빈 값일 수 없습니다")
    if "]" in tag or "\n" in tag or "\r" in tag:
        raise ValueError("tag에는 ']'나 개행을 쓸 수 없습니다")
    if not text:
        raise ValueError("text는 필수입니다(빈 값 불가)")
    text = " ".join(text.split())
    return tag, text


def _append_task_log_line(task_dir: Path, line: str) -> None:
    """log.md에 한 줄 append(union merge로 여러 곳에서 동시 append해도 충돌 0).
    파일이 개행으로 끝나지 않으면 먼저 개행을 넣어 줄 경계를 지킨다.
    """
    log_path = task_dir / "log.md"
    needs_leading_nl = False
    if log_path.exists():
        with log_path.open("rb") as f:
            f.seek(0, 2)
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_leading_nl = f.read(1) != b"\n"
    with log_path.open("a", encoding="utf-8") as f:
        if needs_leading_nl:
            f.write("\n")
        f.write(line + "\n")


def _record_task_entry(
    project: str | None,
    task: str | None,
    text: str | None,
    tag: str | None,
    via: str | None,
    ctx: Context | None,
) -> str:
    """bowl='tasks' 경로: log.md에 한 줄 append하고 그 줄을 반환한다."""
    resolved_project = _resolve_record_project(project, ctx)
    slug = _resolve_task_slug(resolved_project, task)
    tag, text = _validate_task_tag_text(tag, text)

    # 실제 시계 — 지어 쓰면 PC 간 선후가 뒤집힌다. 단 "현지시각 그대로"도 안 된다:
    # 시간대가 다른 호스트(웹 컨테이너=UTC)가 끼면 같은 파일 안에서 시각 비교가 깨진다.
    # 그래서 기준 시간대로 통일한 시계를 쓴다(cfg.now, namu-57 5단계).
    ts = cfg.now().strftime("%Y-%m-%d %H:%M:%S")
    machine = cfg.NAMU_MACHINE
    line = f"[{tag}] {ts} {machine} · {text}"
    if via:
        line += f" (via {via})"

    task_dir = task_resolve.tasks_root_for(resolved_project) / slug
    _append_task_log_line(task_dir, line)
    return line


_NEW_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _validate_new_task_slug(task: str | None) -> str:
    """create=True용 새 슬러그 검증(namu-57 2단계 보완). 폴더명으로 안전한 문자만
    허용해 경로 조작(`/`, `\\`, `..`, 절대경로 등)을 원천 차단한다 — 정규식이
    영문/숫자/하이픈/언더스코어만 통과시키므로 `/`나 `..`는 애초에 매치되지 않는다.
    """
    task = (task or "").strip()
    if not task:
        raise ValueError("task(슬러그)는 필수입니다")
    if not _NEW_SLUG_RE.match(task):
        raise ValueError(
            f"task 슬러그 {task!r}가 올바르지 않습니다 — 영문/숫자/하이픈(-)/언더스코어(_)만 "
            "허용되고 첫 글자는 영문/숫자여야 합니다(경로 문자 금지: '/', '\\\\', '..' 등)"
        )
    return task


def _create_task_entry(
    project: str | None,
    task: str | None,
    title: str | None,
    purpose: str | None,
    done_when: list[str] | None,
    via: str | None,
    ctx: Context | None,
) -> str:
    """bowl='tasks', create=True 경로: 새 task 폴더(task.md+log.md)를 만들고
    `[시작]` 줄을 append한다. `context.<machine>.md`는 만들지 않는다(namu-57 신규
    생성 중단). SKILL.md '파일 템플릿' 절의 형식을 그대로 따른다.
    """
    resolved_project = _resolve_record_project(project, ctx)
    slug = _validate_new_task_slug(task)

    purpose = (purpose or "").strip()
    if not purpose:
        raise ValueError(
            "create=True일 때 purpose는 필수입니다(목적 없는 task는 나중에 아무도 못 읽습니다)"
        )

    task_dir = task_resolve.tasks_root_for(resolved_project) / slug
    if task_dir.exists():
        raise ValueError(
            f"task {slug!r}는 프로젝트 {resolved_project!r}에 이미 있습니다 — 덮어쓸 수 "
            "없습니다(task.md는 불변 목적, log.md는 append-only). 기존 task에 기록하려면 "
            "create=False로 호출하세요"
        )

    display_title = (title or slug).strip() or slug
    machine = cfg.NAMU_MACHINE
    today = cfg.now().strftime("%Y-%m-%d")

    if done_when:
        done_when_lines = "\n".join(f"- [ ] {item}" for item in done_when)
    else:
        done_when_lines = "- [ ] ..."

    task_md = (
        f"# {slug} — {display_title}\n"
        f"📅 생성 {today} [{machine}] · 🔗 관련: __\n"
        "\n"
        "## 목적\n"
        f"{purpose}\n"
        "\n"
        "## 완료조건\n"
        f"{done_when_lines}\n"
    )
    log_md = f"# log — {slug}\n(append만. 이 파일이 이 task의 권위 있는 기록이다)\n\n"

    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(task_md, encoding="utf-8")
    (task_dir / "log.md").write_text(log_md, encoding="utf-8")

    ts = cfg.now().strftime("%Y-%m-%d %H:%M:%S")
    start_line = f"[시작] {ts} {machine} · 작업 생성, 목적·완료조건 확정"
    if via:
        start_line += f" (via {via})"
    _append_task_log_line(task_dir, start_line)

    return f"task 생성됨: {task_dir}\n{start_line}"


_KIND_TO_BOWL = {"lesson": "learnings", "note": "learnings", "fact": "profile"}
_VALID_RECORD_BOWLS = ("learnings", "tasks", "profile")


def _resolve_record_bowl(bowl: str | None, kind: str) -> str:
    """bowl 인자 해석(namu-57 2단계 2단위). bowl=None이면 기존 kind에서 유도한다
    (fact→profile, lesson/note→learnings) — 기존 호출은 100% 그대로 동작한다.
    bowl을 명시했는데 kind와 모순되면(예: bowl='learnings'+kind='fact') 즉시
    ValueError로 드러낸다. bowl='tasks'는 kind와 무관하다(kind는 tasks 경로에서
    쓰지 않는다).
    """
    if bowl is None:
        inferred = _KIND_TO_BOWL.get(kind)
        if inferred is None:
            raise ValueError("kind는 'lesson'/'note'/'fact' 중 하나여야 합니다")
        return inferred
    if bowl not in _VALID_RECORD_BOWLS:
        raise ValueError(f"bowl은 {list(_VALID_RECORD_BOWLS)} 중 하나여야 합니다: {bowl!r}")
    if bowl == "tasks":
        return bowl
    inferred = _KIND_TO_BOWL.get(kind)
    if inferred is not None and inferred != bowl:
        raise ValueError(
            f"bowl={bowl!r}과 kind={kind!r}가 모순됩니다(kind={kind!r}는 {inferred!r} 그릇입니다)"
        )
    return bowl


def _normalize_tags(tags: list[str] | str | None) -> list[str] | None:
    if tags is None or isinstance(tags, list):
        return tags
    # str 경로
    stripped = tags.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return [tags]


@mcp.tool()
def namu_recall(
    query: str | None = None,
    task_type: str | None = None,
    limit: int = 5,
    project: str | None = None,
    ctx: Context | None = None,
):
    """Load relevant past memory BEFORE starting a task (context loading).
    Use at task/session start to recall how similar work went before and what
    facts/preferences are on file. Returns something useful even on weak
    matches: if the query matches nothing, learnings falls back to the most
    recent entries. For warming up context, not precise analysis. For
    pattern/trend analysis use namu_search instead.

    ALSO call this whenever the user asks something like "what's left to do" /
    "let's continue" / "where were we" — on the web there is no session hook
    to auto-brief you, so this tool's `tasks` field IS the briefing: it lists
    every currently-open task and its exact re-entry point. For a scrollback
    of recent activity lines (not just the resume point) use namu_search
    instead (bowl='tasks').

    Args:
      query: topic keywords (optional; omit to get the most recent learnings)
      task_type: filter by code/doc/analysis/other (optional; learnings only)
      limit: max learnings entries (default 5, small for token efficiency)
      project: which project's open tasks to include (folder name, e.g.
        'namu-agent'). Omit for the same default as namu_search(bowl='tasks'):
        "current project" on stdio (has a cwd), "all projects merged" on the
        web (no cwd there). project='*' forces "all projects" explicitly on
        either side.
    Returns: three-bowl dict —
      {"profile": [...active facts/preferences, all of them, no limit...],
       "learnings": [...lesson/note dicts: timestamp, task, outcome, reason,
       kind, tags, ...],
       "tasks": [...every OPEN task, most-recent-activity first: {"project",
       "slug", "title", "last_ts", "next"}, where `next` is the full,
       untruncated re-entry point (the task's last `[다음]` log line) or None
       if it was never left with one...]}
    """
    _resolve_via(ctx)
    _ensure_db()
    resolved_project = _resolve_recall_project(project, ctx)
    projects = [resolved_project] if resolved_project is not None else None
    with closing(get_conn()) as conn:
        return {
            "profile": profile.active(),
            "learnings": _recall(conn, query, task_type, limit),
            "tasks": task_resolve.open_tasks_briefing(projects),
        }


@mcp.tool()
def namu_search(
    query: str | None = None,
    bowl: str = "learnings",
    project: str | None = None,
    task: str | None = None,
    machine: str | None = None,
    via: str | None = None,
    since: str | None = None,
    until: str | None = None,
    outcome_filter: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
):
    """Search one of THREE memory bowls with precise axis filters (analytical
    lookup during judgment — for fuzzy context warming use namu_recall instead).

    Bowls (`bowl`):
      - 'learnings' (default): task outcomes/reasons/notes. Adds a trend
        summary {success/failure/partial counts}.
      - 'tasks': project work-log lines (log.md, merged across machines).
        `project` picks a project by folder name (e.g. 'namu-agent'); omit
        it to default to "here" on stdio or "all projects merged" on the
        web (no cwd there). `project='*'` forces "all projects" explicitly
        on either side.
      - 'profile': facts/preferences.

    `query` is optional everywhere — omit it to filter by axes alone (e.g.
    "what did I do yesterday on hp" = bowl='tasks', machine='hp',
    since='2026-07-24'). Other axes: task (substring), machine/via (exact),
    since/until (date or datetime, inclusive).

    Examples:
      namu_search(bowl='tasks', machine='hp', since='2026-07-24')
      namu_search(query='timeout', bowl='learnings', outcome_filter='failure')
      namu_search(bowl='tasks', project='namu-agent', task='namu-57')

    Returns: {"bowl", "results": [...], "count": N[, "summary": {...} (learnings only)]}
    """
    _resolve_via(ctx)
    _ensure_db()
    if bowl == "tasks":
        if project == "*":
            project = None
        elif project is None:
            project = _default_search_project(ctx)
    with closing(get_conn()) as conn:
        return _search_bowl(
            conn,
            bowl=bowl,
            query=query,
            project=project,
            task=task,
            machine=machine,
            via=via,
            since=since,
            until=until,
            outcome_filter=outcome_filter,
            limit=limit,
        )


@mcp.tool()
def namu_record(
    task: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    task_type: str = "other",
    verified_by: str = "ai",
    tags: list[str] | None = None,
    kind: str = "lesson",
    subject: str | None = None,
    statement: str | None = None,
    source: str | None = None,
    supersedes: str | None = None,
    bowl: str | None = None,
    project: str | None = None,
    text: str | None = None,
    tag: str | None = None,
    create: bool = False,
    title: str | None = None,
    purpose: str | None = None,
    done_when: list[str] | None = None,
    ctx: Context | None = None,
):
    """Append-only record into one of THREE memory bowls. Pick `bowl`
    explicitly, or omit it and it's inferred from `kind` (100% backward
    compatible — existing lesson/note/fact calls need no change). Explicit
    `bowl` that contradicts `kind` (e.g. bowl='learnings'+kind='fact')
    raises ValueError immediately.

    bowl='learnings' (kind='lesson'|'note', default): a task outcome+reason
      (lesson) or a conversation snippet (note) → learnings.yaml. Required:
      task, reason (non-empty). lesson also requires outcome
      ('success'/'failure'/'partial'); note's outcome is optional. Trigger:
      lesson = your own judgment there's a generalizable pattern; note =
      only when the user explicitly asks to remember the conversation.

    bowl='profile' (kind='fact'): a fact/preference → profile.yaml (no
      SQLite cache). Required: subject, statement, source (non-empty — WHY
      you know this). `supersedes`=<old id> corrects a prior fact
      (append-only, never edited in place). Soft policy: propose to the
      user first ("should I remember this?").

    bowl='tasks' (namu-57 2단계, new): one project work-log line →
      that task's log.md (git merge=union — safe to append from anywhere,
      including the web). Required: project (folder name, e.g.
      'namu-agent'; on stdio omit for "current project", on the web it's
      MANDATORY — no cwd there), task (slug or unique prefix like
      'namu-57'; must already exist, this never creates a task folder unless
      create=True — 0/2+ matches raise ValueError listing open
      tasks/candidates and, for the 0-match case, a hint to pass
      create=True), text (the note, newlines collapsed to spaces). tag
      defaults to '기록' (must not contain ']' or a newline). Line format:
      `[tag] YYYY-MM-DD HH:MM:SS <machine> · text`.
      WARNING: tags '[완료]'/'[중단]' mean the WHOLE TASK is closing and
      drop it from open-task briefings — never use them for a mid-task
      progress note (this caused real incidents twice).

    bowl='tasks', create=True (namu-57 2단계 보완, new): create a brand-new
      task folder instead of appending to an existing one — this is how the
      web starts new work (e.g. design sessions) since it has no local
      /namu-task skill. Required: project (same rule as above), task (the
      new slug — folder-name-safe chars only: letters/digits/hyphen/
      underscore, first char alphanumeric; '/', '\\', '..' etc. are
      rejected), purpose (non-empty — WHY this task exists; nobody can make
      sense of a task with no purpose later). Optional: title (defaults to
      the slug), done_when (list of completion-condition strings rendered
      as an unchecked checklist). Raises ValueError if the slug already
      exists (task.md is an immutable purpose statement, log.md is
      append-only — creation never overwrites). Writes task.md + log.md
      following the SKILL.md templates (no context.<machine>.md — that
      legacy file is no longer created), appends a `[시작]` line, and
      returns a human-readable string with the created path and that line.

    id/timestamp/machine are filled in by the server for every bowl.
    Returns: ULID str (learnings/profile) or the appended log line / task
    creation summary (tasks).
    """
    # namu-38: samsung 라이브 실측에서 record 직후 git 단계까지 12분 공백이
    # 관측됐다 — ensure_db(캐시 재생성)/record(yaml+sqlite)/sync(git push) 세 구간
    # 중 어디서 지연이 생기는지 판정하려면 구간별 시간이 반드시 필요하다. db.py는
    # 코어라 침습을 최소화하고, record()는 전체 구간 하나로만 잰다.
    via = _resolve_via(ctx)
    t0 = time.perf_counter()
    _ensure_db()
    t1 = time.perf_counter()

    resolved_bowl = _resolve_record_bowl(bowl, kind)

    if resolved_bowl == "tasks":
        if create:
            result = _create_task_entry(project, task, title, purpose, done_when, via, ctx)
        else:
            result = _record_task_entry(project, task, text, tag, via, ctx)
        t2 = time.perf_counter()
        memory_sync.sync_push(f"task: {task} ({cfg.NAMU_MACHINE})")
        t3 = time.perf_counter()
        memory_sync._append_sync_log(
            f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
        )
        return result

    if resolved_bowl == "learnings":
        entry_id = record(
            task, outcome, reason, task_type, verified_by, _normalize_tags(tags), kind=kind,
            via=via,
        )
    else:  # profile
        vb = verified_by if verified_by in ("human", "ai", "unverified") else "human"
        entry_id = profile.record_fact(
            subject, statement, source, supersedes=supersedes,
            verified_by=vb, tags=_normalize_tags(tags), via=via,
        )
    t2 = time.perf_counter()
    # 설치형(~/.namu) 자동 동기화 활성 시에만 실제 push가 일어난다(sync_enabled 하드가드).
    # 반환값이 False여도(비활성/실패) record 자체의 성공 결과에는 영향을 주지 않는다.
    label = (task or statement or subject or "")[:50]
    memory_sync.sync_push(f"learn: {label} ({cfg.NAMU_MACHINE})")
    t3 = time.perf_counter()
    memory_sync._append_sync_log(
        f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
    )
    return entry_id


@mcp.tool()
def namu_sync_setup(remote_url: str) -> str:
    """Enable git auto-sync for the standalone (~/.namu) learnings install.

    Wires up local git (init/.gitignore/.gitattributes/remote/marker) so that
    subsequent namu_record calls auto-push and session-start hooks auto-pull.
    The remote git repository itself must already exist and be prepared by the
    user beforehand (e.g. an empty private GitHub repo) — this tool only sets
    up the local side, it does not create the remote.

    Args:
      remote_url: git remote URL to push learnings to
    Returns: human-readable result string (per-step success/failure notes)
    """
    return memory_sync.sync_setup(remote_url)


if __name__ == "__main__":
    mcp.run(transport="stdio")
