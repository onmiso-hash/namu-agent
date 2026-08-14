"""작업(task)을 다른 프로젝트 방으로 옮긴다 — 설계서 4단계(`docs/new_project_rule.md` 7장).

## 왜 여기 한 곳인가

`project_policy.py`와 같은 이유다 — 클라우드(`namu-cloud-routing`)가 이 repo를 vendor
서브모듈로 얹어 그대로 import한다. 그래서 이 모듈은:

- `Path.home()`이나 cwd에 의존하지 않는다. 뿌리 경로(`source_root`/`dest_root`)는
  전부 호출자가 인자로 준다(`task_resolve.tasks_root_for`가 이미 그 규칙을 가지고
  있으니, 여기서 다시 만들지 않는다).
- 시각(`ts`)은 호출자가 `cfg.now()`로 만들어 넘긴다 — `task_resolve.set_pin`과 같은
  이유: 이 모듈은 config를 부르지 않으므로 `datetime.now()`를 직접 쓰면 시간대가
  다른 호스트(웹 컨테이너=UTC)의 기록과 선후가 뒤집힌다.
- 문안에 쓰는 호칭은 `person` 인자로 받는다(개인용 '사용자' / 클라우드 '회원') —
  `project_policy._web_ask_message`와 같은 방식.

## 조건 ①(설계서 4장) — 이미 있는 방으로만

`resolve_move_destination`이 이 조건의 문지기다. 없는 이름을 주면 거절하되, 그
메시지는 **오류가 아니라 사람에게 그대로 보여줄 방 목록**이다(`project_policy`의
`_web_ask_message`와 같은 문체). 목록에 "새 프로젝트로 만들기"를 넣지 않는 것이
이 함수의 존재 이유다 — 넣는 순간 옮기기가 새 프로젝트를 만드는 우회로가 되고,
`new_project_rule.md` 2장이 두 번 겪은 사고(AI가 그 항목을 스스로 골라 새 방이
생김)가 그대로 재현된다.

## 조건 ②(설계서 4장) — 책갈피를 같이 정리

`move_task`가 처리한다. 책갈피(`.pin.<기기>`)는 프로젝트 폴더 **안에** 있는 파일이라,
작업 폴더만 옮기면 옛 방에 남은 책갈피가 없는 작업을 가리키게 된다(`task_resolve`
모듈 docstring이 이미 설명하는 문제의 연장선). 기기별로 파일이 갈리므로(git 충돌
0의 근거) 기기마다 따로 본다 — 옮긴 목적지에 그 기기의 책갈피가 이미 있으면
덮어쓰지 않는다(그 기기가 목적지에서 이미 다른 작업을 가리키고 있는데 말없이
지우면 그쪽 사람의 표시가 사라진다).

## 조건 ③(설계서 4장) — 옮기는 일은 한 곳에서만

기기 간 잠금은 만들 수 없다(파일 기반 동기화라 서버가 없다). 그래서 이 모듈은
안전장치를 지어내지 않는다 — `move_task`의 docstring이 위험을 그대로 적어 알릴
뿐이고, 창을 좁히는 실질적 조치(옮긴 직후 곧바로 `memory_sync.sync_push`를 부르는
것)는 호출자(`mcp_server.namu_task_move`)의 몫이다. 이 모듈은 memory_sync를 부르지
않는다 — vendor 서브모듈로 얹였을 때 클라우드의 동기화 방식까지 강제하지 않기
위해서다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import task_resolve

# task_resolve._parse_log_line이 읽는 형식(`[태그] YYYY-MM-DD HH:MM:SS <기기> · 내용`)과
# 정확히 같은 모양이어야 한다 — 새 형식을 만들면 이 줄만 통합 검색·브리핑에서 못 읽힌다.
_MOVE_LOG_TAG = "기록"


def _move_ask_message(requested: str | None, known: list[str], person: str) -> str:
    """만들기 전에 사람에게 그대로 보여줄 질문 — `project_policy._web_ask_message`와
    같은 형태다. 목록에는 **이미 있는 방뿐**이다 — 새로 만드는 항목이 없으니
    AI가 안 물어보고 아무거나 골라도 새 프로젝트는 생기지 않는다.
    """
    if requested:
        head = f"방 {requested!r}는 없습니다 — 아무것도 옮기지 않았습니다."
    else:
        head = "어느 방으로 옮길지 아직 정해지지 않았습니다."

    if known:
        lines = [f"  {i}. {name}" for i, name in enumerate(known, start=1)]
        listed = "\n".join(lines)
    else:
        listed = "  (아직 다른 방이 없습니다)"

    return (
        f"{head}\n\n"
        "작업은 **이미 있는 방**으로만 옮길 수 있습니다 — 옮기기로 새 방이 생기면 "
        "새 프로젝트를 막아 둔 이유가 그대로 무너집니다.\n\n"
        f"어디로 옮길지는 {person}만 정할 수 있습니다. 아래 질문을 그대로 보여주고 "
        "답을 기다리세요.\n\n"
        f"── {person}에게 보여줄 질문 ──\n"
        "이 작업을 어느 방으로 옮길까요?\n"
        f"{listed}\n"
        "──────────────────\n\n"
        f"{person}에게 답을 받은 뒤, 고른 이름을 to로 줘 다시 부르세요."
    )


def resolve_move_destination(to: str | None, *, known: list[str], person: str = "사용자") -> str:
    """옮길 방 이름을 정한다. `known`(그 사람이 이미 가진 방 이름 목록)에 있으면 그대로
    반환, 없거나 비었으면 ValueError(사람에게 그대로 보여줄 방 목록)를 던진다.

    설계서 4장 조건 ① — 옮기기로 새 프로젝트가 생기는 길은 없다. `resolve_create_project`
    (`project_policy.py`)와 짝을 이루는 함수이지만 성격이 다르다: 저기는 "새로 만들
    수 있는 이름 하나(WEB_PROJECT)"를 더 얹어 목록을 만들지만, 여기는 얹지 않는다 —
    옮기기는 애초에 새 방을 만드는 경로가 아니어야 한다.
    """
    requested = (to or "").strip()
    if requested and requested in known:
        return requested
    raise ValueError(_move_ask_message(requested or None, known, person))


def _append_move_log_line(task_dir: Path, machine: str, ts: str, text: str) -> None:
    """옮긴 작업의 log.md 끝에 `[기록]` 한 줄을 append한다.

    `mcp_server._append_task_log_line`과 같은 트레일링 개행 안전 처리를 그대로
    따르되, 이 모듈이 mcp_server를 import할 수 없어(mcp_server가 이 모듈을
    import하므로 반대 방향은 순환 임포트) 여기서 다시 구현한다 — 로직이 세 줄뿐이라
    복제 비용보다 순환 임포트를 피하는 이득이 크다. 형식은 `task_resolve`가 읽는
    로그 줄 규약과 정확히 같다: `[기록] YYYY-MM-DD HH:MM:SS <기기> · <내용>`.
    """
    log_path = task_dir / "log.md"
    needs_leading_nl = False
    if log_path.exists():
        with log_path.open("rb") as f:
            f.seek(0, 2)
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_leading_nl = f.read(1) != b"\n"
    line = f"[{_MOVE_LOG_TAG}] {ts} {machine} · {text}"
    with log_path.open("a", encoding="utf-8") as f:
        if needs_leading_nl:
            f.write("\n")
        f.write(line + "\n")


def _move_pins(source_root: Path, dest_root: Path, slug: str) -> tuple[list[dict], list[dict]]:
    """설계서 4장 조건 ② — 이 slug를 가리키는 원본 방의 책갈피를 전부 목적지로
    옮기거나(목적지에 그 기기 책갈피가 없을 때) 원본 것만 뗀다(있을 때).

    반환: (moved, dropped) — 각각 `{"machine", "ts"}` 목록(dropped는 ts를 안 갖는다.
    뗀 뒤에는 더 이상 존재하지 않는 값이라서다).
    """
    dest_machines = {p["machine"] for p in task_resolve.read_pins(dest_root)}

    moved: list[dict] = []
    dropped: list[dict] = []
    for pin in task_resolve.read_pins(source_root):
        if pin["slug"] != slug:
            continue
        machine = pin["machine"]
        if machine in dest_machines:
            # 목적지에 그 기기가 이미 다른(또는 같은) 작업을 가리키고 있다 —
            # 말없이 덮어쓰면 그쪽 사람의 표시가 사라지므로 원본 것만 뗀다.
            task_resolve.clear_pin(source_root, machine)
            dropped.append({"machine": machine})
        else:
            task_resolve.set_pin(dest_root, machine, slug, pin["ts"])
            task_resolve.clear_pin(source_root, machine)
            moved.append({"machine": machine, "ts": pin["ts"]})
    return moved, dropped


def move_task(*, source_root: Path, dest_root: Path, slug: str, machine: str, ts: str) -> dict:
    """작업 폴더 하나를 `source_root`에서 `dest_root`로 옮긴다(설계서 4단계 실제 이동).

    ⚠ **여러 기기에서 동시에 옮기지 말 것.** log.md는 여러 PC가 줄 단위로
    union merge하는 것을 전제로 설계됐다(append-only, git 충돌 0의 근거가 "각
    기기는 제 줄만 붙인다"는 것). 한쪽이 폴더를 옮기는 도중 다른 쪽이 같은
    task의 옛 자리 log.md에 줄을 붙이면, 그 줄은 옮겨진 새 자리로 못 따라가고
    두 자리에 걸쳐 남거나 다음 동기화 때 충돌한다. 이 함수에는 기기 간 잠금이
    없다(파일 기반 동기화만 있는 구조에서 만들 수 없다) — 창을 좁히는 유일한
    조치는 호출자가 옮긴 직후 곧바로 `memory_sync.sync_push`로 밀어 올리는
    것뿐이다(여기서는 하지 않는다 — 이 모듈은 memory_sync를 부르지 않는다).

    동작 순서:
      1. `source_root/slug`가 없으면 ValueError.
      2. `source_root == dest_root`면 ValueError(옮길 필요가 없다).
      3. `dest_root/slug`가 이미 있으면 ValueError — **합치지 않는다.** log.md는
         append-only라 두 파일을 섞으면 어느 쪽 기록인지 영영 알 수 없어진다.
      4. 폴더를 옮긴다(`dest_root`가 없으면 만든다).
      5. 이 slug를 가리키는 원본 방의 책갈피를 전부 정리한다(`_move_pins`).
      6. 목적지 log.md 끝에 `[기록]` 한 줄로 이관 사실을 남긴다(`machine`/`ts`는
         이 줄에 쓰인다 — `task_resolve.set_pin`이 시각을 인자로 받는 것과 같은
         이유로, 이 모듈이 config를 직접 부르지 않기 때문이다).

    반환: `{"slug", "from_project", "to_project", "moved_pins", "dropped_pins"}`.
    `from_project`/`to_project`는 `source_root.name`/`dest_root.name`(=방 이름,
    `tasks_root_for`가 만드는 마지막 폴더명과 같다).
    """
    source_dir = source_root / slug
    if not source_dir.is_dir():
        raise ValueError(f"작업 {slug!r}가 {source_root.name!r}에 없습니다")

    if source_root == dest_root:
        raise ValueError(
            f"작업 {slug!r}는 이미 {source_root.name!r}에 있습니다 — 옮길 필요가 없습니다"
        )

    dest_dir = dest_root / slug
    if dest_dir.exists():
        raise ValueError(
            f"작업 {slug!r}는 이미 {dest_root.name!r}에 있습니다 — 옮기지 않았습니다"
            "(같은 슬러그가 있으면 합치지 않고 거절합니다)"
        )

    dest_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_dir), str(dest_dir))

    moved_pins, dropped_pins = _move_pins(source_root, dest_root, slug)

    _append_move_log_line(
        dest_dir, machine, ts, f"방을 {source_root.name}에서 {dest_root.name}으로 옮김"
    )

    return {
        "slug": slug,
        "from_project": source_root.name,
        "to_project": dest_root.name,
        "moved_pins": moved_pins,
        "dropped_pins": dropped_pins,
    }
