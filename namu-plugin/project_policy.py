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
- **웹** — 새 프로젝트는 생기지 않는다. 이미 있는 방 이름을 주면 그 방에 만들고,
  처음 보는 이름이거나 이름이 없으면 `WEB_PROJECT` 한 곳으로 간다(거절하지 않는다 —
  자리가 정해져 있으니 물을 것이 없다). 웹에는 폴더를 여는 단계가 통째로 없어서, 그
  빈자리를 AI가 쓴 글자 하나가 대신하던 것이 사고의 뿌리였다(실사고:
  onnamu-security · blog-summary-bot · blog-auto-bot). **이름이 새 폴더를 만들지
  못하게 되면** 그 글자로 할 수 있는 일은 이미 있는 방을 고르는 것뿐이고, 그것은
  일지를 덧붙이는 일과 같은 무게다.

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


def resolve_create_project(
    project: str | None,
    *,
    is_web: bool,
    cwd_project: str | None = None,
    existing: list[str] | None = None,
) -> tuple[str, str | None]:
    """새 작업(create)을 만들 프로젝트를 정한다. `(프로젝트, 안내문|None)`을 돌려준다.

    안내문은 부른 쪽이 준 이름을 쓰지 않았을 때만 채워진다 — 조용히 다른 자리에
    만들면 부른 쪽도 사람도 어디에 들어갔는지 모른다.

    `is_web`이면 `cwd_project`는 보지 않는다(웹에는 열린 폴더가 없다).
    """
    requested = (project or "").strip() or None
    known = list(existing or [])

    if is_web:
        if requested and requested in known:
            return requested, None
        if requested and requested != WEB_PROJECT:
            notice = (
                f"ℹ {requested!r}는 아직 없는 프로젝트입니다 — 웹에서는 새 프로젝트를 "
                f"만들지 않으므로 {WEB_PROJECT!r}에 만들었습니다. 이미 있는 방 이름을 "
                f"주면 그 방에 만듭니다. 새 프로젝트는 그 폴더를 연 PC에서 생깁니다."
            )
            return WEB_PROJECT, notice
        return WEB_PROJECT, None

    if not cwd_project:
        raise ValueError(
            "지금 열려 있는 폴더를 알 수 없어 새 작업을 만들 자리를 정하지 "
            "못했습니다"
        )

    if requested is None or requested == cwd_project:
        return cwd_project, None

    if requested in known:
        return requested, None

    raise ValueError(_unknown_project_message(requested, cwd_project, known))
