#!/usr/bin/env python3
"""나이테 — 세션 기록을 읽어 사용자가 AI를 되돌린 자리를 찾는다.

쓰는 법:
    python3 naite.py 되돌림                 최근 7일 — 요약만 보여준다
    python3 naite.py 되돌림 --자세히        낱낱을 표로 늘어놓는다
    python3 naite.py 되돌림 --최근 30       최근 30일
    python3 naite.py 되돌림 --전부          전체 기간
    python3 naite.py 되돌림 --날 2026-09-04 그날 하루
    python3 naite.py 되돌림 --방 naite      그 폴더에서 연 세션만
    python3 naite.py 되돌림 --넓게          약한 신호까지 포함(오탐이 늘어난다)
    python3 naite.py 되돌림 --원문          발화를 자르지 않는다(--자세히를 겸한다)

기본은 요약이다. 30일치 낱낱은 190줄이 넘어 화면에 담기지 않으므로,
먼저 갈래·날짜·방으로 어디에 몰렸는지 보고 --날·--방으로 파고든다.

이 도구는 기록을 읽기만 한다. 고치지 않는다.
"""

import argparse
import json
import pathlib
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

기록_뿌리 = pathlib.Path.home() / ".claude" / "projects"

# ── 사람 발화가 아닌 것들 ────────────────────────────────────────────
# 최상위 type이 'user'인 줄에는 사람 발화 말고도 여러 가지가 섞여 있다.
# 아래 표지로 시작하는 것은 시스템이 넣은 것이라 사람이 친 말이 아니다.
시스템_표지 = (
    "<task-notification>",      # 서브에이전트 완료 알림
    "<command-name>",           # 슬래시 명령
    "<command-message>",
    "<local-command-stdout>",
    "<bash-input>",             # ! 로 직접 실행한 명령
    "<bash-stdout>",
)

중단_표지 = (
    "[Request interrupted by user]",
    "[Request interrupted by user for tool use]",
)

# toolDenialKind 가운데 사람이 직접 거절한 것. 이것만 '도구 거절'(되돌림)로 센다.
사람_거절_종류 = frozenset({"user-rejected"})

# 사람이 '거절'해도 되돌림이 아닌 도구. AI가 띄운 선택지 질문 창(AskUserQuestion)을
# 닫고 글로 답하면 기록에는 user-rejected로 남는다. 2026-09-25 분석에서 사람의 거절
# 17건 중 9건이 이것이었고, 대부분 "접속자 주소는 로그인한 상태에서만 볼 수 있게
# 해줘." 같은 평범한 답이었다 — 질문에 답한 것이지 AI를 되돌린 것이 아니다.
되돌림_아닌_거절_도구 = frozenset({"AskUserQuestion"})

# 사람이 도구 호출을 한 번 거절하면 거절 표지와 "[Request interrupted by user for tool
# use]"가 같은 순간(실측 0.003초 차)에 두 줄로 남는다. 둘을 따로 세면 한 번의 거절이
# 두 건이 된다(2026-09-25 분석: 사람의 거절 17건 중 11건). 거절 뒤 이 초 안의 중단은
# 그 거절에 딸린 것으로 보고 따로 세지 않는다.
거절_짝_초 = 3

# 같은 말을 고쳐 다시 보낸 것. 앞 발화 전체가 뒤 발화의 첫머리와 같고(덧붙여 다시
# 보낸 것) 이 초 안이면, 말로 반박을 한 번만 센다(2026-09-04 "지도에 왜 나무클라우드
# 만을 넣는데? …"를 41초 뒤 한 문장을 덧붙여 다시 보냈다). 대화 기록 두 달치에서
# 이런 짝은 그 하나였고, 글자가 완전히 같은 재전송은 3분 넘게 떨어진 "세션
# 마무리해줘"·"닫아"뿐이라 되돌림과는 무관했다. 그래서 창을 짧게 잡았다.
재전송_초 = 120

# ── 되돌림 신호 ──────────────────────────────────────────────────────
# 실제 기록 782건에 대보고 적중 건수와 오탐을 눈으로 확인해 등급을 갈랐다.
# '강함'은 대부분 진짜 되돌림이었고, '약함'은 붙여넣은 남의 글까지 걸렸다.
강한_신호 = [
    ("되물음", re.compile(r"(아니지|아냐\s*\?|아니야\s*\?|아녔|아닌가|아닌데)")),
    ("강조 반복", re.compile(r"(라니깐|라니까|다니깐|다니까|분명히|라고\s*했|라고\s*말했)")),
    ("부정 시작", re.compile(r"^\s*아니[,\s]")),
    ("결과 부정", re.compile(r"(안\s?되었|안\s?됐|안\s?되네|안\s?되는데|변화가\s?없|"
                             r"그대로\s?(야|네|인데|돌아)|또\s?이러|또\s?그러)")),
    # 아래 셋은 사고 기록과 대조하다 놓친 것이 드러나 뒤에 더한 규칙이다.
    # 08-22 "그렇게 구현되었었잖아", 08-18 "썅~~ 이게 뭐야", 08-22 "그게 무슨말이야"를
    # 앞의 다섯 규칙이 하나도 잡지 못했다.
    ("되짚음", re.compile(r"(잖아|잖니|잖어|았었잖|었잖)")),
    ("감정 표출", re.compile(r"(씨발|시발|썅|쌍놈|미쳤|어이가\s?없|짜증|답답하|장난하)")),
    # '뭐야?' 단독은 뺐다. 전수 검사에서 "그게 뭐야? 설명해줘" 같은 단순 질문
    # 9건을 끌어왔고, 그것 때문에만 잡힌 진짜 되돌림은 1건뿐이었다.
    ("반문", re.compile(r"(이게\s?뭐야|무슨\s?말이|뭔\s?소리|뭔소리|"
                        r"어떻게\s?된\s?거|어떻게\s?된거|왜\s?이래|왜\s?그래)")),
    # 아래 둘은 2026-09-09에 오탐 19건을 손으로 가려내면서 더한 규칙이다.
    # '확인 추궁'을 약한 신호로 내리면 사용자가 앞뒤 모순을 짚은 세 건까지 함께
    # 놓치게 되는데, 그 세 건이 공통으로 쓰던 말투가 이 둘이었다.
    ("모순 지적", re.compile(r"(어떤\s?게?\s?맞|어느\s?게?\s?맞|뭐가\s?맞|"
                            r"말도\s?안\s?되|말이\s?안\s?되)")),
    # 종결형 '아니야·아냐'만 받는다. 연결형 '아니라'와 존댓말 '아닙니다'까지 받으면
    # 붙여넣은 홈페이지 문구 안의 남의 말이 걸렸다. 다만 발화 첫머리에서 사실을
    # 곧바로 뒤집는 '~게 아니라'는 되돌림이 확실해 앞머리 스무 자에 한해 받는다.
    ("사실 정정", re.compile(r"(이|가|게|건)\s?(아니야|아냐)(?=[\s.,!?~]|$)"
                            r"|^[^\n]{0,20}(게|것이|건)\s?아니라")),
    # 아래 셋은 2026-09-25 분석에서 더했다. 요청 중단 뒤에 나온 분명한 반박("배포
    # 절차서가 있지않아?", "이미 그렇게 되어 있지 않아?", "갈라? 이런말 쓰지마!",
    # "아냐.. 시험하지 말고 소스를 확인해!", "그만해")을 말로 반박이 하나도 못 잡았다.
    # 그때는 요청 중단으로 잡혔지만 끊지 않고 말만 했다면 놓쳤을 것이다. 측정값은
    # README "지금까지 잰 정확도" 참고.
    ("있던 것 짚기", re.compile(r"(있지\s?않아\s*\?|있지않아|되어\s?있지\s?않)")),
    ("금지", re.compile(r"((쓰|하)지\s?마(?=[!~.\s,]|$)|(쓰|하)지\s?말(고|라))")),
    ("멈춤", re.compile(r"(^\s*그만해|^\s*아냐[.,\s])")),
]

약한_신호 = [
    ("왜", re.compile(r"왜\s")),
    ("다시", re.compile(r"(다시\s|또\s)")),
    ("부정", re.compile(r"(안\s?되|안\s?나|없네|없는데|안\s?보이)")),
    ("제대로", re.compile(r"(제대로|검증한거|확인한거)")),
    # '맞아?·맞지?'는 2026-09-09 전수 검사에서 단독으로 열 건을 잡았는데 그중
    # 일곱이 "설치된 거 맞아?" 같은 단순 확인 질문이었다. 강한 신호에서 내렸다.
    ("확인 추궁", re.compile(r"(맞아\s*\?|맞지\s*\?|맞나\s*\?|맞는지)")),
]

# 붙여넣기로 보이는 기준. 사용자가 웹 AI의 답변이나 로그를 통째로 붙이면
# 그 안의 남의 말까지 신호로 걸린다. 숨기지 않고 표시만 달아 사람이 가리게 한다.
붙여넣기_길이 = 600
붙여넣기_줄수 = 8


def 화면폭(글자):
    """한글·한자는 두 칸을 차지한다. 표를 맞추려면 세어야 한다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in 글자)


def 폭맞춰_자르기(글자, 폭):
    글자 = re.sub(r"\s+", " ", 글자).strip()
    쌓임 = 0
    결과 = []
    for c in 글자:
        w = 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if 쌓임 + w > 폭 - 1:
            결과.append("…")
            break
        결과.append(c)
        쌓임 += w
    return "".join(결과)


def 칸채우기(글자, 폭):
    return 글자 + " " * max(0, 폭 - 화면폭(글자))


def 사람_발화인가(줄):
    """사람이 실제로 친 말이면 그 글을, 아니면 None을 돌려준다."""
    if 줄.get("type") != "user":
        return None
    if 줄.get("isMeta") or 줄.get("isSidechain"):
        # isMeta는 훅이 붙인 안내, isSidechain은 내가 서브에이전트에게 보낸 지시다.
        return None
    본문 = (줄.get("message") or {}).get("content")
    if isinstance(본문, str):
        글 = 본문
    elif isinstance(본문, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in 본문):
            return None
        조각 = [b.get("text", "") for b in 본문 if isinstance(b, dict) and b.get("type") == "text"]
        글 = "\n".join(t for t in 조각 if t)
    else:
        return None
    글 = 글.strip()
    if not 글:
        return None
    if 글.startswith(시스템_표지):
        return None
    return 글


def 대화_기록_파일들(뿌리=None):
    """사람과 나눈 대화 기록만 돌려준다 — 서브에이전트의 대화 기록은 뺀다.

    `<세션id>/subagents/agent-*.jsonl`에는 서브에이전트가 한 일이 따로 적힌다. 그
    안의 사람 쪽 줄은 전부 내가 보낸 지시라 발화로는 걸러지지만, 도구 거절 표지는
    그 파일에만 남는다(2026-09-25 실측: 본 기록과 겹치는 것 0건). 세션 종료 훅은 본
    대화 기록 한 장만 읽으므로 그 표지를 세지 않는다 — 여기서 함께 읽으면 명령줄
    숫자만 부풀어 두 숫자가 어긋난다. 주간 점검은 파일 이름을 세션 id로 쓰므로,
    빼지 않으면 서브에이전트 기록 한 장이 세션 하나로 세어지기도 한다.
    """
    뿌리 = 기록_뿌리 if 뿌리 is None else 뿌리
    return sorted(p for p in 뿌리.rglob("*.jsonl")
                  if "subagents" not in p.relative_to(뿌리).parts)


def 세션_읽기(파일):
    """파일 하나를 읽어 그 세션의 정보와 사람 발화 목록을 돌려준다."""
    제목 = None
    작업위치 = None
    발화 = []       # (시각, 글)
    중단 = []       # 시각
    거절 = []       # 시각 — 사람이 거절한 것(user-rejected)만
    자동차단 = []   # 시각 — 자동 모드 분류기 등 사람이 아닌 쪽이 막은 것
    선택창 = []     # 시각 — 사람이 선택지 질문 창을 닫은 것(되돌림 아님, 짝 중단을 거두는 데만 쓴다)
    거절_표지 = []  # (시각, 종류, 도구) — 가리지 않은 원본. 나중에 다시 가를 수 있게 둔다
    도구_이름 = {}  # tool_use id -> 도구 이름. 거절 줄에는 도구 이름이 없어 이것으로 찾는다
    for 줄글 in 파일.open(encoding="utf-8", errors="replace"):
        줄글 = 줄글.strip()
        if not 줄글:
            continue
        try:
            줄 = json.loads(줄글)
        except Exception:
            continue

        if 제목 is None and 줄.get("aiTitle"):
            제목 = 줄["aiTitle"]
        if 작업위치 is None and 줄.get("cwd"):
            작업위치 = 줄["cwd"]

        시각 = 줄.get("timestamp", "")

        if 줄.get("type") == "assistant":
            for 조각 in ((줄.get("message") or {}).get("content") or []):
                if isinstance(조각, dict) and 조각.get("type") == "tool_use" and 조각.get("id"):
                    도구_이름[조각["id"]] = 조각.get("name") or ""

        # 도구 거절은 사람 발화가 아니라 줄에 붙은 표지로 남는다.
        # 표지 값이 하나가 아니다(2026-09-25 실측: 'user-rejected'와 'automode-blocked',
        # 그중 약 3분의 2가 automode-blocked). 자동 모드 분류기가 막은 것은 사람이
        # AI를 되돌린 것이 아니므로 '도구 거절'에 넣지 않고 따로 센다. 처음 보는 값도
        # 사람의 거절로 단정하지 않는다 — 되돌림은 사람이 한 일만 센다.
        # 사람이 거절했어도 선택지 질문 창을 닫은 것은 되돌림이 아니다(되돌림_아닌_거절_도구).
        종류 = 줄.get("toolDenialKind")
        if 종류:
            도구 = _거절된_도구(줄, 도구_이름)
            거절_표지.append((시각, str(종류), 도구))
            if 종류 not in 사람_거절_종류:
                자동차단.append(시각)
            elif 도구 in 되돌림_아닌_거절_도구:
                선택창.append(시각)
            else:
                거절.append(시각)

        글 = 사람_발화인가(줄)
        if 글 is None:
            continue
        if 글 in 중단_표지:
            중단.append(시각)
            continue
        발화.append((시각, 글))

    return {
        "파일": 파일,
        "제목": 제목,
        "작업위치": 작업위치,
        "발화": 발화,
        "중단": 중단,
        "거절": 거절,
        "자동차단": 자동차단,
        "선택창": 선택창,
        "거절_표지": 거절_표지,
    }


def _거절된_도구(줄, 도구_이름):
    """거절 줄이 가리키는 도구 이름. 모르면 빈 글자.

    거절 줄 자체에는 도구 이름이 없고, 본문의 tool_result 조각에 앞선 AI 줄의
    tool_use id(`tool_use_id`)만 있다. 그 id로 앞에서 모아 둔 이름을 찾는다.
    """
    for 조각 in ((줄.get("message") or {}).get("content") or []):
        if isinstance(조각, dict) and 조각.get("type") == "tool_result":
            return 도구_이름.get(조각.get("tool_use_id") or "", "")
    return ""


def 세션이름(세션):
    if 세션["제목"]:
        return 세션["제목"]
    if 세션["발화"]:
        return 폭맞춰_자르기(세션["발화"][0][1], 30)
    return 세션["파일"].stem[:8]


def 방이름(세션):
    위치 = 세션["작업위치"]
    if not 위치:
        return "?"
    return pathlib.Path(위치).name


def _초(시각):
    try:
        return datetime.fromisoformat(str(시각).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _거절에_딸린_중단인가(중단시각, 거절시각들):
    """이 중단이 바로 앞 거절과 한 행동인가(거절_짝_초 안). 시각을 모르면 아니다."""
    t = _초(중단시각)
    if t is None:
        return False
    for 거절시각 in 거절시각들:
        d = _초(거절시각)
        if d is not None and 0 <= t - d <= 거절_짝_초:
            return True
    return False


def _고쳐_다시_보냈나(앞, 뒤):
    """(시각, 글) 두 발화 — 뒤가 앞을 그대로 담아 곧바로 다시 보낸 것인가."""
    a, b = _초(앞[0]), _초(뒤[0])
    if a is None or b is None or not 0 <= b - a <= 재전송_초:
        return False
    앞글 = re.sub(r"\s+", " ", 앞[1]).strip()
    뒤글 = re.sub(r"\s+", " ", 뒤[1]).strip()
    return bool(앞글) and 뒤글.startswith(앞글)


def 방_열쇠(이름):
    """방 이름을 견줄 때 쓰는 열쇠 — 대소문자를 가리지 않는다.

    세션 측정 그릇에 같은 방이 `project`와 `Project`로 따로 적혀 있었다(윈도우 PC는
    폴더 이름의 대소문자를 가리지 않아 어느 쪽으로든 열린다). 적힌 값은 고치지 않고,
    견주고 묶을 때만 이 열쇠로 맞춘다.
    """
    return (이름 or "").strip().casefold()


def 되돌림_찾기(세션, 넓게=False):
    """이 세션에서 되돌림으로 보이는 자리를 모두 돌려준다.

    한 번의 행동이 두 건으로 세어지지 않게 두 가지를 거둔다. ① 도구 거절(또는 선택지
    창 닫기)과 같은 순간의 요청 중단은 거절에 딸린 것이라 따로 세지 않는다. ② 같은
    말을 덧붙여 곧바로 다시 보냈으면 말로 반박은 뒤의 것 하나만 센다.
    """
    찾음 = []
    짝_거절 = list(세션["거절"]) + list(세션.get("선택창") or [])

    for 시각 in 세션["중단"]:
        if _거절에_딸린_중단인가(시각, 짝_거절):
            continue
        찾음.append({"시각": 시각, "갈래": "요청 중단", "신호": "표지",
                     "글": "[요청을 중간에 끊음]", "붙여넣기": False})
    # '거절'에는 사람이 거절한 것만 들어 있다. 자동 모드가 막은 것('자동차단')은
    # 사람이 AI를 되돌린 것이 아니라 여기 넣지 않는다(세션_읽기 참고).
    for 시각 in 세션["거절"]:
        찾음.append({"시각": 시각, "갈래": "도구 거절", "신호": "표지",
                     "글": "[도구 호출을 거절함]", "붙여넣기": False})

    규칙 = list(강한_신호) + (list(약한_신호) if 넓게 else [])
    발화 = 세션["발화"]
    for 차례, (시각, 글) in enumerate(발화):
        if 차례 == 0:
            # 세션의 첫 발화는 아직 AI가 아무것도 안 한 시점이라 되돌림일 수 없다.
            continue
        if 차례 + 1 < len(발화) and _고쳐_다시_보냈나(발화[차례], 발화[차례 + 1]):
            continue            # 뒤에 다시 보낸 것이 있다 — 그쪽 하나만 센다
        맞은신호 = [이름 for 이름, 패턴 in 규칙 if 패턴.search(글)]
        if not 맞은신호:
            continue
        찾음.append({
            "시각": 시각,
            "갈래": "말로 반박",
            "신호": "·".join(맞은신호),
            "글": 글,
            "붙여넣기": len(글) > 붙여넣기_길이 or 글.count("\n") >= 붙여넣기_줄수,
        })

    찾음.sort(key=lambda x: x["시각"])
    return 찾음


def 시각만(시각):
    """기록의 시각은 세계 표준시라 우리 시각으로 옮겨 보여준다."""
    try:
        t = datetime.fromisoformat(시각.replace("Z", "+00:00"))
        return t.astimezone().strftime("%H:%M")
    except Exception:
        return "?"


def 우리날짜(시각):
    try:
        t = datetime.fromisoformat(시각.replace("Z", "+00:00"))
        return t.astimezone().strftime("%m-%d")
    except Exception:
        return "?"


def 우리날짜전체(시각):
    """--날 옵션에 그대로 넣을 수 있는 형태로 돌려준다."""
    try:
        t = datetime.fromisoformat(시각.replace("Z", "+00:00"))
        return t.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return "?"


def 많은순(모음, 열쇠, 몇개):
    """어느 값에 몇 건이 몰렸는지 세어 많은 순으로 돌려준다."""
    셈 = {}
    for 건 in 모음:
        셈[건[열쇠]] = 셈.get(건[열쇠], 0) + 1
    차례 = sorted(셈.items(), key=lambda x: (-x[1], x[0]))
    return 차례[:몇개], len(셈)


def 막대(수, 최대, 길이=18):
    if 최대 <= 0:
        return ""
    return "█" * max(1, round(수 / 최대 * 길이))


def 출력_요약(모음, 인자):
    """낱낱을 늘어놓기 전에, 어디에 몰려 있는지부터 보여준다.

    30일치를 그냥 늘어놓으면 190줄이 넘어 화면에 담기지 않는다. 먼저 볼 것은
    갈래·날짜·방이고, 그 셋은 그대로 --날·--방으로 파고드는 열쇠이기도 하다.
    """
    갈래, _ = 많은순(모음, "갈래", 9)
    print("  갈래      " + " · ".join(f"{이름} {수}건" for 이름, 수 in 갈래))
    print()

    # --날로 이미 하루만 골랐다면 날짜별 분포는 한 줄뿐이라 보여줄 것이 없다.
    날짜묶음 = None if 인자.날 else {}
    for 건 in ([] if 날짜묶음 is None else 모음):
        날짜묶음.setdefault(우리날짜전체(건["시각"]), 0)
        날짜묶음[우리날짜전체(건["시각"])] += 1
    많은날 = sorted(날짜묶음.items(), key=lambda x: (-x[1], x[0]))[:5] if 날짜묶음 else []
    if 많은날:
        최대 = 많은날[0][1]
        print(f"  많이 나온 날 (전체 {len(날짜묶음)}일 중 상위 {len(많은날)}일)")
        for 날, 수 in 많은날:
            print(f"    {날}  {칸채우기(막대(수, 최대), 20)}{수}건")
        if len(날짜묶음) > 1:
            print(f"    → 하루만 보려면   --날 {많은날[0][0]}")
        print()

    # --방으로 이미 한 방만 골랐다면 방별 분포도 마찬가지다.
    많은방, 방수 = ([], 0) if 인자.방 else 많은순(모음, "방", 5)
    if 많은방:
        print(f"  많이 나온 방 (전체 {방수}개 중 상위 {len(많은방)}개)")
        for 이름, 수 in 많은방:
            print(f"    {칸채우기(폭맞춰_자르기(이름, 24), 26)}{수}건")
        if 방수 > 1:
            print(f"    → 한 방만 보려면   --방 {많은방[0][0]}")
        print()

    몰린세션, 세션수 = 많은순(모음, "세션", 5)
    if 몰린세션:
        print(f"  몰린 세션 (전체 {세션수}개 중 상위 {len(몰린세션)}개)")
        for 이름, 수 in 몰린세션:
            print(f"    {칸채우기(폭맞춰_자르기(이름, 40), 42)}{수}건")
        print()

    신호셈 = {}
    for 건 in 모음:
        if 건["신호"] == "표지":
            continue
        for 하나 in 건["신호"].split("·"):
            신호셈[하나] = 신호셈.get(하나, 0) + 1
    if 신호셈:
        많은신호 = sorted(신호셈.items(), key=lambda x: (-x[1], x[0]))[:6]
        print("  자주 걸린 신호")
        print("    " + " · ".join(f"{이름} {수}건" for 이름, 수 in 많은신호))
        print()

    붙임 = sum(1 for 건 in 모음 if 건["붙여넣기"])
    if 붙임:
        print(f"  ※ {붙임}건은 붙여넣은 글이 섞여 있어 남의 말이 걸렸을 수 있습니다.")
    # 숫자는 README "지금까지 잰 정확도"의 최신 실측(2026-09-09, 64건 중 12건)과 맞춘다.
    # 규칙을 고쳐 다시 재면 두 곳을 함께 고친다.
    print("  ※ 말로 반박은 낱말 규칙으로 판정하므로 다섯 중 하나쯤은 잘못 잡힙니다(실측 19%).")
    print()
    print("  → 낱낱을 보려면   --자세히")
    print()


def 출력_낱낱(모음, 인자):
    폭_날짜, 폭_세션, 폭_시각, 폭_신호 = 7, 28, 7, 16
    머리 = (칸채우기("날짜", 폭_날짜) + 칸채우기("세션", 폭_세션)
            + 칸채우기("시각", 폭_시각) + 칸채우기("신호", 폭_신호) + "되돌린 말")
    print("  " + 머리)
    print("  " + "─" * 100)

    for 건 in 모음:
        표시 = 건["글"]
        if not 인자.원문:
            표시 = 폭맞춰_자르기(표시, 46)
        else:
            표시 = re.sub(r"\s+", " ", 표시).strip()
        if 건["붙여넣기"]:
            표시 = "(붙여넣기 섞임) " + 표시
        # 칸을 자를 때는 글자 수가 아니라 화면폭으로 잰다 — 한글은 두 칸이다.
        print("  "
              + 칸채우기(우리날짜(건["시각"]), 폭_날짜)
              + 칸채우기(폭맞춰_자르기(건["세션"], 폭_세션 - 1), 폭_세션)
              + 칸채우기(시각만(건["시각"]), 폭_시각)
              + 칸채우기(폭맞춰_자르기(건["신호"], 폭_신호 - 1), 폭_신호)
              + 표시)
    print()


def _범위_안(시각, 자를시각, 날):
    """그 시각이 --최근·--날로 고른 범위 안인가. 읽을 수 없는 시각은 뺀다."""
    try:
        t = datetime.fromisoformat(시각.replace("Z", "+00:00"))
    except Exception:
        return False
    if 자를시각 is not None and t < 자를시각:
        return False
    if 날 and t.astimezone().strftime("%Y-%m-%d") != 날:
        return False
    return True


def 명령_되돌림(인자):
    if not 기록_뿌리.exists():
        print(f"세션 기록 폴더가 없습니다: {기록_뿌리}")
        return 1

    자를시각 = None
    if 인자.날:
        자를시각 = None          # 날짜를 짚었으면 기간 자르기는 쓰지 않는다
    elif not 인자.전부:
        자를시각 = datetime.now(timezone.utc) - timedelta(days=인자.최근)

    모음 = []
    읽은세션 = 0
    자동차단_수 = 0
    for 파일 in 대화_기록_파일들():
        세션 = 세션_읽기(파일)
        if not 세션["발화"] and not 세션["중단"] and not 세션["거절"] and not 세션["자동차단"]:
            continue
        if 인자.방 and 방_열쇠(방이름(세션)) != 방_열쇠(인자.방):
            continue
        읽은세션 += 1
        자동차단_수 += sum(1 for 시각 in 세션["자동차단"] if _범위_안(시각, 자를시각, 인자.날))
        for 건 in 되돌림_찾기(세션, 넓게=인자.넓게):
            if not _범위_안(건["시각"], 자를시각, 인자.날):
                continue
            건["세션"] = 세션이름(세션)
            건["방"] = 방_열쇠(방이름(세션))     # 대소문자만 다른 방을 한 줄로 묶는다
            건["파일"] = 파일.name
            모음.append(건)

    모음.sort(key=lambda x: x["시각"])

    기간말 = 인자.날 if 인자.날 else ("전체 기간" if 인자.전부 else f"최근 {인자.최근}일")
    범위말 = f" · 방 {인자.방}" if 인자.방 else ""
    넓게말 = " · 약한 신호 포함" if 인자.넓게 else ""
    print(f"\n되돌림 {len(모음)}건 — {기간말}{범위말}{넓게말}\n")
    if 자동차단_수:
        # 되돌림 건수에 넣지 않는다 — 사람이 아니라 자동 모드 분류기가 막은 것이다.
        # 그래도 숨기지는 않는다: 분류기가 자주 막는다는 것 자체가 볼 거리다.
        print(f"  (자동 모드가 막은 도구 호출 {자동차단_수}건은 되돌림에 넣지 않았습니다)\n")

    if not 모음:
        print("  잡힌 것이 없습니다.\n")
        return 0

    # --원문은 낱낱을 자르지 말라는 뜻이므로 낱낱을 보겠다는 말과 같다.
    자세히 = 인자.자세히 or 인자.원문
    if 자세히:
        출력_낱낱(모음, 인자)
    else:
        출력_요약(모음, 인자)
    return 0


def 주된흐름(주장=None):
    받개 = argparse.ArgumentParser(prog="naite", add_help=True,
                                   description="세션 기록에서 어긋난 자리를 찾는다")
    하위 = 받개.add_subparsers(dest="명령")

    되돌림 = 하위.add_parser("되돌림", help="사용자가 AI를 되돌린 자리를 찾는다")
    되돌림.add_argument("--최근", type=int, default=7, help="며칠치를 볼지 (기본 7)")
    되돌림.add_argument("--전부", action="store_true", help="기간을 제한하지 않는다")
    되돌림.add_argument("--자세히", action="store_true", help="요약 대신 낱낱을 표로 늘어놓는다")
    되돌림.add_argument("--넓게", action="store_true", help="약한 신호까지 포함(오탐이 는다)")
    되돌림.add_argument("--원문", action="store_true", help="낱낱을 자르지 않고 보여준다(--자세히를 겸한다)")
    되돌림.add_argument("--방", default=None, help="이 폴더에서 연 세션만 본다")
    되돌림.add_argument("--날", default=None, help="이 날짜만 본다 (보기: 2026-09-04)")

    인자 = 받개.parse_args(주장)
    if 인자.명령 == "되돌림":
        return 명령_되돌림(인자)
    받개.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(주된흐름())
