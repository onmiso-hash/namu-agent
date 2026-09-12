#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1"]
# ///
"""SessionEnd 훅 — 세션이 끝날 때 나이테를 그 세션 하나에만 돌려 값을 기억에 남긴다.

왜 만들었나
-----------
주간 점검의 주된 지표인 "세션당 어긋남 건수"는 대화 기록(`~/.claude/projects`)에서
계산하는데, 그 대화 기록에는 두 가지 제약이 있다.

1. 동기화되지 않는다 — 그 기계에서 연 세션만 있고, 웹에서 연 세션은 아예 잡히지
   않는다.
2. 약 28일이 지나면 사라진다 — 2026-09-08에 몇 시간 사이에 파일 98개가 94개로 줄고
   가장 오래된 날이 08-09에서 08-11로 밀리는 것을 실제로 관측했다.

그래서 세션이 끝날 때마다 그 자리에서 재서 기억에 남긴다. 기억은 동기화되므로 어느
기계에서 연 세션이든 한자리에 모이고, 대화 기록이 사라진 뒤에도 값이 남는다.
2026-09-11에 검증했다 — 세션마다 따로 재서 합산한 값과 전체를 한 번에 잰 값이 같은
시점에 어긋남 158건·세션 51개·세션당 3.10으로 똑같이 나왔다.

왜 "훅은 기록하지 않는다"는 원칙의 예외인가
-------------------------------------------
나무의 다른 훅 여섯은 알리고 막을 뿐 아무것도 적지 않는다. 그 원칙의 근거는
**교훈**에 관한 것이다: 자동 기록은 "작업 완료" 시점이 기계적으로 모호해 쓰레기가
쌓이고, 의미 있는 `reason`을 기계가 만들 수 없다.

이 훅은 그 근거에 걸리지 않는다. 적는 것이 판단이 아니라 **기계가 잰 숫자와 사람이
실제로 한 말의 원문**이고, 시점도 모호하지 않다(세션이 끝나는 순간 하나뿐이다).
그래서 들어가는 그릇도 교훈이 아니라 따로 만든 세션 측정 그릇이며, 그 그릇은
`namu_record`로는 아예 쓸 수 없다(`config.BOWLS`의 `web_exposed=False`).

**이 훅은 교훈을 적지 않는다.** 교훈은 지금까지대로 AI가 판단해 `namu_record`로
남긴다. 이 경계가 무너지면 원칙이 무의미해진다.

동작
----
세션이 끝날 때 그 세션의 대화 기록 한 장만 읽어 어긋남을 세고, 사람 발화 원문과
함께 `~/.namu/memory/sessions.yaml`에 한 건 남긴 뒤 원격에 올린다.

그 일을 훅 프로세스에서 직접 하지 않고 떼어낸 프로세스에 맡긴다 — 까닭은
`일꾼_띄우기`에 적었다.

어떤 에러가 나도 exit 0 — 훅이 세션 종료를 인질로 잡으면 안 된다.
"""
import json
import os
import pathlib
import subprocess
import sys

_훅_폴더 = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_훅_폴더.parent))
sys.path.insert(0, str(_훅_폴더.parent / "naite"))


def 재기(기록_파일, 세션_id, 끝난_이유):
    """대화 기록 한 장을 읽어 남길 값을 만든다. 남길 것이 없으면 None.

    재는 규칙 자체는 `sessions.measure`에 한 벌만 있다 — 웹 대화창의
    `namu_record_session`도 같은 함수를 쓴다. 여기서 하는 일은 대화 기록 파일에서
    그 함수가 받을 모양으로 발화를 뽑아 주는 것뿐이다. 규칙이 두 벌이 되면 같은
    대화도 어디서 넣었느냐에 따라 숫자가 달라진다.
    """
    import naite
    import sessions

    세션 = naite.세션_읽기(기록_파일)
    return sessions.measure(
        session_id=세션_id,
        utterances=[{"at": 시각, "text": 글} for 시각, 글 in 세션["발화"]],
        interrupts=list(세션["중단"]),
        denials=list(세션["거절"]),
        project=naite.방이름(세션),
        title=naite.세션이름(세션),
        end_reason=끝난_이유,
    )


def 입력_읽기():
    """들어온 값을 읽고 일할 거리가 되는지만 본다. 아니면 None."""
    try:
        들어온값 = json.load(sys.stdin)
    except Exception:
        return None

    기록_경로 = (들어온값.get("transcript_path") or "").strip()
    세션_id = (들어온값.get("session_id") or "").strip()
    if not 기록_경로 or not 세션_id:
        return None
    if not pathlib.Path(기록_경로).exists():
        return None
    return 들어온값


def _분리_옵션() -> dict:
    """부모가 끝나도 자식이 따라 죽지 않게 하는 옵션.

    POSIX에서는 자식에게 세션을 새로 열어 주면 프로세스 그룹이 갈라져서, 부모가
    받는 종료 신호를 함께 받지 않는다. 윈도우에는 그런 개념이 없으므로 같은 구실을
    하는 생성 표지 두 개를 쓴다.
    """
    if hasattr(os, "setsid"):
        return {"start_new_session": True}

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    return {"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP}


def 일꾼_띄우기(들어온값) -> None:
    """재고 남기고 올리는 일을 떼어낸 프로세스에 맡기고 곧바로 돌아온다.

    세션 종료 훅에 주어지는 시간이 1.5초다. 공식 문서는 "SessionEnd 훅들이 1.5초
    예산을 나눠 쓰고, **설정**에 더 긴 timeout을 적으면 예산을 거기 맞춰 올린다"고
    적고 있는데, 그 '설정'이 플러그인이 가진 hooks.json까지 가리키는지는 밝히지
    않았다. 이 훅은 hooks.json에 timeout 30을 적어 두었는데도 실제로 끊겼다.

    2026-09-12에 관측한 것은 이렇다. 파일 추가와 커밋까지는 0.1초 안에 끝나
    커밋이 정상으로 남았고, 2.3초가 걸리는 원격 올리기는 수행 기록조차 남기지
    못한 채 사라졌다. 1.5초 예산과 각 단계의 소요가 정확히 들어맞는다.

    올리기만 떼어내지 않고 재는 일까지 전부 떼어내는 까닭은, 대화 기록이 길어지면
    재는 일 자체가 1.5초를 넘길 수 있고 그때는 측정값조차 남지 않기 때문이다.
    """
    자식 = subprocess.Popen(
        [sys.executable, str(pathlib.Path(__file__).resolve()), "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_분리_옵션(),
    )
    # 자식을 기다리지 않는다. 들어온 값은 수백 바이트라 파이프 버퍼에 그대로
    # 들어가므로, 이 프로세스가 곧바로 끝나도 자식이 읽는 데 지장이 없다.
    자식.stdin.write(json.dumps(들어온값, ensure_ascii=False).encode("utf-8"))
    자식.stdin.close()


def 일하기(들어온값) -> None:
    """떼어낸 프로세스에서 도는 본체 — 재고, 남기고, 올린다."""
    기록_파일 = pathlib.Path(들어온값["transcript_path"].strip())
    세션_id = 들어온값["session_id"].strip()

    import memory_sync
    import sessions

    잰값 = 재기(기록_파일, 세션_id, (들어온값.get("reason") or "").strip() or None)
    if 잰값 is None:
        return
    if sessions.already_recorded(세션_id, len(잰값["utterances"])):
        return

    sessions.record_session(**잰값)

    # 올리기가 실패해도 값은 이미 파일에 있다 — 다음 기록의 올리기가 함께 싣고 간다.
    # 그래서 여기서 실패를 되살리려 애쓰지 않는다.
    try:
        memory_sync.sync_push("session: 어긋남 %d건 (%s)" % (
            잰값["misalignments"], 잰값["project"] or "?",
        ))
    except Exception:
        pass


def main():
    들어온값 = 입력_읽기()
    if 들어온값 is None:
        return
    if "--worker" in sys.argv[1:]:
        일하기(들어온값)
    else:
        일꾼_띄우기(들어온값)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
