"""공유 세션 컨텍스트 헬퍼 — session_recall.py(Claude Code)와 session_inject.py(agy)가 공동 호출.

conn은 호출자가 열고 닫는다. 예외는 삼키지 않고 호출자가 처리.
단, 개별 파일 파싱 실패는 해당 파일만 스킵하고 진행.
"""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from task_resolve import _extract_task_title, _line_tag
from task_resolve import find_active_task as _resolve_task
from task_resolve import find_latest_closed_task as _find_latest_closed_task
from task_resolve import (
    check_project_marker_conflict,
    find_open_tasks,
    has_legacy_tasks,
    journal,
    next_note,
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


def _short_date(ts: str) -> str:
    """`2026-07-25 09:00:00` → `07-25`."""
    return ts[5:10]


def _title_without_slug(task_dir: Path) -> str:
    """task.md 제목에서 폴더명 접두를 걷어낸다.

    실물 task.md의 첫 헤더는 `# namu-57-memory-retrieval — 메모리 "꺼내는 쪽" …`
    형태라, 브리핑 줄에 폴더명을 이미 굵게 쓴 뒤 제목을 붙이면 같은 slug가 두 번
    나와 좁은 CLI 폭을 낭비한다.
    """
    title = _extract_task_title(task_dir / "task.md")
    if title.startswith(task_dir.name):
        title = title[len(task_dir.name):].lstrip(" —-–:")
    return title or task_dir.name


def _one_line(text: str, limit: int = 70) -> str:
    """여러 줄을 한 줄로 접고 limit자에서 자른다(잘리면 … 표시)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _flat(text: str) -> str:
    """자르지 않고 한 줄로만 접는다 — 맨 위 task의 `다음:` 전용(namu-57 1-2 보완).

    나머지 줄은 좁은 CLI 폭 때문에 잘라야 하지만, 맨 위 task의 "다음"만은 전문을
    싣는다. 이 한 줄이 곧 재진입 지점이라 잘리면 세션이 log.md를 한 번 더 읽어야
    착수할 수 있고, 그러면 "이어서 하자" 한마디로 이어지지 않는다(사용자 지적).
    """
    return " ".join(text.split())


def _build_task_section(project_dir: str | Path, tasks_dir: Path) -> tuple[list[str], str | None]:
    """(브리핑 본문 줄들, 맨 위 task 제목) 반환. 열린 task가 없으면 ([], None).

    형식 3원칙(namu-57 1-2):
      ① "진행 중 1개" 단정 제거 — 열린 task를 전부 세운다(맨 위 ▸는 추천일 뿐)
      ② "다음" 기록이 없으면 그렇다고 말한다 — 지금까지는 조용한 빈칸이라
         사용자가 왜 안 나오는지 알 수 없었다
      ③ 시간순 활동을 맨 위에 — 사용자가 실제로 묻는 "어제 뭐 했지"에 먼저 답한다
    """
    open_tasks = find_open_tasks(tasks_dir)
    if not open_tasks:
        return ([], None)

    parts: list[str] = []

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

    parts.append(f"### 📂 열린 task {len(open_tasks)}개")
    missing_next = 0
    for i, task_dir in enumerate(open_tasks):
        note = next_note(task_dir)
        if note is None:
            missing_next += 1
        if i >= _OPEN_TASK_LINES:
            continue
        marker = "▸ " if i == 0 else ""
        if note:
            # 맨 위(▸)만 전문 — 재진입 지점이라 잘리면 안 된다(_flat 주석 참고).
            next_text = _flat(note) if i == 0 else _one_line(note)
        else:
            next_text = "(기록 없음)"
        parts.append(
            f"- {marker}**{task_dir.name}** — {_one_line(_title_without_slug(task_dir), 40)}"
            f"\n  - 다음: {next_text}"
        )
    if len(open_tasks) > _OPEN_TASK_LINES:
        parts.append(f"- … ({len(open_tasks) - _OPEN_TASK_LINES}개 더)")
    parts.append("")
    parts.append(
        "▸는 가장 최근 활동한 task일 뿐 **단정이 아닙니다** — 나머지도 전부 열려 있습니다. "
        "다만 사용자가 대상을 지목하지 않고 \"이어서 하자\"고만 하면 **되묻지 말고 ▸의 "
        "`다음:`부터 착수하세요** — 이어갈 지점은 이미 log의 마지막 `[다음]` 줄에 적혀 "
        "있으니 사용자에게 다시 물을 이유가 없습니다. 다른 task를 원하면 사용자가 이름을 댑니다."
    )
    if missing_next:
        parts.append(
            f"⚠ \"다음\" 기록이 없는 task {missing_next}개 — 세션 끝에 log.md에 "
            "`[다음] YYYY-MM-DD HH:MM:SS <machine> · <다음 세션이 시작할 지점>` 한 줄을 "
            "남기면 다음 세션부터 여기에 표시됩니다."
        )
    parts.append("")

    return (parts, _extract_task_title(open_tasks[0] / "task.md"))


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
        lines.append(f"- {m.get('text', '')}  ({stamp} {m.get('machine', '')} · id `{short_id}`)")
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

        if not learnings and not carryover:
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
