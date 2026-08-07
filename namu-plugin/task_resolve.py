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


def _title_from_text(text: str, fallback: str) -> str:
    """task.md 본문(글자)에서 첫 번째 # 헤더를 뽑는다. 없으면 fallback.

    파일이 아니라 글자를 받는 이유: 설명서를 통째로 읽어 둔 쪽(`parse_task_doc`)이
    제목만 얻으려고 같은 파일을 한 번 더 열지 않게 하기 위해서다. 제목을 뽑는
    규칙은 여기 하나뿐이어야 한다 — 두 벌이 되면 한쪽만 고쳐지는 종류의 결함이다.
    """
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _extract_task_title(task_md_path: Path) -> str:
    """task.md 첫 번째 # 헤더에서 제목 추출. 실패 시 폴더명 폴백."""
    try:
        return _title_from_text(
            task_md_path.read_text(encoding="utf-8"), task_md_path.parent.name
        )
    except OSError:
        return task_md_path.parent.name


def strip_slug_prefix(title: str, slug: str) -> str:
    """task 제목에서 폴더명(slug) 접두를 **반복해서** 걷어낸다.

    실물 task.md의 첫 헤더는 `# namu-57-memory-retrieval — 메모리 "꺼내는 쪽" …`
    형태다 — 읽는 쪽은 대개 slug를 이미 굵게 쓴 뒤 제목을 붙이므로, 그대로 두면
    같은 이름이 한 줄에 두 번 나온다. 반복인 이유는 task 생성 시 title에 이미
    slug가 들어간 채 넘어오면 저장 쪽이 한 번 더 앞에 붙여 `# <slug> — <slug> —
    설명`이 되기 때문이다(namu-63·64 실물). 생성 쪽은 namu-64에서 막았지만
    log·task.md는 append-only/불변이라 이미 적힌 것은 고칠 수 없어, 읽는 쪽에서
    영구히 흡수한다.

    (namu-64 재검토) 이 함수는 원래 session_context.py에만 있어 "화면 그리는
    단계에서만" 가려졌고, 같은 데이터를 쓰는 다른 소비자(scripts/
    namu_active_task.py --all --json, namu_recall의 tasks, 웹 대시보드)에는
    중복이 그대로 새어 나갔다. 그래서 제목을 만드는 쪽(task_resolve)으로 옮겨
    모든 소비자가 한 번에 깨끗한 제목을 받게 했다.
    """
    while title.startswith(slug):
        stripped = title[len(slug):].lstrip(" —-–:")
        if not stripped:
            break
        title = stripped
    return title or slug


# 한 줄 화면(브리핑 목록·statusLine)에 제목을 실을 때의 공통 상한.
# 40자인 이유는 브리핑이 namu-64부터 써 온 값이며, statusLine은 모델·폴더·컨텍스트
# 표시가 같은 줄을 나눠 쓰므로 그보다 넉넉할 이유가 없기 때문이다.
TITLE_LINE_LIMIT = 40


def one_line(text: str, limit: int = 70) -> str:
    """여러 줄을 한 줄로 접고 limit자에서 자른다(잘리면 … 표시).

    (namu-72) 원래 session_context.py에만 있어 **브리핑만** 제목을 잘랐다.
    statusLine은 같은 데이터를 다른 경로로 읽으면서 이 장치를 안 거쳐, 긴 제목이
    화면 한 줄을 통째로 뒤덮었다(실물: namu-70·71). 자르는 규칙이 화면마다 따로
    있으면 새 화면이 생길 때마다 같은 사고가 반복되므로, 제목을 만드는 쪽
    (task_resolve, stdlib 전용이라 statusLine도 import 가능)으로 옮겨 한 벌만 둔다
    — strip_slug_prefix를 여기로 옮긴 것과 같은 판단이다.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def task_title(task_dir: Path) -> str:
    """task.md 제목에서 폴더명 접두를 걷어낸 '보여주기용' 제목.

    원문 그대로가 필요하면 `_extract_task_title`을 쓴다 — 여기서 걷어내는 것은
    표기 중복뿐이고 원본 파일은 건드리지 않는다.
    """
    return strip_slug_prefix(_extract_task_title(task_dir / "task.md"), task_dir.name)


def _parse_log_ts(line: str) -> tuple[str, str] | None:
    """log.md 한 줄에서 (날짜, 시간) 튜플 추출."""
    match = re.search(r"^\[.*?\]\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}:\d{2}))?(?:\s|$)", line)
    if not match:
        return None
    date_str = match.group(1)
    time_str = match.group(2) or "00:00:00"
    return (date_str, time_str)


def _latest_log_ts(log_path: Path) -> tuple[str, str] | None:
    """log.md에서 가장 **늦은** 타임스탬프 반환(파일의 마지막 줄이 아니다).

    예전에는 뒤에서부터 첫 파싱 성공 줄을 썼다. 파일 순서 == 시간 순서라는 가정인데,
    두 가지로 깨진다. ① 시간대가 다른 호스트가 기록하면 나중 줄의 시각이 더 이르게
    적힌다(namu-57 5단계에서 cfg.now로 통일해 원인은 없앴지만, 그 전에 적힌 줄은
    append-only라 영영 남는다) ② union merge는 두 PC의 줄을 각자 덩어리째 이어붙이므로
    병합 결과의 줄 순서가 전역 시간순이 아니다.

    `last_ts`는 브리핑에서 task 정렬(가장 최근 활동 순)에 쓰이므로, 한 줄만 이르게
    찍혀도 진행 중인 task가 목록 아래로 내려간다. max로 고르면 두 경우 모두 안전하다.
    """
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    stamps = [ts for line in lines if (ts := _parse_log_ts(line)) is not None]
    return max(stamps) if stamps else None


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


# ---------------------------------------------------------------------------
# 책갈피(pin, namu-70) — "다음엔 이것부터" 표시
# ---------------------------------------------------------------------------
#
# 왜 log.md가 아니라 별도 파일인가: ①log는 append-only라 "껐다 켰다 하는 현재 상태"를
# 담을 수 없다(다섯 번 바꾸면 줄 다섯 개가 남고 지금 값은 계산해야 나온다) ②log에
# 적으면 그 task의 last_ts가 갱신돼 **순서가 두 경로로 흔들린다** — 이 작업이 없애려던
# "기록을 건드려 화면 순서를 바꾸는" 짓과 결과가 같아진다. 순서는 표시의 문제이지
# 기록의 문제가 아니다(namu-70 목적).
#
# 왜 기기(machine)마다 파일을 따로 두는가: 책갈피는 mutable이라 같은 파일을 두 PC가
# 고치면 git 병합 충돌이 난다(profile.yaml에서 실제로 났던 종류의 사고). 각 PC가
# 제 이름이 붙은 파일에만 쓰면 충돌 가능성 자체가 0이고, 파일은 그대로 동기화되므로
# 다른 PC가 무엇을 꽂아뒀는지도 보인다(사용자 결정 2026-08-01).
_PIN_PREFIX = ".pin."

# 파일 이름에 들어가는 값이라 경로 조작(`../`)·구분자를 원천 차단한다. log 파싱용
# `_MACHINE_RE`보다 길이를 넉넉히 잡는다 — 저기 20자는 "본문 조각을 machine으로
# 오인하지 않기" 위한 보수적 상한이고, 여기는 실제 호스트 이름이 그대로 온다.
_PIN_MACHINE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _pin_path(tasks_dir: Path, machine: str) -> Path:
    if not _PIN_MACHINE_RE.match(machine or ""):
        raise ValueError(f"기기 이름이 파일 이름으로 쓸 수 없는 형태입니다: {machine!r}")
    return tasks_dir / f"{_PIN_PREFIX}{machine}"


def set_pin(tasks_dir: Path, machine: str, slug: str, ts: str) -> None:
    """이 기기의 책갈피를 slug로 꽂는다(기존 값은 덮어쓴다 — 기기당 하나).

    ts는 호출자가 준다 — 이 모듈은 stdlib 전용(statusLine 공유)이라 config를 못
    쓰는데, 기록 시각은 반드시 `cfg.now()`(기준 시간대)여야 하기 때문이다. 여기서
    `datetime.now()`를 쓰면 시간대가 다른 호스트의 책갈피와 선후가 뒤집힌다.
    """
    tasks_dir.mkdir(parents=True, exist_ok=True)
    _pin_path(tasks_dir, machine).write_text(f"{slug}\n{ts}\n", encoding="utf-8")


def clear_pin(tasks_dir: Path, machine: str) -> str | None:
    """이 기기의 책갈피를 뺀다. 꽂혀 있던 slug를 반환(없었으면 None).

    다른 기기의 책갈피는 건드리지 않는다 — 그 파일은 그 기기의 것이고, 남의 PC
    상태를 여기서 지우면 그쪽에서 되살아나 깜빡이게 된다.
    """
    path = _pin_path(tasks_dir, machine)
    slug = None
    try:
        slug = path.read_text(encoding="utf-8").splitlines()[0].strip() or None
    except (OSError, IndexError):
        slug = None
    try:
        path.unlink()
    except OSError:
        return None
    return slug


def read_pins(tasks_dir: Path) -> list[dict[str, str]]:
    """이 방에 꽂힌 책갈피 전부를 **최근에 꽂은 순**으로 반환.

    항목: `{"machine", "slug", "ts"}`. 파일이 깨졌거나 slug가 비면 건너뛴다
    (책갈피 하나가 망가졌다고 브리핑 전체가 멈추면 안 된다).

    닫힌 task를 가리키는 책갈피도 그대로 돌려준다 — 걸러내는 일은 열린 task
    목록과 맞춰 보는 쪽(`_pinned_first`)이 한다. 그래야 다른 기기가 꽂아둔
    책갈피를 지우지 않고도 화면에서 조용히 사라진다.
    """
    try:
        paths = sorted(tasks_dir.glob(f"{_PIN_PREFIX}*"))
    except OSError:
        return []

    pins: list[dict[str, str]] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        slug = lines[0].strip() if lines else ""
        if not slug:
            continue
        pins.append(
            {
                "machine": path.name[len(_PIN_PREFIX):],
                "slug": slug,
                "ts": lines[1].strip() if len(lines) > 1 else "",
            }
        )
    pins.sort(key=lambda p: (p["ts"], p["machine"]), reverse=True)
    return pins


def _pinned_first(tasks_dir: Path, task_dirs: list[Path]) -> list[Path]:
    """책갈피가 꽂힌 task를 앞으로 당긴다(여러 개면 최근에 꽂은 것부터).

    파이썬 sorted는 안정 정렬이라, 책갈피가 없는 task들의 상대 순서(최근 활동순)는
    그대로 유지된다 — 책갈피는 "맨 앞 몇 개"만 정하고 나머지 규칙은 안 건드린다.
    """
    pins = read_pins(tasks_dir)
    if not pins:
        return task_dirs

    rank: dict[str, int] = {}
    for i, pin in enumerate(pins):
        rank.setdefault(pin["slug"], i)
    return sorted(task_dirs, key=lambda d: rank.get(d.name, len(pins)))


def clear_pin_if_points_to(tasks_dir: Path, machine: str, slug: str) -> bool:
    """이 기기의 책갈피가 slug를 가리키고 있으면 뺀다. 뺐으면 True.

    작업을 닫을 때 부른다 — 끝난 작업이 계속 맨 위에 남으면 책갈피가 곧 방해물이
    된다. 다른 기기 것은 건드리지 않는다(닫힌 task를 가리키는 책갈피는 열린 목록과
    맞춰 보는 단계에서 이미 화면에서 사라진다).
    """
    try:
        current = _pin_path(tasks_dir, machine).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    if not current or current[0].strip() != slug:
        return False
    clear_pin(tasks_dir, machine)
    return True


def pins_by_slug(tasks_dir: Path) -> dict[str, dict[str, str]]:
    """slug → 그 task에 꽂힌 책갈피 중 **가장 최근 것**. 화면 표시용.

    두 PC가 같은 task를 꽂으면 항목이 둘이지만 화면에 붙일 표시는 하나면 된다.
    """
    result: dict[str, dict[str, str]] = {}
    for pin in read_pins(tasks_dir):
        result.setdefault(pin["slug"], pin)
    return result


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


def is_open(task_dir: Path) -> bool:
    """이 task가 아직 열려 있는가(닫힘 판정은 `_is_closed` 하나가 권위).

    모듈 밖(mcp_server 등)에서 닫힘 여부를 물을 때 쓰는 공개 이름이다 — 판정
    규칙이 두 벌로 갈리지 않도록 새로 구현하지 않고 그대로 뒤집어 준다.
    """
    return not _is_closed(task_dir)


def find_active_task(tasks_dir: Path) -> tuple[str, str] | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 진행 중 task의 (폴더명, 제목) 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if not _is_closed(task_dir):
            return (task_dir.name, task_title(task_dir))

    return None


def find_open_tasks(tasks_dir: Path) -> list[Path]:
    """tasks_dir의 '열린'(닫히지 않은) task 폴더 전부를 최근 활동순으로 반환.

    `find_active_task`는 이 목록의 첫 번째만 뽑아 "진행 중 1개"로 단정했는데,
    실측상 열린 task가 6개인데도 1개만 보이는 게 브리핑이 계속 빗나간 원인이었다
    (namu-57 증상 A). 목록을 그대로 넘겨 호출자가 전부 보여주게 한다.

    (namu-70) 책갈피가 꽂혀 있으면 그 task가 앞에 온다 — 최근 활동순 하나로만
    세우면 만든 순서가 곧 중요도가 돼, 26초 늦게 만든 사소한 작업이 급한 작업
    앞에 서는 일이 실제로 있었다. 여기서 흡수하므로 statusLine·브리핑·웹이
    각자 순서 규칙을 따로 갖지 않는다.
    """
    open_dirs = [d for d in _sorted_task_dirs(tasks_dir) if not _is_closed(d)]
    return _pinned_first(tasks_dir, open_dirs)


def next_why(task_dir: Path) -> str | None:
    """마지막 `[다음]` 묶음의 '왜' 한 줄. 없으면 None.

    브리핑의 ▸(가장 최근 작업)에만 쓴다(namu-65 5단계, 사용자 결정 A). 나머지 작업은
    요약 한 줄이 맞지만 ▸는 **이어받는 지점**이라, 한 줄만으로는 왜 그 지점인지 몰라
    착수가 어렵다. 전문을 다시 쏟는 것과 한 줄만 주는 것 사이의 절충이며, 이관이
    남긴 줄이 정확히 '요약/왜' 두 줄이라 새 데이터 없이 된다.
    """
    try:
        lines = (task_dir / "log.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    found = None
    for index, line in enumerate(lines):
        parsed = _parse_log_line(line)
        if parsed is not None and parsed["tag"] == "다음" and parsed["text"]:
            found = _continuations(lines, index).get("왜")
    return found or None


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

    for index, line in enumerate(lines):
        parsed = _parse_log_line(line)
        if parsed is not None and parsed["tag"] == "다음" and parsed["text"]:
            # 요약이 있으면 요약, 없으면 첫 줄(namu-65 5단계).
            shown, _rest = _display_text(lines, index, parsed["text"])
            entries.append(shown)
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


# 세 줄 묶음(namu-65 4단계)의 이어지는 줄. 머리줄 다음에 오는 **들여쓴** 줄들이며,
# 라벨은 셋뿐이다. `요약:`은 이관된 옛 줄에만 있다 — 그때는 머리줄이 이미 긴 원문이라
# 요약을 아래에 덧붙였기 때문이고, 새로 적히는 줄은 머리줄 자체가 요약이다.
_CONT_LABELS = ("요약", "왜", "상세")


def _continuations(lines: list[str], head_index: int) -> dict[str, str]:
    """머리줄(head_index) 바로 다음의 들여쓴 줄들을 라벨→값으로 모은다.

    들여쓰기로 판정하는 이유는 읽는 쪽 규약이 "`[`로 시작하는 줄만 항목"이기 때문이다
    — 그 규약을 그대로 두면 옛 450줄과 새 세 줄 묶음이 한 파일에 섞여도 항목 수가
    흔들리지 않는다. 라벨이 없는 들여쓴 줄(옛 로그의 이어쓴 문단)은 무시한다.
    """
    found: dict[str, str] = {}
    for line in lines[head_index + 1:]:
        if not line[:1].isspace():
            break
        stripped = line.strip()
        for label in _CONT_LABELS:
            prefix = f"{label}:"
            if stripped.startswith(prefix):
                found.setdefault(label, stripped[len(prefix):].strip())
                break
    return found


def _display_text(lines: list[str], head_index: int, head_text: str | None) -> tuple[str | None, str]:
    """화면에 실을 한 줄과, 검색용으로 함께 훑을 나머지를 돌려준다.

    규칙은 "요약이 있으면 요약, 없으면 첫 줄"이다(namu-65 5단계). 이관된 옛 줄은
    머리줄이 2,000자짜리 문단이라 요약을 써야 하고, 새 줄은 머리줄이 곧 요약이다.
    화면에서 빠진 부분도 검색에서는 빠지면 안 되므로 따로 돌려준다.
    """
    cont = _continuations(lines, head_index)
    summary = cont.get("요약")
    rest = [v for k, v in cont.items() if k != "요약" or summary is None]
    if summary:
        rest.append(head_text or "")
        return summary, " ".join(x for x in rest if x)
    return head_text, " ".join(x for x in rest if x)


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

    `title`은 `task_title()`을 거쳐 slug 접두가 걷힌 상태다(namu-64 재검토) —
    slug는 같은 dict의 `slug` 키로 이미 따로 주므로, 제목에까지 넣으면 모든
    소비자가 이름을 두 번 찍는다. 예전에는 session_context(브리핑 렌더)만
    걷어내서 --all --json·namu_recall·대시보드에는 중복이 그대로 나갔다.
    """
    if projects is None:
        projects = list_projects()

    rows: list[dict[str, str | None]] = []
    for project in projects:
        tasks_dir = tasks_root_for(project)
        project_name = tasks_dir.name
        pins = pins_by_slug(tasks_dir)
        for task_dir in find_open_tasks(tasks_dir):
            ts = _latest_log_ts(task_dir / "log.md")
            pin = pins.get(task_dir.name)
            rows.append(
                {
                    "project": project_name,
                    "slug": task_dir.name,
                    "title": task_title(task_dir),
                    "last_ts": f"{ts[0]} {ts[1]}" if ts else None,
                    "next": next_note(task_dir),
                    # ▸ 항목에만 쓰이는 한 줄(namu-65) — 없으면 None.
                    "why": next_why(task_dir),
                    # 책갈피(namu-70) — 안 꽂혀 있으면 둘 다 None. dict를 통째로
                    # 넣지 않고 두 칸으로 펴는 이유는 이 반환값이 웹·대시보드까지
                    # 그대로 가는 평평한 표이기 때문이다(중첩되면 소비자마다 파싱).
                    "pin_machine": pin["machine"] if pin else None,
                    "pin_ts": pin["ts"] if pin else None,
                }
            )

    # 책갈피가 꽂힌 것부터(최근에 꽂은 순), 나머지는 지금까지대로 최근 활동순.
    rows.sort(
        key=lambda r: (bool(r["pin_ts"] is not None), r["pin_ts"] or "", r["last_ts"] or ""),
        reverse=True,
    )
    return rows


def find_latest_closed_task(tasks_dir: Path) -> Path | None:
    """tasks_dir에서 log 타임스탬프가 가장 최신인 '닫힌' task 폴더 반환. 없으면 None."""
    for task_dir in _sorted_task_dirs(tasks_dir):
        if _is_closed(task_dir):
            return task_dir

    return None


def tasks_root_for(project_dir: str | Path) -> Path:
    """tasks 저장 루트 = 개인 풀 `~/.namu/tasks/<프로젝트 방 이름>/` (namu-34).

    방 이름을 정하는 규칙은 `project_key_for` 하나뿐이다 — namu-73에서
    `basename(현재 폴더)` → `basename(프로젝트 뿌리)`로 개정됐다(하위 폴더로
    들어가면 작업을 잃어버리던 결함). 읽는 쪽·쓰는 쪽이 모두 이 함수를 거치므로
    화면과 기록이 갈릴 일이 없다.

    규칙 한 줄, 특례 0 — 메모리 데이터 루트(cfg.NAMU_DATA_ROOT, 교훈·db 전용)와는
    무관하며 개발 repo(이 repo)도 예외를 두지 않는다. tasks는 여전히 "프로젝트 귀속"
    데이터지만 저장 위치만
    개인 풀로 통합해, PC 간 공유를 개인 전역 동기화에 편승시킨다(공개 repo에
    작업 기록이 노출되는 것도 원천 차단).

    Path.home()은 HOME 환경변수를 존중하므로(POSIX) 테스트는 monkeypatch로
    가짜 HOME을 주입해 실제 ~/.namu를 건드리지 않고 격리할 수 있다.
    """
    return Path.home() / ".namu" / "tasks" / project_key_for(project_dir)


# 프로젝트 뿌리 표시. `.git`은 폴더(보통)일 수도 파일(하위 모듈·worktree)일 수도 있어
# is_dir()로 좁히지 않는다 — 하위 모듈에서 상위로 빨려 올라가면 별도 프로젝트의
# 작업이 남의 방에 섞인다(namu-cloud-routing이 실제로 이 repo의 하위 모듈이다).
_PROJECT_ROOT_MARKERS = (".git",)


def project_key_for(project_dir: str | Path) -> str:
    """프로젝트 방 이름 = `basename(프로젝트 뿌리)` (namu-73).

    namu-34는 이 값을 `basename(현재 폴더)`로 정했다. 그 규칙은 작업 도중 폴더를
    한 칸만 옮겨도 다른 프로젝트로 오인한다 — 실물로 `~/.namu/tasks/`에 작업 없이
    이름표만 있는 빈 방(namu-plugin·scratchpad·namu)이 생겼고, statusLine은 그동안
    '진행 task 없음'을 냈다. 기록도 같은 함수를 쓰므로 하위 폴더에서 남긴 기록이
    엉뚱한 방에 쌓일 수 있었다.

    그래서 위로 거슬러 올라가며 프로젝트 뿌리 표시(`.git`)를 찾고 그 폴더 이름을
    쓴다. 찾지 못하면 namu-34의 규칙 그대로 현재 폴더 이름으로 폴백한다.

    **홈 폴더에서 멈춘다** — dotfiles를 git으로 관리하는 사람이 드물지 않은데, 홈을
    뿌리로 인정하면 홈 아래 모든 프로젝트가 한 방으로 합쳐진다(작업 기록이 서로
    섞이는 쪽이 방이 갈리는 것보다 훨씬 나쁘다).

    경로가 실재하지 않으면 탐색하지 않고 곧장 basename을 쓴다 — 이 함수는 폴더
    경로뿐 아니라 이미 확정된 방 이름(`project='namu-agent'`처럼 웹에서 넘어오는
    값)으로도 불리기 때문이다.
    """
    raw = str(project_dir).rstrip("/\\")
    fallback = os.path.basename(raw)

    try:
        start = Path(raw).resolve()
        if not start.is_dir():
            return fallback
        home = Path.home().resolve()
    except OSError:
        return fallback

    current = start
    while True:
        if current == home:
            break
        if any((current / marker).exists() for marker in _PROJECT_ROOT_MARKERS):
            return current.name
        if current.parent == current:  # 파일시스템 최상단
            break
        current = current.parent

    return fallback


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

            for index, line in enumerate(lines):
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
                shown, rest = _display_text(lines, index, parsed["text"])
                entries.append(
                    {
                        "ts": ts,
                        "project": project_name,
                        "task_slug": task_slug,
                        "tag": parsed["tag"],
                        "machine": parsed["machine"],
                        "via": parsed["via"],
                        # 화면에는 요약 한 줄만(namu-65 완료조건 10). 화면에서 뺀
                        # 부분은 detail로 남겨 검색에서까지 빠지지 않게 한다.
                        "text": shown,
                        "detail": rest,
                    }
                )

    entries.sort(key=lambda e: (e["ts"], e["project"], e["task_slug"]), reverse=True)
    if limit is not None:
        entries = entries[:limit]
    return entries


# 작업 설명서(task.md)가 검색 결과에 실릴 때 다는 태그. log.md 줄의 태그
# ([시작]·[단계]·[다음]…)와 **같은 자리**에 들어가되 겹치지 않는 이름이라, 읽는
# 쪽이 "이 건은 일지 한 줄이 아니라 설명서 한 장"임을 바로 안다. 이 태그가 log.md에
# 적히는 일은 없다 — 설명서는 파일이 따로 있고 append 대상이 아니다.
TASK_DOC_TAG = "설명서"

# task.md 머리의 생성 줄. 실물: `📅 생성 2026-07-31 [hp] · 🔗 관련: __`
_TASK_DOC_CREATED_RE = re.compile(r"생성\s+(\d{4}-\d{2}-\d{2})(?:\s*\[([^\]]+)\])?")

# 생성 줄은 머리말에만 있다. 본문까지 뒤지면 "## 목적" 안의 `생성 2026-...` 같은
# 서술이 생성 시각으로 둔갑하므로 앞부분만 본다.
_TASK_DOC_HEAD_LINES = 5


def _task_doc_origin(text: str, task_dir: Path) -> tuple[str, str | None]:
    """설명서의 (ts, machine). 생성 줄이 없으면 log.md의 가장 이른 줄로 대신한다.

    ts는 log 줄과 같은 폭(`YYYY-MM-DD HH:MM:SS`)으로 맞춘다 — 두 종류가 한 목록에
    섞여 정렬·범위 필터를 함께 타므로 폭이 다르면 사전순 비교가 어긋난다(날짜만
    적힌 `2026-07-31`은 `2026-07-31 00:00:00`보다 **작다**).

    폴백이 필요한 이유(실측 2026-08-08): 실물 84장 중 3장(namu-16·39·40)에는 생성
    줄이 없다. 이 머리말 형식이 굳기 전에 만들어졌고 task.md는 불변이라 고칠 수도
    없다. 시각이 비면 정렬에서 맨 뒤로 밀리고 since/until 필터에서 통째로 빠지므로,
    그 task가 처음 기록된 시각을 대신 쓴다 — 생성 시각의 가장 정확한 근사이고 셋 다
    log.md 첫 줄에 시각이 있는 것을 확인했다.
    """
    for line in text.splitlines()[:_TASK_DOC_HEAD_LINES]:
        match = _TASK_DOC_CREATED_RE.search(line)
        if match:
            return f"{match.group(1)} 00:00:00", match.group(2)

    try:
        log_lines = (task_dir / "log.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", None
    parsed = [p for p in (_parse_log_line(line) for line in log_lines) if p]
    if not parsed:
        return "", None
    earliest = min(parsed, key=lambda p: p["ts"])
    return earliest["ts"], earliest["machine"]


def parse_task_doc(task_md_path: Path, project: str) -> dict[str, str | None] | None:
    """task.md 한 장 → journal() 줄과 **같은 모양**의 항목 하나. 못 읽으면 None.

    단위가 줄이 아니라 문서 한 장인 이유(2026-08-08 사용자 결정): 설명서는 제목·목적·
    완료조건이 한 덩어리로 하나의 답을 이룬다. 줄로 쪼개면 `- [x] 안내서 4종 검토`
    한 줄만 걸려 그게 어느 작업의 무엇인지 알 수 없고, 검색 대상 줄이 625줄에서
    2,091줄로 불어나 log.md 쪽 결과까지 묻힌다.

    반환 모양을 journal()과 같게 맞추는 이유: 이 결과를 받는 곳(플러그인·웹·클라우드)
    이 세 군데인데, 새 모양을 만들면 세 곳을 다 고쳐야 하고 안 고친 곳에서는 설명서가
    조용히 사라진다. 같은 모양에 tag만 `설명서`로 다르면 안 고친 곳도 그대로 뜬다.

    `project`를 인자로 받는 이유: 클라우드는 회원별 폴더를 훑느라 개인 풀 경로 규칙을
    못 쓴다. 파싱 규칙만 여기서 내주면 그쪽이 함수를 베끼지 않아도 되고, 베끼는 순간
    두 서버가 갈라지는 일(2026-08-08 작업일지 검색에서 실제로 겪었다)을 막는다.
    """
    try:
        raw = task_md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    task_dir = task_md_path.parent
    slug = task_dir.name
    ts, machine = _task_doc_origin(raw, task_dir)
    title = strip_slug_prefix(_title_from_text(raw, slug), slug)

    # 화면에 실을 한 줄은 제목, 나머지(목적·완료조건)는 detail — journal()의
    # `_display_text`와 같은 역할 분담이다. 머리말 두 줄(제목·생성)은 이미 다른
    # 칸으로 갔으므로 detail에서 뺀다.
    body_lines = [
        line
        for line in raw.splitlines()
        if not line.startswith("# ") and not _TASK_DOC_CREATED_RE.search(line)
    ]
    detail = "\n".join(body_lines).strip()

    return {
        "ts": ts,
        "project": project,
        "task_slug": slug,
        "tag": TASK_DOC_TAG,
        "machine": machine,
        # 설명서에는 `(via ...)` 꼬리표가 없다 — 사람이 만든 문서이지 AI가 남긴
        # 로그 줄이 아니므로 출처 라벨이 애초에 붙지 않는다.
        "via": None,
        "text": title,
        "detail": detail,
    }


def task_docs(project: str | None = None) -> list[dict[str, str | None]]:
    """개인 풀의 task.md 전부를 journal()과 같은 모양으로 합쳐 최신순 반환한다.

    journal()에 합치지 않고 함수를 나눈 이유: journal()은 검색만 쓰는 게 아니라
    브리핑의 "최근 활동"과 마무리 검사(closing_guard)도 함께 쓴다. 설명서를 거기
    섞으면 오늘 아무 일도 없던 작업 84개가 활동 목록에 나타나 "어제 무슨 일이
    있었나"의 답이 망가진다. 설명서가 필요한 곳은 검색뿐이라 합류 지점도 검색
    색인 한 곳(`db._bowl_rows`)뿐이다.

    필터 인자를 두지 않은 이유: 이 결과는 색인에 통째로 담기고 걸러내기는 SQL이
    한다(설계서 6장 5단계). 여기에 파이썬 필터를 또 두면 같은 규칙이 두 벌이 된다.

    stdlib 전용 유지 — journal()과 같은 모듈 규약이다.
    """
    if project is None:
        targets = [(name, _tasks_pool_root() / name) for name in list_projects()]
    else:
        root = tasks_root_for(project)
        targets = [(root.name, root)]

    entries: list[dict[str, str | None]] = []
    for project_name, tasks_root in targets:
        try:
            doc_files = sorted(tasks_root.glob("*/task.md"))
        except OSError:
            continue
        for doc_path in doc_files:
            entry = parse_task_doc(doc_path, project_name)
            if entry is not None:
                entries.append(entry)

    entries.sort(key=lambda e: (e["ts"], e["project"], e["task_slug"]), reverse=True)
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
