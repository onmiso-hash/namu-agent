"""공유 세션 컨텍스트 헬퍼 — session_recall.py(Claude Code)와 session_inject.py(agy)가 공동 호출.

conn은 호출자가 열고 닫는다. 예외는 삼키지 않고 호출자가 처리.
단, 개별 파일 파싱 실패는 해당 파일만 스킵하고 진행.
"""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from task_resolve import _extract_task_title, _latest_log_ts, _line_tag
from task_resolve import find_active_task as _resolve_task
from task_resolve import find_latest_closed_task as _find_latest_closed_task
from task_resolve import (
    check_project_marker_conflict,
    find_open_tasks,
    has_legacy_tasks,
    journal,
    next_note,
    open_tasks_briefing,
    record_project_marker,
)


def _same_resolved_path(a: str | Path, b: str | Path) -> bool:
    """두 경로가 같은 실제 위치를 가리키는지(realpath 비교). ~/.namu behind 경고가
    project_dir(현재 프로젝트)와 우연히 같은 저장소일 때(예: 개발 repo 자체를
    ~/.namu로 쓰는 극단적 설정) 같은 fetch를 두 번 하지 않기 위한 중복 방지용이다.
    비교 자체가 실패해도(존재하지 않는 경로 등) 예외를 전파하지 않고 다르다고 본다
    (실패 시 두 번 체크되는 게 아예 안 되는 것보다 안전)."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


_CARRYOVER_RE = re.compile(r"이월:\s*(.+)")


def _extract_carryover(log_path: Path) -> str | None:
    """log.md에서 '마지막 [완료] 줄'의 '이월:' 마커 뒤 텍스트를 추출. 없으면 None.

    이월 텍스트는 마커 뒤 첫 문장 경계('. ')까지만 취한다 — 실물 로그(namu-25/26)는
    이월 항목 뒤에 "커밋·푸시 진행" 같은 무관한 후속 메모가 이어 붙기 때문.
    """
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    last_done_line = None
    for line in lines:
        if _line_tag(line) == "완료":
            last_done_line = line

    if last_done_line is None:
        return None

    match = _CARRYOVER_RE.search(last_done_line)
    if not match:
        return None

    text = match.group(1).strip()
    cut = text.find(". ")
    if cut != -1:
        text = text[: cut + 1]
    text = text.strip()
    return text or None


def _git_check_log_path(project_dir: str | Path) -> Path | None:
    """git 동기화 체크 물증 로그 경로 — namu_statusline.py의 _log_path와 같은 규칙으로
    cfg.NAMU_DATA_ROOT(namu-35: 고정 `~/.namu`) 아래 db/에 남긴다(렌더 로그 옆).

    project_dir는 더 이상 폴백으로 쓰이지 않는다 — 데이터 루트가 고정 상수라 항상
    존재하므로, 예전처럼 "값이 없을 때 project_dir로 대체" 분기를 둘 이유가 없다.
    cfg는 함수 내부에서 import해 테스트가 config 모듈 속성을 monkeypatch로
    격리할 수 있게 한다(모듈 관례와 동일).
    """
    import config as cfg

    return cfg.NAMU_DATA_ROOT / "db" / "git_check.log"


def _append_git_check_log(project_dir: str | Path, line: str) -> None:
    """git 체크 실패 사유 1줄 기록. 로깅 실패가 세션 시작을 막으면 안 되므로 전예외 무음."""
    try:
        path = _git_check_log_path(project_dir)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {line}\n")
    except Exception:
        pass


def check_git_behind(project_dir: str | Path) -> int | None:
    """project_dir의 원격 대비 behind 커밋 수 반환. 판정 불가/실패 시 None(무음 스킵).

    비 git 폴더·upstream 미설정·오프라인·타임아웃 등 모든 실패는 None으로 무음
    처리하되, 사유 1줄을 물증 로그에 남긴다(무음 실패 잠복 금지 — namu_statusline.py
    렌더 로그와 동일 원칙). 세션 시작 지연 요인이므로 각 git 호출은 3초 타임아웃.
    환경변수 NAMU_GIT_CHECK=0이면 아예 스킵한다(훅 지연 회피 스위치).
    """
    if os.environ.get("NAMU_GIT_CHECK") == "0":
        return None

    pd = str(project_dir)
    try:
        fetch = subprocess.run(
            ["git", "-C", pd, "fetch", "--quiet"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            shell=False,
            stdin=subprocess.DEVNULL,  # 서버 stdin(파이프) 상속 차단 (namu-38, memory_sync 규약 참조)
        )
        if fetch.returncode != 0:
            _append_git_check_log(
                pd, f"SKIP fetch rc={fetch.returncode} err={(fetch.stderr or '').strip()[:200]}"
            )
            return None

        count_res = subprocess.run(
            ["git", "-C", pd, "rev-list", "--count", "HEAD..@{upstream}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            shell=False,
            stdin=subprocess.DEVNULL,  # 서버 stdin(파이프) 상속 차단 (namu-38)
        )
        if count_res.returncode != 0:
            _append_git_check_log(
                pd,
                f"SKIP rev-list rc={count_res.returncode} err={(count_res.stderr or '').strip()[:200]}",
            )
            return None

        return int(count_res.stdout.strip())
    except Exception as exc:
        _append_git_check_log(pd, f"SKIP {type(exc).__name__}: {exc}")
        return None


def find_active_task(project_dir: str | Path) -> Path | None:
    """project_dir 기준 개인 풀 tasks 루트에서 가장 최근에 진행 중인 task 폴더 반환.
    없으면 None.

    tasks 저장 위치는 `cfg.tasks_dir_for(project_dir)` = `~/.namu/tasks/<basename>/`
    (namu-34)이며, 메모리(cfg.NAMU_DATA_ROOT)와는 별개다.
    """
    import config as cfg

    tasks_dir = cfg.tasks_dir_for(project_dir)
    result = _resolve_task(tasks_dir)
    if result is None:
        return None
    return tasks_dir / result[0]


# 브리핑에 세우는 최근 활동 줄 수 / 열린 task 줄 수. 나머지는 "… (N개 더)"로 접는다
# (CLI 한 화면을 넘기면 사용자가 스크롤백으로 되짚지 못한다).
_JOURNAL_LINES = 8
_OPEN_TASK_LINES = 5
# 다른 방(프로젝트) 열린 task 줄 수 (namu-63) — 이 방 목록보다 짧게 접는다. 다른
# 방은 "여기 뭔가 열려 있다"는 신호만 주면 되고, 상세는 그 폴더에서 세션을 열어야
# 재진입 지점(다음:)이 의미가 있다.
_OTHER_ROOM_LINES = 3


def _short_date(ts: str) -> str:
    """`2026-07-25 09:00:00` → `07-25`."""
    return ts[5:10]


def _strip_slug_prefix(title: str, slug: str) -> str:
    """task 제목에서 폴더명(slug) 접두를 걷어낸다.

    실물 task.md의 첫 헤더는 `# namu-57-memory-retrieval — 메모리 "꺼내는 쪽" …`
    형태라, 브리핑 줄에 slug를 이미 굵게 쓴 뒤 제목을 붙이면 같은 slug가 두 번
    나와 좁은 CLI 폭을 낭비한다.

    접두는 **반복해서** 걷어낸다(namu-64) — task 생성 시 title에 이미 slug를 넣어
    넘기면 저장 쪽이 slug를 한 번 더 앞에 붙여 `# <slug> — <slug> — 설명` 형태가
    되고(namu-63·64 실물이 그렇다), 한 번만 걷어내면 브리핑 줄에 이름이 그대로
    두 번 찍힌다. 기록은 append-only라 원본을 고칠 수 없으므로 읽는 쪽에서 흡수한다.
    """
    while title.startswith(slug):
        stripped = title[len(slug):].lstrip(" —-–:")
        if not stripped:
            break
        title = stripped
    return title or slug


def _title_without_slug(task_dir: Path) -> str:
    """task.md 제목에서 폴더명 접두를 걷어낸다(task_dir 기반 래퍼, `_strip_slug_prefix` 참고)."""
    return _strip_slug_prefix(_extract_task_title(task_dir / "task.md"), task_dir.name)


def _one_line(text: str, limit: int = 70) -> str:
    """여러 줄을 한 줄로 접고 limit자에서 자른다(잘리면 … 표시)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# 문장 경계: 마침표/물음표/느낌표 + 공백. `_split_sentences`가 이 뒤에서 숫자
# 사이(버전 문자열 등)인지 한 번 더 확인해 걸러낸다(정규식만으로는 "0.1.26"처럼
# 공백이 아예 없는 경우까지만 자동으로 안전하고, "9. 0.1.40으로" 같이 숫자 뒤
# 공백 다음이 다시 숫자인 경우는 별도 판정이 필요하다).
_SENTENCE_END_RE = re.compile(r"[.!?]\s+")


def _split_sentences(text: str) -> list[str]:
    """마침표·물음표·느낌표 + 공백을 기준으로 문장 단위로 쪼갠다 — ▸(맨 위) task의
    `다음:`을 하위 목록 여러 줄로 나눠 읽기 쉽게 하기 위함(namu-64).

    (namu-57 1-2가 세운) "자르지 않는다"는 성질을 그대로 유지한다 — 폭 기준
    하드랩(textwrap)은 쓰지 않는다(마크다운 렌더러가 부드러운 줄바꿈을 뭉개
    화면에 반영되지 않는다).
    글자 보존 불변식: 반환값을 공백 하나로 이으면 원문(공백 정규화 후)과
    정확히 같다 — 조각을 자르지도, 버리지도 않는다.

    숫자 바로 앞(마침표 직전)과 공백 다음 첫 글자가 둘 다 숫자면 문장 경계로
    보지 않는다 — `v0.1.39`, `0.1.26` 같은 버전 문자열은 자체로는 마침표 뒤에
    공백이 없어 이미 안전하지만, "...9. 0.1.40으로..."처럼 숫자로 끝난 문장
    바로 뒤에 또 다른 숫자로 시작하는 버전이 오면 소수점/버전 표기로 오인해
    잘못 쪼갤 수 있어 이 경우만 별도로 막는다.
    """
    normalized = " ".join(text.split())
    if not normalized:
        return []

    sentences: list[str] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(normalized):
        punct_pos = m.start()
        before = normalized[punct_pos - 1] if punct_pos > 0 else ""
        after = normalized[m.end()] if m.end() < len(normalized) else ""
        if before.isdigit() and after.isdigit():
            continue  # 소수점/버전 표기 — 문장 경계 아님
        sentences.append(normalized[start : m.end()].rstrip())
        start = m.end()
    tail = normalized[start:]
    if tail:
        sentences.append(tail)
    return sentences


def _build_next_block(note: str) -> str:
    """▸(맨 위) task의 `다음:` 블록 — 문장을 하위 목록 항목으로 한 줄씩 나눠 렌더.

    첫 문장은 기존과 같은 `- 다음: <문장>` 줄에 싣고, 이후 문장은 같은 계층
    (`  - <문장>`)의 후속 줄로 이어 붙인다 — 목록 서식이 깨지지 않게 기존
    `- 다음: ...` 하위 줄과 들여쓰기를 맞춘다(namu-64). 문장이 하나뿐이면
    기존(namu-57 1-2) 전문 한 줄 표시와 동일한 결과가 나온다(회귀 없음).
    """
    sentences = _split_sentences(note)
    if not sentences:
        return "\n  - 다음: (기록 없음)"
    lines = [f"\n  - 다음: {sentences[0]}"]
    for s in sentences[1:]:
        lines.append(f"\n  - {s}")
    return "".join(lines)


def _build_other_room_lines(other_rows: list[dict[str, str | None]]) -> list[str]:
    """"다른 방"(다른 프로젝트 폴더) 열린 task 목록 줄들(namu-63).

    각 행은 `open_tasks_briefing()`이 준 `{project, slug, title, last_ts, next}` 그대로
    쓴다 — 다른 방은 제목만 보여주고 `다음:`은 붙이지 않는다(재진입은 그 폴더에서
    세션을 열어야 의미가 있다). 제목은 반드시 `_strip_slug_prefix`를 거친다 —
    실물 task.md 제목 관행(`# <slug> — 설명`)이 slug로 시작해, 이미 굵게 쓴
    slug 뒤에 원문 제목을 그대로 붙이면 "**task-b** — task-b — 다른 방 작업"처럼
    같은 이름이 줄 안에서 두 번 찍힌다(검수 지적, namu-63 재검토).
    """
    lines = [f"**다른 방 {len(other_rows)}개**"]
    for row in other_rows[:_OTHER_ROOM_LINES]:
        date = _short_date(row["last_ts"]) if row["last_ts"] else "?"
        slug = row["slug"] or ""
        title = _one_line(_strip_slug_prefix(row["title"] or slug, slug), 40)
        lines.append(f"- `{row['project']}` **{slug}** — {title}  `{date}`")
    if len(other_rows) > _OTHER_ROOM_LINES:
        lines.append(f"- … ({len(other_rows) - _OTHER_ROOM_LINES}개 더)")
    return lines


def _build_this_room_lines(open_tasks: list[Path]) -> tuple[list[str], int]:
    """"이 방" 열린 task 목록 줄들 + "다음" 기록이 없는 task 개수 반환.

    다른 방 유무와 무관하게 항상 같은 형식을 쓴다(검수 지적 — 날짜 표기가
    상황에 따라 붙었다 안 붙었다 하면 같은 섹션이 형식만 달라져 혼란스럽다).
    이 방/다른 방 분기(namu-63)에서 이 렌더 로직이 두 벌로 복사돼 있던 것도
    이 헬퍼 하나로 합쳤다 — 한쪽만 고치는 드리프트를 막기 위함.

    ▸(맨 위)만 `다음:`을 전문으로 싣는다(namu-57 1-2 보완, `_split_sentences`
    참고) — 그 한 줄이 재진입 지점이라 잘리면 안 된다. 한도는 `_OPEN_TASK_LINES`,
    초과분은 "… (N개 더)"로 접는다.

    ▸ 항목은 제목 서식으로 강조한다(namu-64) — 마크다운은 색을 고를 수 없어
    굵기+색을 함께 얻는 방법이 이것뿐이다. 앞뒤로 빈 줄을 둬 나머지 목록과
    시각적으로 분리한다(사용자 지적 — "다음에 이어갈 작업이 눈에 안 띈다").
    단계는 반드시 구역 제목(`### 📂 열린 task …`)보다 **한 단계 아래**(`####`)
    여야 한다 — 같은 `###`를 쓰면 크기·색이 구역 제목과 동일해져 ▸가 "이어갈
    작업"이 아니라 새 구역처럼 보인다(검수 지적, namu-64 재검토).
    """
    lines: list[str] = []
    missing_next = 0
    for i, task_dir in enumerate(open_tasks):
        note = next_note(task_dir)
        if note is None:
            missing_next += 1
        if i >= _OPEN_TASK_LINES:
            continue
        ts = _latest_log_ts(task_dir / "log.md")
        date = _short_date(f"{ts[0]} {ts[1]}") if ts else "?"
        title = f"**{task_dir.name}** — {_one_line(_title_without_slug(task_dir), 40)}  `{date}`"
        if i == 0:
            next_block = _build_next_block(note) if note else "\n  - 다음: (기록 없음)"
            lines.append(f"\n#### ▸ {title}\n{next_block}")
        else:
            next_text = _one_line(note) if note else "(기록 없음)"
            lines.append(f"- {title}\n  - 다음: {next_text}")
    if len(open_tasks) > _OPEN_TASK_LINES:
        lines.append(f"- … ({len(open_tasks) - _OPEN_TASK_LINES}개 더)")
    return lines, missing_next


def _open_task_explain_lines(missing_next: int) -> list[str]:
    """▸ 설명 문단 + "다음" 기록 없는 task 경고. 이 방에 열린 task가 있을 때만 붙인다."""
    lines = [
        "▸는 가장 최근 활동한 task일 뿐 **단정이 아닙니다** — 나머지도 전부 열려 있습니다. "
        "다만 사용자가 대상을 지목하지 않고 \"이어서 하자\"고만 하면 **되묻지 말고 ▸의 "
        "`다음:`부터 착수하세요** — 이어갈 지점은 이미 log의 마지막 `[다음]` 줄에 적혀 "
        "있으니 사용자에게 다시 물을 이유가 없습니다. 다른 task를 원하면 사용자가 이름을 댑니다."
    ]
    if missing_next:
        lines.append(
            f"⚠ \"다음\" 기록이 없는 task {missing_next}개 — 세션 끝에 log.md에 "
            "`[다음] YYYY-MM-DD HH:MM:SS <machine> · <다음 세션이 시작할 지점>` 한 줄을 "
            "남기면 다음 세션부터 여기에 표시됩니다."
        )
    return lines


def _build_task_section(project_dir: str | Path, tasks_dir: Path) -> tuple[list[str], str | None]:
    """(브리핑 본문 줄들, 맨 위 task 제목) 반환.

    형식 3원칙(namu-57 1-2):
      ① "진행 중 1개" 단정 제거 — 열린 task를 전부 세운다(맨 위 ▸는 추천일 뿐)
      ② "다음" 기록이 없으면 그렇다고 말한다 — 지금까지는 조용한 빈칸이라
         사용자가 왜 안 나오는지 알 수 없었다
      ③ 시간순 활동을 맨 위에 — 사용자가 실제로 묻는 "어제 뭐 했지"에 먼저 답한다

    다른 방(cross-room, namu-63): 이 방(현재 프로젝트) 밖에도 열린 task가 있으면
    "다른 방" 블록을 덧붙인다 — `open_tasks_briefing(projects=None)`(개인 풀 전체
    순회, namu-57 2단계에 이미 있던 함수)로 조회하고 이 방을 뺀 나머지만 쓴다.
    새 순회 로직은 짜지 않는다.

    이 방·다른 방이 전부 0개면 ([], None). 이 방은 0개인데 다른 방에만 있으면
    task_section은 다른 방 블록만 담아 반환하고 top_title은 여전히 None이다
    (호출자 build_context_markdown이 top_title 유무로 "관련 교훈 검색 대상 task가
    있는지"를 판단하므로 — 다른 방 task는 "지금 이 세션에서 이어갈 대상"이
    아니다).
    """
    open_tasks = find_open_tasks(tasks_dir)
    project_name = tasks_dir.name
    other_rows = [r for r in open_tasks_briefing() if r["project"] != project_name]

    if not open_tasks and not other_rows:
        return ([], None)

    parts: list[str] = []

    if open_tasks:
        entries = journal(project=project_dir, limit=_JOURNAL_LINES)
        if entries:
            parts.append("### 🕘 최근 활동 (시간순, task 무관)")
            for e in entries:
                machine = f"{e['machine']} · " if e["machine"] else ""
                tag = f"[{e['tag']}] " if e["tag"] else ""
                parts.append(
                    f"- `{_short_date(e['ts'])}` {machine}**{e['task_slug']}** {tag}{_one_line(e['text'])}"
                )
            parts.append("")

    this_room_lines, missing_next = _build_this_room_lines(open_tasks)

    if not other_rows:
        # 다른 방이 하나도 없으면 기존 출력 그대로(namu-63 확정 형식 — 회귀 방지).
        # 헤더 문구·▸ 전문 규칙은 유지하되, "이 방" 항목 형식(날짜 포함)은
        # 다른 방 유무와 무관하게 항상 동일하다(검수 지적 — 날짜 표기 통일).
        parts.append(f"### 📂 열린 task {len(open_tasks)}개")
        parts.extend(this_room_lines)
        parts.append("")
        parts.extend(_open_task_explain_lines(missing_next))
        parts.append("")
        return (parts, _extract_task_title(open_tasks[0] / "task.md"))

    # 다른 방이 있는 경우(namu-63 확정 형식): "이 방 N개 · 다른 방 M개" 헤더로 합산.
    parts.append(
        f"### 📂 열린 task — 이 방 {len(open_tasks)}개 · 다른 방 {len(other_rows)}개"
    )
    parts.append("")

    if open_tasks:
        parts.append(f"**이 방** ({project_name})")
        parts.extend(this_room_lines)
    else:
        parts.append(
            f"⚠ 이 방({project_name})에는 열린 작업이 없습니다 — "
            "이어가려면 그 폴더에서 세션을 여세요."
        )
    parts.append("")

    parts.extend(_build_other_room_lines(other_rows))
    parts.append("")

    if open_tasks:
        parts.extend(_open_task_explain_lines(missing_next))
        parts.append("")
        return (parts, _extract_task_title(open_tasks[0] / "task.md"))

    return (parts, None)


_WELCOME_MARKDOWN = (
    "## 🌳 NAMU 준비됨\n\n"
    "아직 기록된 작업·교훈이 없습니다 (신규 환경이면 정상입니다).\n\n"
    "- 설치 확인: `/mcp`에서 `namu-memory`가 connected인지, 또는 recall을 요청해 "
    "\"비어 있음\" 응답이 오는지 확인하세요.\n"
    "- `/namu-task`로 첫 작업을 시작할 수 있습니다."
)


def _build_memo_section() -> list[str]:
    """붙어 있는 스틱노트 섹션(namu-56). 한 장도 없으면 빈 목록(섹션 자체 없음).

    task/교훈보다 **앞에** 놓는다 — 메모는 사용자가 "이거 좀 갖고 있어"라고 맡긴
    것이라 세션 시작 시 눈에 띄어야 제 역할을 한다. 파일이 깨져 있어도 브리핑
    전체를 죽이지 않는다(memo.load_all이 빈 목록으로 흡수).

    id는 앞부분만 보여준다(26자를 그대로 실으면 본문이 묻힌다). 자르는 길이는
    memo.short_ids가 목록을 보고 정한다 — 고정 8자로 자르면 같은 밀리초에 붙인
    메모끼리 앞자리가 겹쳐, 화면의 값을 복사해도 떼기가 거절되는 일이 생긴다.
    """
    import memo

    memos = memo.load_all()
    if not memos:
        return []

    shorts = memo.short_ids(memos)
    lines = [f"### 📌 붙여둔 메모 {len(memos)}장"]
    for m in memos:
        stamp = str(m.get("timestamp") or "")[:16].replace("T", " ")
        short_id = shorts.get(str(m.get("id") or ""), "")
        # 브리핑에는 요약 한 줄만 싣는다(namu-65 완료조건 10) — 원문은 memo.yaml과
        # namu_recall에 그대로 남는다. 3층 이전 메모는 옛 text가 요약 자리를 대신하므로
        # 화면이 종전과 같다.
        summary, _reason, _body = memo.layers(m)
        lines.append(f"- {summary}  ({stamp} {m.get('machine', '')} · id `{short_id}`)")
    lines.append("※ 다 쓴 메모는 `namu_memo_remove`로 떼세요(떼면 파일에서 사라집니다).\n")
    return lines


def build_context_markdown(conn, machine: str, project_dir: str | Path) -> str | None:
    """세션 컨텍스트 마크다운 조립.

    project_dir(현재 프로젝트 폴더) 기준 개인 풀 tasks 루트(`cfg.tasks_dir_for`,
    `~/.namu/tasks/<basename>/`, namu-34)에서 진행 중 task를 찾는다 — tasks는
    저장 위치가 메모리(conn, cfg.NAMU_DATA_ROOT 기준)와 분리돼 있다.

    진행 중 task도 교훈도 0건이면 완전한 침묵(None) 대신 짧은 환영 안내를 반환한다
    (신규 설치 사용자가 무응답을 "설치 실패"로 오인하는 문제 방지, namu-25/26).

    원격 저장소가 behind 상태면(fetch로 감지) 브리핑 맨 앞에 경고 섹션을 붙인다 —
    사용자가 CC를 켜기 전 git pull을 잊으면 이 브리핑 자체가 낡은 상태로 만들어지는
    문제(namu-27) 방지. 감지 불가/실패는 무음 스킵(check_git_behind가 보장).
    tasks·개인전역지식이 실제로 놓이는 `~/.namu`(개인 풀, namu-34) 저장소도 같은
    방식으로 behind 여부를 확인해 경고를 덧붙인다 — project_dir 저장소와 `~/.namu`는
    별개 git 저장소라 하나만 pull해선 다른 쪽 낡은 상태를 못 잡기 때문이다.

    프로젝트 키 충돌(다른 경로의 동명 프로젝트가 같은 machine에서 같은 키를 쓰는
    경우, namu-34 ②)과 구 위치(`project_dir/tasks/`) 잔존(namu-34 ⑤)도 여기서
    감지해 경고 1줄씩 붙인다 — 둘 다 감지·보고 전용이며 자동 조치는 하지 않는다.
    """
    import db
    import config as cfg

    tasks_dir = cfg.tasks_dir_for(project_dir)

    behind = check_git_behind(project_dir)
    warnings: list[str] = []
    if behind is not None and behind > 0:
        warnings.append(
            f"### ⚠ 원격 미동기화 — 원격에 새 커밋 {behind}개\n\n"
            "이 브리핑은 낡은 상태일 수 있습니다. AI는 다른 작업 전에: "
            "① 사용자에게 보고하고 승인받아 `git pull --ff-only` 실행 "
            "② pull 후 tasks/ 상태를 다시 읽어 진행 중 task·다음 작업을 재안내할 것.\n"
        )

    home_namu = Path.home() / ".namu"
    if not _same_resolved_path(project_dir, home_namu):
        home_behind = check_git_behind(home_namu)
        if home_behind is not None and home_behind > 0:
            warnings.append(
                f"### ⚠ 개인 풀(~/.namu) 미동기화 — 원격에 새 커밋 {home_behind}개\n\n"
                "tasks·개인전역지식이 낡은 상태일 수 있습니다. AI는 다른 작업 전에: "
                "① 사용자에게 보고하고 승인받아 `git -C ~/.namu pull --ff-only` 실행 "
                "② pull 후 tasks/ 상태를 다시 읽어 진행 중 task·다음 작업을 재안내할 것.\n"
            )

    conflict = check_project_marker_conflict(tasks_dir, machine, str(project_dir))
    if conflict is not None:
        registered, current = conflict
        warnings.append(
            f"⚠ 프로젝트 키 충돌 — 다른 경로의 동명 프로젝트가 이 키"
            f"({tasks_dir.name})를 사용 중입니다 (등록: {registered} / 현재: {current}).\n"
        )
    record_project_marker(tasks_dir, machine, str(project_dir))

    if has_legacy_tasks(project_dir):
        warnings.append(
            f"⚠ 구 위치 task 발견 — `~/.namu/tasks/{tasks_dir.name}/`로 이관 필요.\n"
        )

    warning = "\n".join(warnings) if warnings else None

    task_section, top_title = _build_task_section(project_dir, tasks_dir)
    parts: list[str] = ["## 🌳 NAMU — 세션 컨텍스트 자동 로딩\n"]
    memo_section = _build_memo_section()
    parts.extend(memo_section)

    if task_section:
        parts.extend(task_section)

    # top_title 기준(namu-63) — task_section이 아니다. 이 방(현재 프로젝트)에
    # 열린 task가 하나도 없으면 다른 방 task가 있어도 top_title은 None이고(다른
    # 방 task는 "지금 이어갈 대상"이 아니다), 이월·환영 분기가 그대로 살아남으며
    # 다른 방 블록(task_section)도 함께 실린다(완료조건 6번 — 섹션이 통째로
    # 사라지던 결함 수정).
    if top_title:
        # 교훈 검색어는 맨 위(가장 최근 활동) task 제목 — 열린 task 전부로 검색하면
        # 관련도가 흐려진다.
        learnings = db.recall(conn, query=top_title, limit=3)
        if learnings:
            parts.append("### 💡 관련 교훈")
            for it in learnings:
                parts.append(f"- [{it['outcome']}] {it['task']}: {it['reason']}")
    else:
        learnings = db.recall(conn, limit=5)

        closed_task = _find_latest_closed_task(tasks_dir)
        carryover = _extract_carryover(closed_task / "log.md") if closed_task else None

        if not learnings and not carryover and not task_section:
            # 보여줄 게 환영 안내뿐인 상황이라도 붙여둔 메모는 반드시 살린다 —
            # 사용자가 맡긴 것이 "아직 아무 기록도 없다"는 이유로 사라지면 안 된다.
            memo_block = ("\n".join(memo_section) + "\n") if memo_section else ""
            if warning:
                return warning + "\n" + memo_block + _WELCOME_MARKDOWN
            return memo_block + _WELCOME_MARKDOWN

        if learnings:
            parts.append("### 💡 최근 교훈")
            for it in learnings:
                parts.append(f"- [{it['outcome']}] {it['task']}: {it['reason']}")

        if carryover:
            parts.append(f"\n### ⏭ 다음 작업 후보 (마감 task 이월: {closed_task.name})")
            parts.append(f"- {carryover}")

    parts.append("\n---\n※ 새 교훈이 생기면 namu_record 도구로 저장하세요.")
    result = "\n".join(parts)
    if warning:
        result = warning + "\n" + result
    return result
