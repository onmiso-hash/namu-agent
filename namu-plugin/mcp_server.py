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
import memo
import memory_sync
import profile
import record_input
import task_resolve
from mcp.server.fastmcp import Context, FastMCP
from db import init_db, rebuild_from_yaml, record, cache_is_stale
from db import recall as _recall
from db import search_bowl as _search_bowl

# 소개문(instructions)은 손으로 쓰지 않는다 — 도구 설명과 같은 선언(config.FIELDS)에서
# 만들어야 둘이 갈라지지 않는다(namu-65 후속 ②). http_server.py도 이 인스턴스를 그대로
# 재사용하므로 웹 경로에서도 같은 소개문이 나간다.
mcp = FastMCP("namu-memory", instructions=record_input.server_instructions())


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


# 작업을 닫는 태그는 이 둘뿐이다(task_resolve._log_says_closed가 보는 것도 이 둘).
_CLOSING_TAGS = ("완료", "중단")

# "닫는다"는 뜻으로 흔히 쓰이지만 닫히지 **않는** 말들(namu-66). 실물 로그에서
# '종료' 1건·'마무리' 1건이 나왔고, 그중 namu-37은 기록만 보면 닫힌 적이 없는
# 상태로 남았다 — 옛 형식 파일이 우연히 닫아 주고 있었을 뿐이다.
_CLOSING_SYNONYMS = (
    "종료", "마무리", "끝", "종결", "완결", "닫음", "닫기", "done", "close", "closed", "finish",
)


def _validate_task_tag_text(tag: str | None, text: str | None) -> tuple[str, str]:
    """tag/text 입력 정리: strip, 빈 값 거절, tag에 ']'·개행 금지, text 개행은
    공백으로 접어 한 줄로 만든다(log.md는 줄 단위 파일이라 여러 줄이 들어가면
    파싱이 깨진다). tag 생략(None) 시 기본값 '기록'.

    닫는 뜻의 유의어는 거절한다(namu-66) — 태그는 자유 문자열이라 '종료'라고 적어도
    저장은 성공하지만 판정은 '완료'/'중단'만 보므로, 적은 쪽은 닫았다고 믿고
    목록에는 계속 열려 있는 상태가 된다. 조용히 어긋나느니 그 자리에서 거절하는 게
    낫다("닫았다고 생각했는데 안 닫힘"은 몇 주 뒤에야 발견된다).
    """
    tag = "기록" if tag is None else tag.strip()
    text = (text or "").strip()
    if not tag:
        raise ValueError("tag는 빈 값일 수 없습니다")
    if "]" in tag or "\n" in tag or "\r" in tag:
        raise ValueError("tag에는 ']'나 개행을 쓸 수 없습니다")
    if tag.lower() in _CLOSING_SYNONYMS:
        raise ValueError(
            f"tag={tag!r}는 작업을 닫지 못합니다 — 닫는 말은 '완료'(다 끝냄)와 "
            "'중단'(더 안 함) 둘뿐입니다. 정말 닫는 것이면 그 둘 중 하나로 다시 "
            "적고, 한 단계만 끝난 것이면 '기록'처럼 닫지 않는 말을 쓰세요"
        )
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


# 작업일지 세 줄 묶음(namu-65 4단계). 이어지는 줄은 공백 4칸으로 들여쓴다 —
# 읽는 쪽이 예나 지금이나 "`[`로 시작하는 줄"만 항목으로 세므로, 들여쓴 줄은
# 옛 코드에서도 그냥 무시된다(옛 450줄과 새 줄이 한 파일에 섞여도 안전).
_LOG_INDENT = "    "
_LOG_REASON_LABEL = "왜: "
_LOG_BODY_LABEL = "상세: "


def _log_block(head: str, reason: str | None, body: str | None) -> str:
    """머리줄 + (왜/상세) 이어지는 줄을 한 덩어리로 만든다.

    `생략` 한 단어는 줄 자체를 만들지 않는다 — 화면에서 감추기로 한 값을 파일에
    남겨두면 브리핑이 '왜: 생략'이라는 빈 소리를 하게 된다.
    """
    lines = [head]
    for label, value in ((_LOG_REASON_LABEL, reason), (_LOG_BODY_LABEL, body)):
        value = " ".join((value or "").split())
        if not value or cfg.is_omitted(value):
            continue
        lines.append(f"{_LOG_INDENT}{label}{value}")
    return "\n".join(lines)


def _record_task_entry(
    project: str | None,
    task: str | None,
    text: str | None,
    tag: str | None,
    via: str | None,
    ctx: Context | None,
    reason: str | None = None,
    body: str | None = None,
) -> str:
    """bowl='tasks' 경로: log.md에 한 줄(또는 세 줄 묶음) append하고 그것을 반환한다."""
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
    block = _log_block(line, reason, body)

    task_dir = task_resolve.tasks_root_for(resolved_project) / slug
    _append_task_log_line(task_dir, block)
    return block + _unmet_done_when_warning(task_dir, tag)


def _unmet_done_when_warning(task_dir: Path, tag: str) -> str:
    """닫는 줄인데 task.md에 안 채운 완료조건이 남아 있으면 붙일 경고(namu-66).

    막지 않고 경고만 하는 이유: 이관("남은 몫은 다른 방에서")이나 범위 축소로 닫는
    것은 정당하고 실제로 자주 있다(namu-50). 다만 그때도 "무엇을 안 하고 닫는지"가
    기록에 드러나야 하므로, 조용히 넘어가는 대신 눈에 보이게 한다.

    기록 자체는 이미 append됐다 — 경고 때문에 기록이 사라지면 append-only가 깨진다.
    """
    if tag not in _CLOSING_TAGS:
        return ""
    try:
        lines = (task_dir / "task.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    unmet = [ln.strip()[5:].strip() for ln in lines if ln.strip().startswith("- [ ]")]
    unmet = [u for u in unmet if u and u != "..."]
    if not unmet:
        return ""
    listed = "\n".join(f"  · {u}" for u in unmet[:5])
    more = f"\n  · … 외 {len(unmet) - 5}개" if len(unmet) > 5 else ""
    return (
        f"\n⚠ 안 채운 완료조건 {len(unmet)}개가 남은 채로 [{tag}] 했습니다:\n"
        f"{listed}{more}\n"
        "  정말 충족했다면 task.md의 네모칸을 채우고, 안 하고 닫는 것이라면 "
        "왜 안 하는지를 이 줄에 남기세요(이관·범위 축소는 정당한 종결 사유입니다)."
    )


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
    text: str | None,
    tag: str | None,
    via: str | None,
    ctx: Context | None,
) -> str:
    """bowl='tasks', create=True 경로: 새 task 폴더(task.md+log.md)를 만들고
    `[시작]` 줄을 append한다. `context.<machine>.md`는 만들지 않는다(namu-57 신규
    생성 중단). SKILL.md '파일 템플릿' 절의 형식을 그대로 따른다.

    namu-62 ③: text(+tag)를 함께 주면 `[시작]` 다음 줄로 그것까지 append한다.
    예전에는 이 두 인자를 **조용히 버려서** 생성 직후 `[다음]`이 빈 task가
    남았고(실측 2건), 브리핑이 "다음: (기록 없음)"으로 떠 다음 세션이 이어갈
    지점을 잃었다. text를 생략하면 반환문에 경고를 붙여 누락이 눈에 보이게 한다.
    """
    resolved_project = _resolve_record_project(project, ctx)
    slug = _validate_new_task_slug(task)

    purpose = (purpose or "").strip()
    if not purpose:
        raise ValueError(
            "create=True일 때 purpose는 필수입니다(목적 없는 task는 나중에 아무도 못 읽습니다)"
        )

    # 폴더를 만들기 전에 검증한다 — 뒤에서 터지면 목적만 적힌 껍데기 task가 남는다.
    if (text or "").strip():
        follow_tag, follow_text = _validate_task_tag_text(tag, text)
    else:
        if (tag or "").strip():
            raise ValueError(
                f"tag={tag!r}만 주고 text가 비었습니다 — 남길 내용이 없으면 줄을 쓸 수 "
                "없습니다. tag와 text를 함께 주세요(예: tag='다음', text='다음 세션이 "
                "시작할 지점')"
            )
        follow_tag = follow_text = None

    task_dir = task_resolve.tasks_root_for(resolved_project) / slug
    if task_dir.exists():
        raise ValueError(
            f"task {slug!r}는 프로젝트 {resolved_project!r}에 이미 있습니다 — 덮어쓸 수 "
            "없습니다(task.md는 불변 목적, log.md는 append-only). 기존 task에 기록하려면 "
            "create=False로 호출하세요"
        )

    # 호출자가 title에 slug를 이미 넣어 넘기는 일이 잦다("namu-64-… — 브리핑 …").
    # 그대로 두면 아래 머리줄이 `# <slug> — <slug> — 설명`이 돼 이름이 영구히 두 번
    # 박힌다(namu-63·64 실물이 그렇게 만들어졌고, task.md는 불변이라 사후 수정도
    # 못 한다). 저장 전에 접두를 걷어 원본부터 깨끗하게 만든다 — 읽는 쪽
    # (task_resolve.strip_slug_prefix)의 흡수는 이미 적힌 것들을 위한 것이다.
    display_title = task_resolve.strip_slug_prefix((title or slug).strip() or slug, slug)

    # 제목 칸에 문제 설명을 통째로 넣는 호출이 잦다(namu-70·71 실물 — 각각 60·70자).
    # 제목은 statusLine 한 줄과 브리핑 목록에 그대로 실리는 이름이고, 설명이 갈 곳은
    # 바로 아래 `## 목적`이다. 읽는 쪽에서 자르는 안전망은 이미 있지만(one_line),
    # 자른 제목은 원문을 되찾을 수 없으므로 **들어올 때** 막는다. 거절인 이유는
    # namu-66(닫는 말)과 같다 — 조용히 잘라 저장하면 호출자가 잘못 넣은 줄 모른다.
    if len(display_title) > task_resolve.TITLE_LINE_LIMIT:
        raise ValueError(
            f"제목이 너무 깁니다({len(display_title)}자 > "
            f"{task_resolve.TITLE_LINE_LIMIT}자) — 제목은 statusLine 한 줄에 실리는 "
            "'이름'입니다. 짧은 이름만 남기고 설명은 purpose(목적) 칸으로 옮기세요. "
            f"받은 제목: {display_title!r}"
        )

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

    summary = f"task 생성됨: {task_dir}\n{start_line}"

    if follow_text:
        follow_line = f"[{follow_tag}] {ts} {machine} · {follow_text}"
        if via:
            follow_line += f" (via {via})"
        _append_task_log_line(task_dir, follow_line)
        summary += f"\n{follow_line}"
    else:
        summary += (
            "\n⚠ 이어갈 지점([다음] 줄)이 비어 있습니다 — 브리핑에 "
            '"다음: (기록 없음)"으로 뜨고, 다음 세션은 어디서 시작할지 모릅니다. '
            f"지금 바로 namu_record(bowl='tasks', project={resolved_project!r}, "
            f"task={slug!r}, tag='다음', text='<다음 세션이 시작할 지점>')을 한 번 더 "
            "호출하세요(생성 호출에 tag/text를 함께 주면 한 번에 들어갑니다)."
        )

    return summary


_KIND_TO_BOWL = {"lesson": "learnings", "note": "learnings", "fact": "profile"}
_VALID_RECORD_BOWLS = ("learnings", "tasks", "profile", "memo")


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
    if bowl in ("tasks", "memo"):
        # kind와 무관한 그릇들 — tasks는 로그 한 줄, memo는 스틱노트 한 장이라
        # lesson/note/fact 어디에도 속하지 않는다. kind 기본값('lesson')이 넘어와도
        # 모순으로 보지 않는다(호출자가 kind를 줄 이유가 없는 경로다).
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
    Returns: four-bowl dict —
      {"memo": [...every sticky note currently up, oldest first: {"id",
       "timestamp", "text", "machine", "tags", "via"}. Surface these to the
       user when they are relevant — memos are things they asked you to hold
       on to, and on the web this field is the only way they resurface. Take
       one down with namu_memo_remove once it has served its purpose...],
       "profile": [...active facts/preferences, all of them, no limit...],
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
            # memo가 맨 앞이다 — 스틱노트는 "지금 눈에 띄어야" 의미가 있고,
            # 웹에는 세션 훅이 없어 recall 반환이 유일한 노출 경로다(namu-56).
            "memo": memo.load_all(),
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


@mcp.tool(description=record_input.tool_description())
def namu_record(
    # ── 새 이름 13칸 (namu-65) ────────────────────────────────────────────
    bowl: str | None = None,
    summary: str | None = None,
    reason: str | None = None,
    body: str | None = None,
    topic: str | None = None,
    status: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    confidence: str | None = None,
    supersedes: str | None = None,
    create: bool = False,
    done_when: list[str] | None = None,
    # ── 옛 이름 (그대로 불러도 새 칸으로 옮겨 저장한다) ───────────────────
    task: str | None = None,
    outcome: str | None = None,
    task_type: str | None = None,
    verified_by: str | None = None,
    kind: str | None = None,
    subject: str | None = None,
    statement: str | None = None,
    source: str | None = None,
    text: str | None = None,
    tag: str | None = None,
    title: str | None = None,
    purpose: str | None = None,
    ctx: Context | None = None,
):
    """기억 한 건을 남긴다. 자세한 칸 설명은 도구 설명문(표에서 자동 생성)에 있다.

    여기(본문 주석)에는 **동작 순서**만 적는다 — 칸별 설명을 두 곳에 적으면
    갈라지기 때문이다(namu-65: 설명문은 config.FIELDS에서만 만든다).

    (1) record_input.normalize가 그릇을 확정하고, 옛 이름을 새 이름으로 옮기고,
        그 그릇이 받지 않는 칸/빈 필수 칸/정해진 값 밖의 값을 거절한다.
    (2) 그릇별 저장 계층으로 넘긴다(교훈=db.record, 개인 사실=profile.record_fact,
        쪽지=memo.add, 작업일지=log.md append).
    (3) 옮긴 내역(notices)을 반환문 뒤에 붙인다 — 옮겨놓고 알리지 않으면 그것도
        조용한 유실이다.

    반환: 교훈/개인 사실/쪽지는 id, 작업일지는 실제로 적힌 줄(묶음).
    """
    # namu-38: samsung 라이브 실측에서 record 직후 git 단계까지 12분 공백이
    # 관측됐다 — ensure_db(캐시 재생성)/record(yaml+sqlite)/sync(git push) 세 구간
    # 중 어디서 지연이 생기는지 판정하려면 구간별 시간이 반드시 필요하다. db.py는
    # 코어라 침습을 최소화하고, record()는 전체 구간 하나로만 잰다.
    via = _resolve_via(ctx)
    t0 = time.perf_counter()
    _ensure_db()
    t1 = time.perf_counter()

    # 입력 검증·이관은 전부 record_input 한 곳에서 한다(namu-65 2단계). 여기서
    # 다시 판단하면 두 곳이 어긋나고, 어긋난 쪽이 조용히 이기는 것이 이번 사고였다.
    parsed = record_input.normalize({
        "bowl": bowl, "summary": summary, "reason": reason, "body": body,
        "topic": topic, "status": status, "category": category, "tags": tags,
        "project": project, "confidence": confidence, "supersedes": supersedes,
        "create": create, "done_when": done_when,
        "task": task, "outcome": outcome, "task_type": task_type,
        "verified_by": verified_by, "kind": kind, "subject": subject,
        "statement": statement, "source": source, "text": text, "tag": tag,
        "title": title, "purpose": purpose,
    })
    v = parsed.values
    resolved_bowl = parsed.bowl
    v_summary = v.get("summary")
    v_reason = v.get("reason")
    v_body = v.get("body")
    v_topic = v.get("topic")
    v_tags = _normalize_tags(v.get("tags"))

    if resolved_bowl == "tasks":
        if v.get("create"):
            # 작업을 새로 만들 때 body는 "다음 세션이 시작할 지점"이 되어 `[다음]`
            # 줄로 함께 적힌다 — 그 줄이 없는 작업은 브리핑에 "다음: (기록 없음)"으로
            # 떠서 이어받을 수 없다(namu-62 ③). '생략'이면 줄을 만들지 않고, 대신
            # 기존 경고가 그대로 뜨게 둔다.
            start_point = None if cfg.is_omitted(v_body) else v_body
            result = _create_task_entry(
                v.get("project"), v_topic, v_summary, v_reason, v.get("done_when"),
                start_point,
                (v.get("status") or "다음") if start_point else None,
                via, ctx,
            )
        else:
            result = _record_task_entry(
                v.get("project"), v_topic, v_summary, v.get("status"), via, ctx,
                reason=v_reason, body=v_body,
            )
        t2 = time.perf_counter()
        memory_sync.sync_push(f"task: {v_topic} ({cfg.NAMU_MACHINE})")
        t3 = time.perf_counter()
        memory_sync._append_sync_log(
            f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
        )
        return _with_notices(result, parsed.notices)

    if resolved_bowl == "memo":
        entry_id = memo.add(
            tags=v_tags, via=via,
            summary=v_summary, reason=v_reason, body=v_body,
        )
        t2 = time.perf_counter()
        memory_sync.sync_push(f"memo: {(v_summary or '')[:40]} ({cfg.NAMU_MACHINE})")
        t3 = time.perf_counter()
        memory_sync._append_sync_log(
            f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
        )
        return _with_notices(entry_id, parsed.notices)

    if resolved_bowl == "learnings":
        # kind는 없앤 칸이다 — status(성패)가 있으면 교훈, 없으면 단순 기록으로 본다.
        entry_id = record(
            v_topic, v.get("status"), v_reason,
            v.get("category") or "other", v.get("confidence") or "ai", v_tags,
            kind="lesson" if v.get("status") else "note",
            via=via, summary=v_summary, body=v_body,
        )
    else:  # profile
        entry_id = profile.record_fact(
            v_topic, supersedes=v.get("supersedes"),
            verified_by=v.get("confidence") or "human", tags=v_tags, via=via,
            summary=v_summary, reason=v_reason, body=v_body,
        )
    t2 = time.perf_counter()
    # 설치형(~/.namu) 자동 동기화 활성 시에만 실제 push가 일어난다(sync_enabled 하드가드).
    # 반환값이 False여도(비활성/실패) record 자체의 성공 결과에는 영향을 주지 않는다.
    memory_sync.sync_push(f"learn: {(v_summary or v_topic or '')[:50]} ({cfg.NAMU_MACHINE})")
    t3 = time.perf_counter()
    memory_sync._append_sync_log(
        f"RECORD timing ensure={t1 - t0:.2f}s record={t2 - t1:.2f}s sync={t3 - t2:.2f}s"
    )
    return _with_notices(entry_id, parsed.notices)


def _with_notices(result: str, notices: list) -> str:
    """옮긴 내역을 반환문 뒤에 붙인다(완료조건 3).

    안내가 없으면 결과를 그대로 돌려준다 — 새 이름으로 제대로 부른 호출까지 잔소리를
    달면, 정작 봐야 할 때 안 읽힌다.
    """
    if not notices:
        return result
    return str(result) + "\n" + "\n".join(f"※ {n}" for n in notices)


@mcp.tool()
def namu_memo_remove(id: str, ctx: Context | None = None) -> str:
    """Take down one sticky note (namu-56). This DELETES it — memo is the only
    mutable bowl, so the entry is removed from memo.yaml with no tombstone and
    cannot be recovered.

    Args:
      id: the memo's id. A leading prefix is enough (nobody retypes 26 ULID
        chars) — but if the prefix matches several memos, nothing is deleted
        and the candidates are listed instead. Deletion is irreversible here,
        so an ambiguous request does nothing rather than guessing.

    Why this is its own tool rather than an argument on namu_record: taking a
    note down is a different verb from recording, and past damage in this
    system came exactly from arguments whose name disagreed with what they did
    (that is how learnings.yaml got polluted). Returns a short confirmation
    with the removed text.
    """
    _resolve_via(ctx)
    removed = memo.remove(id)
    removed_summary, _reason, _body = memo.layers(removed)
    memory_sync.sync_push(f"memo remove: {removed_summary[:40]} ({cfg.NAMU_MACHINE})")
    return f"메모를 뗐습니다: {removed_summary} (id={removed.get('id')})"


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
