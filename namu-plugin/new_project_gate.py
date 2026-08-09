"""새 프로젝트 게이트 — "처음 보는 프로젝트 이름"은 사람이 고르기 전에는 안 만든다.

## 왜 이 파일이 따로 있나

앞선 판(web-new-project-gate 1차)은 같은 검사를 두 곳에 **손으로 옮겨 적었다** —
개인용 `mcp_server._create_task_entry`와 클라우드
`namu-cloud-routing/src/routing_server._create_task_entry`. 코어에 먼저 넣고
클라우드에는 안 넣었더니 배포해도 웹에서 그대로 뚫렸고(실측: 'blog-summary-bot'이
확인 없이 생김), 원인을 찾는 데 세션 절반이 들었다. 클라우드는 이 폴더를 vendor
서브모듈로 얹어 `task_resolve` 등을 그대로 import하므로, 갈라질 이유가 없는 정책은
여기 한 곳에 둔다.

## 무엇을 막는가 (1차와 달라진 점)

1차 게이트는 "확인 칸 없이 **한 번에** 만들기"만 막았다. 그런데 거절 메시지가
마지막 줄에서 `new_project=True를 붙여 다시 호출하세요`라고 **우회 방법을 그 자리에
알려줬고**, 웹의 AI는 사람에게 묻지 않은 채 그 칸을 스스로 켜서 곧바로 다시 불렀다
(실측 2회: blog-summary-bot, blog-auto-bot). 거절은 AI를 멈추게 하지 못하고 한 번
더 부르게 했을 뿐이며, 그 사이에 사람이 낀다는 보장이 없었다.

그래서 2차는 두 가지를 더한다.

- **질문 문안을 돌려준다** — 무엇을 물어야 하는지 설명하는 대신, 사람에게 그대로
  보여줄 번호 매긴 선택지를 만들어 준다. 물어보는 비용을 0으로 만들어야 묻는다.
- **질문을 보여준 적 없는 이름은 확인 칸을 켜도 거절한다** — 첫 호출은 `new_project`
  값과 무관하게 언제나 질문으로 돌아온다. 처음 구현할 때 이 조건을 "거절 직후
  재시도"에만 걸었더니, AI가 **첫 호출부터 칸을 켜기만 하면** 질문을 한 번도 안
  보여주고 통과하는 더 쉬운 구멍이 남았다(검수에서 잡힘). `new_project`는 도구
  설명에 드러나 있는 평범한 참/거짓 칸이라 AI가 그 존재를 처음부터 안다.
- **답할 시간이 없었던 재시도도 거절한다** — 질문을 돌려준 시각을 기억해 두고,
  `COOLDOWN_SECONDS` 안에 같은 이름으로 `new_project=True`가 오면 거절한다. AI가
  혼자 답을 지어내는 경로(1~5초)와 사람이 목록을 읽고 답하는 경로(보통 십수 초
  이상)를 가르는 것은 **경과 시간**뿐이다 — AI가 채우는 어떤 칸도 "사람이 답했다"를
  증명하지 못하기 때문이다(칸은 AI가 스스로 채울 수 있다).

정리하면 새 프로젝트는 **질문 → (사람이 읽을 만한 시간) → 재호출** 두 걸음을 반드시
거친다. 사람이 미리 "새 프로젝트로 만들어"라고 말해 둔 경우에도 첫 걸음은 생략되지
않는다 — "사람이 진짜 미리 정했다"와 "AI가 스스로 정하고 칸만 켰다"는 참/거짓 칸
하나로 구분할 수 없고, 구분할 수 있다고 믿은 것이 1차 판이 뚫린 이유다.

시간 문턱은 증명이 아니라 문턱이다. 사람이 아주 빨리 답하면 한 번 헛걸음할 수
있는데, 그때는 몇 초 뒤 재시도가 통과하므로 손해가 지연뿐이다.

## 기억은 프로세스 안에만 둔다

질문한 시각은 모듈 전역 dict에 담는다 — 파일로 남기면 클라우드에서는 회원 저장소에
git 커밋이 쌓이고(동기화 대상 폴더다) 개인용에서는 지울 사람이 없는 찌꺼기가 된다.

이 방식은 **서버가 한 프로세스로 뜬다는 전제**에 기댄다(클라우드는 `uvicorn.run`을
workers 없이 부른다 — 같은 전제를 `ask_limit.py`가 먼저 문서화해 뒀다). 나중에
워커를 여럿으로 늘리면 이 기억이 프로세스마다 따로 놀아, 재호출이 다른 워커에
닿으면 "질문한 적 없음"으로 보여 거절된다 — 뚫리는 쪽이 아니라 막히는 쪽으로
어긋나므로 위험하지는 않지만, 그때는 기억을 공유 저장소로 옮겨야 한다.

서버가 재시작하면 잊는다. 잊었을 때는 다음 호출이 다시 질문으로 돌아가므로 이쪽도
막히는 쪽으로 무너진다.
"""
from __future__ import annotations

import time

# 사람이 목록을 읽고 답하기에는 짧고, AI가 곧바로 다시 부르기에는 긴 시간.
# 실측 근거: AI의 즉시 재시도는 도구 호출 사이 1~5초였다(2026-08-09 웹 재현 2회).
COOLDOWN_SECONDS = 15.0

# {(scope, project): 질문을 돌려준 시각(monotonic)}
_asked_at: dict[tuple[str, str], float] = {}


def _subject(person: str) -> str:
    """'사용자'/'회원'에 주격 조사를 붙인다 — 끝 글자에 받침이 있으면 '이', 없으면 '가'.

    호칭을 두 곳(개인용/클라우드)에서 갈아 끼우다 보니 조사를 하나로 박아둘 수 없다.
    """
    last = person[-1]
    if "가" <= last <= "힣":
        has_batchim = (ord(last) - ord("가")) % 28 != 0
        return person + ("이" if has_batchim else "가")
    return person + "이"


def _question_block(project: str, existing: list[str]) -> str:
    """사람에게 그대로 보여줄 선택지. 번호는 1번부터, 0번이 '새로 만들기'다."""
    if existing:
        lines = [f"  {i}. {name}" for i, name in enumerate(existing, start=1)]
    else:
        lines = ["  (아직 만들어 둔 프로젝트가 하나도 없습니다)"]
    lines.append(f"  0. 새 프로젝트로 만들기 — '{project}'")
    return "이 작업을 어느 프로젝트에 넣을까요?\n" + "\n".join(lines)


def _how_to_continue(person: str) -> str:
    return (
        f"{_subject(person)} 기존 프로젝트를 골랐으면 project를 그 이름으로 바꿔 다시 "
        f"부르세요. '새 프로젝트로 만들기'를 골랐을 때만 그대로 다시 부르세요."
    )


def _framed_question(project: str, existing: list[str], person: str) -> str:
    return (
        f"── {person}에게 보여줄 질문 ──\n"
        f"{_question_block(project, existing)}\n"
        f"──────────────────"
    )


def _ask_message(project: str, existing: list[str], person: str) -> str:
    return (
        f"프로젝트 '{project}'는 지금까지 없던 새 이름입니다 — 아직 아무것도 "
        f"만들지 않았습니다.\n\n"
        f"어디에 넣을지는 {person}만 정할 수 있습니다. 아래 질문을 {person}에게 "
        f"그대로 보여주고 답을 기다리세요.\n\n"
        f"{_framed_question(project, existing, person)}\n\n"
        f"{_how_to_continue(person)}\n"
        f"{person}의 답 없이 곧바로 다시 부르면 또 거절됩니다."
    )


def _never_asked_message(project: str, existing: list[str], person: str) -> str:
    return (
        f"프로젝트 '{project}'는 지금까지 없던 새 이름입니다 — 아직 아무것도 "
        f"만들지 않았습니다.\n\n"
        f"확인 칸을 켠 것만으로는 {_subject(person)} 골랐다는 뜻이 되지 않습니다"
        f"(그 칸은 부르는 쪽이 스스로 켤 수 있습니다). 이 이름으로는 아직 "
        f"{person}에게 질문을 보여준 적이 없으므로 만들지 않습니다.\n\n"
        f"{_framed_question(project, existing, person)}\n\n"
        f"{_how_to_continue(person)}"
    )


def _too_soon_message(project: str, existing: list[str], person: str, waited: float) -> str:
    return (
        f"방금({waited:.0f}초 전) 같은 질문을 돌려드렸습니다 — {_subject(person)} 읽고 "
        f"답할 시간이 없었습니다. 답을 받지 않고 스스로 '새 프로젝트가 맞다'고 정한 "
        f"것으로 봅니다.\n\n"
        f"이 이름으로 새 프로젝트를 만들지는 {person}만 정할 수 있습니다. 아래 질문을 "
        f"{person}에게 보여주고 답을 받은 뒤에 다시 부르세요.\n\n"
        f"{_framed_question(project, existing, person)}"
    )


def check(
    project: str,
    existing: list[str],
    *,
    new_project: bool,
    scope: str = "",
    person: str = "사용자",
) -> None:
    """새 작업을 만들기 직전에 부른다. 통과하면 조용히 돌아오고, 아니면 ValueError.

    - `project`가 `existing`에 있으면 아무 일도 하지 않는다(게이트는 처음 보는
      이름에만 걸린다 — 매번 걸리면 기존 사용이 깨진다).
    - 처음 보는 이름인데 이 이름으로 아직 질문을 돌려준 적이 없으면 거절한다.
      `new_project`가 참이어도 마찬가지다 — 첫 호출은 언제나 질문으로 돌아간다.
    - 질문은 했지만 사람이 읽고 답할 시간이 없었으면(문턱 이내) 또 거절한다.

    `scope`는 질문 기억을 가르는 칸이다 — 클라우드는 회원 키를 넣어 다른 회원의
    질문·답이 서로 영향을 주지 않게 한다. `person`은 메시지에 쓰는 호칭
    (개인용 '사용자' / 클라우드 '회원').
    """
    key = (scope, project)

    if project in existing:
        _asked_at.pop(key, None)
        return

    now = time.monotonic()
    asked = _asked_at.get(key)

    if not new_project:
        _asked_at[key] = now
        raise ValueError(_ask_message(project, existing, person))

    if asked is None:
        _asked_at[key] = now
        raise ValueError(_never_asked_message(project, existing, person))

    if now - asked < COOLDOWN_SECONDS:
        raise ValueError(_too_soon_message(project, existing, person, now - asked))

    _asked_at.pop(key, None)


def _reset_for_tests() -> None:
    """질문 기억을 비운다 — 시험이 서로 간섭하지 않게 하는 용도."""
    _asked_at.clear()


def _prime_for_tests(project: str, scope: str = "") -> None:
    """"질문을 이미 보여줬고 사람이 답하고 왔다"는 상태를 심는다.

    게이트가 관심사가 아닌 시험(작업 생성 자체를 보는 시험)이 매번 거절-대기-재호출
    두 걸음을 흉내내지 않아도 되게 한다. 이 함수 없이 시험을 쓰면 두 걸음이 시험마다
    복사되고, 그 복사본들이 게이트를 고칠 때마다 한꺼번에 깨진다.
    """
    _asked_at[(scope, project)] = time.monotonic() - COOLDOWN_SECONDS - 1.0
