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

어떤 에러가 나도 exit 0 — 훅이 세션 종료를 인질로 잡으면 안 된다.
"""
import json
import pathlib
import sys

_훅_폴더 = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_훅_폴더.parent))
sys.path.insert(0, str(_훅_폴더.parent / "naite"))


def 재기(기록_파일, 세션_id, 끝난_이유):
    """대화 기록 한 장을 읽어 남길 값을 만든다. 남길 것이 없으면 None."""
    import naite

    세션 = naite.세션_읽기(기록_파일)
    발화 = 세션["발화"]
    if not 발화:
        # 사람이 한 마디도 안 한 세션이다. 세션 수에 넣으면 분모만 늘어 평균이
        # 실제보다 낮게 보인다.
        return None

    건들 = naite.되돌림_찾기(세션)
    구조_표지 = sum(1 for 건 in 건들 if 건["갈래"] in ("요청 중단", "도구 거절"))

    return {
        "session_id": 세션_id,
        "misalignments": len(건들),
        "structural_marks": 구조_표지,
        "utterances": [{"at": 시각, "text": 글} for 시각, 글 in 발화],
        "interrupts": list(세션["중단"]),
        "denials": list(세션["거절"]),
        "project": naite.방이름(세션),
        "title": naite.세션이름(세션),
        "started_at": 발화[0][0],
        "ended_at": 발화[-1][0],
        "end_reason": 끝난_이유,
    }


def 이미_남겼나(세션_id, 이번_발화수):
    """같은 세션의 값이 이미 있고 더 자랄 것이 없으면 참.

    `--resume`으로 이어서 열면 같은 session_id로 한 번 더 끝난다. 그때는 발화가
    늘어 있으므로 새로 남기고, 합산하는 쪽이 마지막 항목만 세어 겹치지 않게 한다.
    반대로 발화가 안 늘었으면 같은 값을 또 쌓을 뿐이라 남기지 않는다.
    """
    import sessions

    앞선 = sessions.latest_by_session().get(세션_id)
    if 앞선 is None:
        return False
    try:
        return int(앞선.get("utterance_count") or 0) >= 이번_발화수
    except (TypeError, ValueError):
        return False


def main():
    try:
        들어온값 = json.load(sys.stdin)
    except Exception:
        return

    기록_경로 = (들어온값.get("transcript_path") or "").strip()
    세션_id = (들어온값.get("session_id") or "").strip()
    if not 기록_경로 or not 세션_id:
        return

    기록_파일 = pathlib.Path(기록_경로)
    if not 기록_파일.exists():
        return

    잰값 = 재기(기록_파일, 세션_id, (들어온값.get("reason") or "").strip() or None)
    if 잰값 is None:
        return
    if 이미_남겼나(세션_id, len(잰값["utterances"])):
        return

    import memory_sync
    import sessions

    sessions.record_session(**잰값)

    # 올리기가 실패해도 값은 이미 파일에 있다 — 다음 기록의 올리기가 함께 싣고 간다.
    # 그래서 여기서 실패를 되살리려 애쓰지 않는다.
    try:
        memory_sync.sync_push("session: 어긋남 %d건 (%s)" % (
            잰값["misalignments"], 잰값["project"] or "?",
        ))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
