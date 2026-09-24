"""새 작업을 어느 프로젝트에 만들 것인가 — 자리를 정하는 규칙 한 곳.

## 왜 검사가 아니라 규칙인가

앞선 두 판(web-new-project-gate 1·2차)은 전부 **AI가 채워 넣는 값을 검사하는**
방식이었다 — 확인 칸(`new_project`)을 요구하고, 질문 문안을 돌려주고, 15초를 쟀다.
셋 다 뚫렸다. 마지막 문턱은 배포 확인 중에 우리 손으로 뚫었다(그때 만들어진
`deploy-check-0165`가 지금도 남아 있다). AI가 채우는 값을 보는 검사는 AI가 그 값을
채우면 열리기 때문이다.

그래서 검사를 촘촘히 하는 대신 **AI가 새 프로젝트 이름을 적어 넣을 자리 자체를**
없앤다. 경계는 한 줄이다 — 일할 자리를 정하는 것은 사람, 그 자리에서 일을 벌이는
것은 AI.

## 규칙

- **내 PC(stdio)** — 새 프로젝트는 지금 열려 있는 폴더 이름에서만 자동으로 생긴다.
  폴더를 연 것이 사람의 행위이므로 이름도 사람에게서 나온다. `project`를 명시로
  적어 넣었는데 없는 이름이면 거절한다(그 이름이 지금 열린 폴더와 같으면 통과 —
  생략한 것과 결과가 같고, 이름의 출처도 여전히 사람이다).
- **웹** — 새 프로젝트는 생기지 않는다. 이미 있는 방 이름이나 `WEB_PROJECT`를 주면
  그대로 만들고, **그 밖의 경우(이름이 없거나 처음 보는 이름)에는 만들지 않고 방
  목록을 돌려준다** — 사람이 고르라고. 웹에는 폴더를 여는 단계가 통째로 없어서, 그
  빈자리를 AI가 쓴 글자 하나가 대신하던 것이 사고의 뿌리였다(실사고:
  onnamu-security · blog-summary-bot · blog-auto-bot).

## 목록을 돌려주는 것이 왜 걷어낸 게이트와 다른가

2차 게이트도 질문을 돌려줬고 뚫렸다. 그 판의 급소는 질문 자체가 아니라 **선택지에
'새 프로젝트로 만들기 — <지어낸 이름>'이 들어 있었다**는 것이다. AI가 그 항목을
스스로 고르면 사고가 그대로 재현됐고, 그래서 확인 칸과 시간 문턱을 덧대다 결국 다
뚫렸다.

지금 목록에는 **이미 있는 방과 `WEB_PROJECT`뿐**이다. AI가 사람에게 안 물어보고 아무
거나 골라도 새 프로젝트는 생기지 않는다 — 최악이 "방을 잘못 골랐다"이고, 그건 되돌릴
수 있다. 막을 값이 없으니 확인 칸도 시간 문턱도 두지 않는다.

이미 있는 작업에 일지를 덧붙이는 길(create 아님)은 양쪽 다 손대지 않는다 — 폴더가
새로 생기지 않으므로 막을 이유가 없다.

## 왜 코어에 있나

클라우드(`namu-cloud-routing`)는 이 폴더를 vendor 서브모듈로 얹어 그대로 import
한다. 1차 판은 같은 판정을 개인용 `mcp_server`와 클라우드 `routing_server`에 손으로
옮겨 적었고, 코어만 고쳐 배포한 탓에 웹이 그대로 뚫렸다 — 원인을 찾는 데 세션
절반이 들었다. 갈라질 이유가 없는 정책은 여기 한 곳에 둔다.
"""
from __future__ import annotations

# 웹에서 만든 작업이 모이는 방 하나. 웹에는 "지금 열려 있는 폴더"가 없으므로
# 이름을 고를 사람이 없고, 그래서 고르지 않는다.
WEB_PROJECT = "web-project"


# 방 이름·작업 이름 안에 들어가면 안 되는 글자. `/`·`\`는 경로를 가르는 글자이고,
# `:`는 윈도우에서 `Path(뿌리) / "C:"`가 뿌리를 통째로 갈아 끼우는 글자다(미니PC가
# 윈도우라 실제로 도는 자리다).
_PATH_CHARS = ("/", "\\", ":")


def validate_room_name(name: str | None, *, label: str = "project(방 이름)") -> str:
    """방 이름(또는 작업 이름) 하나를 **폴더 이름 한 칸**으로만 쓸 수 있게 거른다.

    ## 왜 필요한가 (2026-09-25 실측)

    방 이름은 `~/.namu/tasks/<이름>`에 그대로 이어 붙는다. 그런데 `'..'`를 주면 그
    자리가 `~/.namu` 자체가 되고, `'/'`를 주면 방 목록이 통째로 "작업"으로 보인다.
    검토에서 `namu_task_move(task='memory', to='web-project', project='..')` 한 번에
    교훈 원본 폴더(`~/.namu/memory`)가 남의 방 안으로 옮겨지는 것을 재현했다 — 웹
    주소로도 부를 수 있는 도구다.

    ## 왜 허용 목록이 아니라 금지 목록인가

    클라우드의 `_validate_project_name`은 영숫자·점·하이픈·밑줄만 받는다. 거기서는
    회원이 고른 이름만 방이 되므로 그걸로 충분하다. 개인용에서는 **방 이름이 사람이
    연 폴더의 이름**이라 한글·공백이 섞일 수 있고, 허용 목록으로 좁히면 이미 있는
    방을 못 부르게 된다. 그래서 "폴더 한 칸을 벗어나게 하는 것"만 막는다 — 빈 값,
    `.`/`..`, 경로 글자(`/`·`\\`·`:`), 제어 문자, 그리고 `.`으로 시작하는 이름(숨은
    폴더 — `.git`이나 책갈피 `.pin.*` 같은 살림 파일 자리다). 클라우드 규칙을 통과하는
    이름은 전부 여기서도 통과하므로 두 규칙이 서로 어긋나지 않는다.

    통과하면 앞뒤 공백을 걷은 이름을, 아니면 ValueError(부르는 쪽에 그대로 보일 안내문).
    """
    raw = "" if name is None else str(name)
    value = raw.strip()
    problem = None
    if not value:
        problem = "비어 있습니다"
    elif value in (".", ".."):
        problem = f"{value!r}는 폴더 자신이나 그 위를 가리킵니다"
    elif any(ch in value for ch in _PATH_CHARS):
        problem = "경로 글자('/', '\\\\', ':')가 들어 있습니다"
    elif any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        problem = "제어 문자(줄바꿈 등)가 들어 있습니다"
    elif value.startswith("."):
        problem = "'.'으로 시작합니다(숨은 폴더 자리입니다)"
    if problem:
        raise ValueError(
            f"{label} {raw!r}는 쓸 수 없습니다 — {problem}. 이름은 폴더 이름 한 칸이어야 "
            "하며 다른 폴더를 가리킬 수 없습니다. 예: 'namu-agent'"
        )
    return value


def _unknown_project_message(
    project: str, cwd_project: str, existing: list[str]
) -> str:
    known = ", ".join(existing) if existing else "(아직 없습니다)"
    return (
        f"프로젝트 {project!r}는 아직 없습니다 — 아무것도 만들지 않았습니다.\n\n"
        f"새 프로젝트는 **지금 열려 있는 폴더**에서만 생깁니다. 어디서 일할지는 "
        f"폴더를 여는 사람이 정하는 것이고, 부르는 쪽이 이름을 적어 넣어 정하는 "
        f"것이 아니기 때문입니다.\n\n"
        f"- {project!r}에서 일하려면: 그 폴더를 열고 거기서 다시 부르세요.\n"
        f"- 지금 열린 폴더에 만들려면: project를 생략하세요(→ {cwd_project!r}).\n"
        f"- 이미 있는 프로젝트에 만들려면: 그 이름을 그대로 주세요 — {known}"
    )


def web_choices(known: list[str]) -> list[str]:
    """웹에서 고를 수 있는 방 목록 — 이미 있는 방들 + `WEB_PROJECT`.

    `WEB_PROJECT`는 아직 폴더가 없어도 언제나 마지막 자리에 선다(웹에서 만든 작업이
    모이는 기본 자리라, 첫 작업을 만들 때도 고를 수 있어야 한다).
    """
    rooms = [name for name in known if name != WEB_PROJECT]
    return rooms + [WEB_PROJECT]


def _web_ask_message(requested: str | None, known: list[str], person: str) -> str:
    """만들기 전에 사람에게 그대로 보여줄 질문 — 번호만 고르면 되는 형태.

    목록에 **새 프로젝트를 만드는 항목은 없다.** 2차 게이트는 이 자리에 '새
    프로젝트로 만들기 — <지어낸 이름>'을 넣었고, AI가 그것을 스스로 골라 사고가
    재현됐다. 여기서 무엇을 고르든 이미 있는 방이거나 `WEB_PROJECT`이므로, 안 묻고
    고르더라도 최악이 "방을 잘못 골랐다"이다.
    """
    if requested:
        head = (
            f"프로젝트 {requested!r}는 아직 없습니다 — 아직 아무것도 만들지 "
            f"않았습니다."
        )
    else:
        head = "이 작업을 어느 방에 넣을지 아직 정해지지 않았습니다."

    choices = web_choices(known)
    lines = []
    for i, name in enumerate(choices, start=1):
        if name == WEB_PROJECT:
            lines.append(f"  {i}. {name} — 웹에서 만든 작업이 모이는 기본 자리")
        else:
            lines.append(f"  {i}. {name}")

    return (
        f"{head}\n\n"
        f"어디에 넣을지는 {person}만 정할 수 있습니다. 아래 질문을 그대로 보여주고 "
        f"답을 기다리세요.\n\n"
        f"── {person}에게 보여줄 질문 ──\n"
        f"이 작업을 어느 프로젝트에 넣을까요?\n"
        + "\n".join(lines)
        + "\n──────────────────\n\n"
        f"{person}에게 답을 받은 뒤, 고른 이름을 project로 줘 다시 부르면 그 방에 "
        f"만듭니다.\n"
        f"이 목록으로는 새 프로젝트를 만들 수 없습니다 — 새 프로젝트는 그 폴더를 연 "
        f"PC에서만 생깁니다."
    )


def resolve_create_project(
    project: str | None,
    *,
    is_web: bool,
    cwd_project: str | None = None,
    existing: list[str] | None = None,
    person: str = "사용자",
) -> str:
    """새 작업(create)을 만들 프로젝트를 정한다. 정해지면 그 이름, 아니면 ValueError.

    웹에서 방이 안 정해졌을 때의 ValueError는 오류가 아니라 **사람에게 그대로 보여줄
    질문**이다(`_web_ask_message`). `person`은 그 문안에 쓰는 호칭
    (개인용 '사용자' / 클라우드 '회원').

    `is_web`이면 `cwd_project`는 보지 않는다(웹에는 열린 폴더가 없다).
    """
    requested = (project or "").strip() or None
    if requested is not None:
        # 목록 대조보다 먼저 거른다 — 목록에 없는 이름은 어차피 거절되지만, 그 안내문이
        # '..'를 "아직 없는 방"처럼 말하게 두면 안 된다.
        requested = validate_room_name(requested)
    known = list(existing or [])

    if is_web:
        if requested == WEB_PROJECT or (requested and requested in known):
            return requested
        raise ValueError(_web_ask_message(requested, known, person))

    if not cwd_project:
        raise ValueError(
            "지금 열려 있는 폴더를 알 수 없어 새 작업을 만들 자리를 정하지 "
            "못했습니다"
        )

    if requested is None or requested == cwd_project:
        return cwd_project

    if requested in known:
        return requested

    raise ValueError(_unknown_project_message(requested, cwd_project, known))
