#!/usr/bin/env python3
"""나무 주간 점검 — 지난주보다 나아졌는지 답할 수 있게 숫자를 재고 남긴다.

왜 만들었나
-----------
2026-09-08에 교훈 264건을 부류로 나눠 재고 상시 규칙을 개편했다. 그런데 그
개선이 일어난 이유는 사용자가 물어봤기 때문이었다. 물어보지 않았으면 아무것도
재지 않았다. 그래서 그 질문을 사람 대신 기계가 던지게 한다.

같은 날 확인한 급한 사실이 하나 더 있다. 세션 기록은 약 28일치만 남는다. 그날
몇 시간 사이에 파일 98개가 94개로 줄었고, 가장 오래된 날이 08-09에서 08-11로
밀렸다. 어긋남 건수는 기록 습관과 무관한 유일한 신호인데 그 원재료가 4주면
사라지므로, **잰 숫자를 그때그때 남겨 두지 않으면 나아졌는지를 영영 답할 수 없다.**

무엇을 재나
-----------
  A 세션당 어긋남 건수      나이테. 기록 습관에 영향받지 않는다
  B 세션당 구조 표지 건수   요청 중단·도구 거절만. 판정이 아니라 표지라 틀릴 수 없다
  C 최근 28일 교훈과 실패   나무 교훈. 적는 습관에 영향받으므로 참고용이다
  D 상시 규칙 개수와 글자 수 매 입력에 붙는 글의 크기

A와 B가 주된 지표다. C는 혼자 읽으면 오해한다 — 실패 기록이 줄어든 것과 실패를
안 적게 된 것을 구별하지 못하기 때문이다.

쓰는 법
-------
    python3 weekly_check.py

이 도구는 재서 보여주기만 한다. **기록은 사람이나 AI가 namu_record로 남긴다.**
기억 저장소에 직접 쓰면 동기화 장치를 건너뛰게 되므로 그렇게 하지 않는다.
"""

import json
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

try:                                    # 나무의 기준 시간대(기본 Asia/Seoul)를 따른다
    from zoneinfo import ZoneInfo
    기준_시간대 = ZoneInfo(os.environ.get("NAMU_TZ", "Asia/Seoul"))
except Exception:                       # tz 자료가 없는 기계에서는 현지시각으로 물러선다
    기준_시간대 = None

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import naite  # noqa: E402

기억_뿌리 = pathlib.Path.home() / ".namu" / "memory"
부류_파일 = pathlib.Path(__file__).parent / "lesson_classes.json"
점검_꼬리표 = "나무점검"
최근_일수 = 28


def 어긋남_재기():
    """나이테로 어긋남을 센다. (건수, 세션수, 구조표지수)를 돌려준다."""
    전체, 세션수, 표지 = 0, 0, 0
    for 파일 in sorted(naite.기록_뿌리.rglob("*.jsonl")):
        세션 = naite.세션_읽기(파일)
        건들 = naite.되돌림_찾기(세션)
        if 건들:
            세션수 += 1
        for 건 in 건들:
            전체 += 1
            if 건["갈래"] in ("요청 중단", "도구 거절"):
                표지 += 1
    return 전체, 세션수, 표지


def 교훈_읽기():
    import yaml
    경로 = 기억_뿌리 / "learnings.yaml"
    if not 경로.exists():
        return []
    with 경로.open(encoding="utf-8") as f:
        return [d for d in yaml.safe_load_all(f) if d]


def 때(d):
    try:
        return datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00"))
    except Exception:
        return None


def 교훈_재기(docs):
    """최근 28일에 쌓인 교훈과 그중 실패 건수.

    점검 기록 자체는 빼고 센다 — 재는 행위가 재는 대상에 섞이면
    점검할 때마다 교훈이 한 건씩 늘어난 것처럼 보인다.
    """
    기준 = datetime.now(timezone.utc) - timedelta(days=최근_일수)
    최근 = [d for d in docs
            if (t := 때(d)) and t >= 기준
            and 점검_꼬리표 not in (d.get("tags") or [])]
    실패 = [d for d in 최근 if d.get("outcome") == "failure"]
    return len(최근), len(실패), 실패


def 상시규칙_재기():
    import yaml
    경로 = 기억_뿌리 / "profile.yaml"
    if not 경로.exists():
        return 0, 0
    with 경로.open(encoding="utf-8") as f:
        docs = [d for d in yaml.safe_load_all(f) if d]
    지난것 = {d.get("supersedes") for d in docs if d.get("supersedes")}
    산것 = [d for d in docs
            if "상시" in (d.get("tags") or []) and d.get("id") not in 지난것]
    글자 = sum(len("- **%s** — %s" % (d.get("subject"),
                                     " ".join(str(d.get("body") or "").split())))
               for d in 산것)
    return len(산것), 글자


def 지난_점검(docs):
    """가장 최근의 나무점검 기록을 찾는다. 없으면 None."""
    점검들 = [d for d in docs if 점검_꼬리표 in (d.get("tags") or [])]
    점검들.sort(key=lambda d: str(d.get("timestamp", "")))
    return 점검들[-1] if 점검들 else None


def 부류_읽기():
    try:
        return json.loads(부류_파일.read_text(encoding="utf-8"))
    except Exception:
        return None


def 부류별_실패(docs, 배정, 부터, 까지=None):
    """기간 안의 실패를 부류별로 센다. 부류가 안 붙은 것은 따로 모은다."""
    셈, 모르는것 = {}, []
    for d in docs:
        t = 때(d)
        if not t or t < 부터 or (까지 and t >= 까지):
            continue
        if d.get("outcome") != "failure":
            continue
        이름 = 배정.get(d.get("id"))
        if 이름 is None:
            모르는것.append(d)
        else:
            셈[이름] = 셈.get(이름, 0) + 1
    return 셈, 모르는것


def 조치_후보(이번, 지난, 부류자료):
    """숫자에서 이번에 볼 것을 뽑아 이름 짓는다. (급함, 한 줄) 목록."""
    기계 = 부류자료.get("기계로_잡을_수_있는_부류", {})
    못잡음 = 부류자료.get("기계로_못_잡는_부류", {})
    후보 = []
    for 이름, n in sorted(이번.items(), key=lambda x: -x[1]):
        옛 = 지난.get(이름, 0)
        늘어남 = n - 옛
        if n == 0:
            continue
        if 이름 in 기계:
            후보.append((늘어남 * 10 + n,
                         "**%s** 실패 %d건(지난 점검 대비 %+d) — 기계로 잡을 수 있다: %s. "
                         "검사가 이미 있으면 왜 못 막았는지 보고, 없으면 만든다."
                         % (이름, n, 늘어남, 기계[이름])))
        elif 이름 in 못잡음 and 못잡음[이름] not in ("실수 기록이 아님",):
            후보.append((늘어남 * 10 + n - 5,
                         "**%s** 실패 %d건(지난 점검 대비 %+d) — 기계로 못 잡는다(%s). "
                         "상시 규칙이 이 부류를 겨냥하는지, 겨냥하는데도 늘었는지 본다."
                         % (이름, n, 늘어남, 못잡음[이름])))
    후보.sort(key=lambda x: -x[0])
    return [줄 for _, 줄 in 후보]


def 지난_조치(기록):
    """지난 점검이 조치를 남겼는지 본다. 안 남겼으면 그 사실을 돌려준다."""
    if not 기록:
        return None
    본문 = str(기록.get("body") or "")
    for 줄 in 본문.splitlines():
        벗김 = 줄.strip()
        if 벗김.startswith("이번 조치:"):
            내용 = 벗김.split(":", 1)[1].strip()
            return 내용 or "(비어 있음)"
    return "(적히지 않음)"


def 화살(지금, 지난, 작을수록좋음=True):
    if 지난 is None:
        return "(첫 측정)"
    차 = 지금 - 지난
    if abs(차) < 0.005:
        return "지난번과 같음"
    좋아짐 = (차 < 0) if 작을수록좋음 else (차 > 0)
    표 = "▼" if 차 < 0 else "▲"
    return "%s %+.2f (%s)" % (표, 차, "좋아짐" if 좋아짐 else "나빠짐")


def 지난값(기록, 열쇠):
    """지난 점검 기록의 본문에서 '열쇠: 숫자' 한 줄을 읽는다."""
    if not 기록:
        return None
    for 줄 in str(기록.get("body") or "").splitlines():
        if 줄.strip().startswith(열쇠 + ":"):
            try:
                return float(줄.split(":", 1)[1].strip().split()[0])
            except Exception:
                return None
    return None


def 주된흐름():
    docs = 교훈_읽기()
    지난 = 지난_점검(docs)

    건수, 세션수, 표지 = 어긋남_재기()
    A = 건수 / 세션수 if 세션수 else 0.0
    B = 표지 / 세션수 if 세션수 else 0.0
    교훈수, 실패수, 실패들 = 교훈_재기(docs)
    규칙수, 규칙글자 = 상시규칙_재기()

    오래된 = min((p.stat().st_mtime for p in naite.기록_뿌리.rglob("*.jsonl")),
                default=None)
    # 기준 시간대를 명시한다. 시간대 없이 호스트 시계를 읽으면 기계마다 날짜가
    # 갈려 점검 기록끼리 견줄 수 없게 된다(test_record_time.py가 이것을 막는다).
    지금 = datetime.now(기준_시간대)
    보존 = ("%d일" % (지금 - datetime.fromtimestamp(오래된, 기준_시간대)).days
            if 오래된 else "모름")

    print()
    print("  나무 주간 점검 — %s" % 지금.strftime("%Y-%m-%d"))
    if 지난:
        print("  지난 점검: %s" % str(지난.get("timestamp"))[:10])
    else:
        print("  지난 점검: 없음 (이번이 첫 기준선입니다)")
    print("  " + "-" * 62)
    print()
    print("  ■ 주된 지표 — 기록 습관에 영향받지 않는다")
    print("    세션당 어긋남: %.2f 건   %s" % (A, 화살(A, 지난값(지난, "세션당 어긋남"))))
    print("    세션당 구조 표지: %.2f 건   %s" % (B, 화살(B, 지난값(지난, "세션당 구조 표지"))))
    print("    (어긋남 %d건 / 세션 %d개, 세션 기록 보존 %s)" % (건수, 세션수, 보존))
    print()
    print("  ■ 참고 지표 — 적는 습관에 영향받으므로 혼자 읽으면 오해한다")
    print("    최근 %d일 교훈: %d건 (그중 실패 %d건)" % (최근_일수, 교훈수, 실패수))
    print()
    print("  ■ 매 입력에 붙는 글")
    print("    상시 규칙: %d개 %d자 (상한 2,000자)" % (규칙수, 규칙글자))
    print()

    # ── 지난 점검이 조치를 남겼는지 먼저 따진다 ──
    앞선조치 = 지난_조치(지난)
    if 지난 and 앞선조치 in ("(적히지 않음)", "(비어 있음)"):
        print("  ■ ⚠ 지난 점검이 조치를 남기지 않았습니다")
        print("    재고 넘어가기만 하면 이 장치는 보고서일 뿐 개선 장치가 아닙니다.")
        print("    이번에는 반드시 '이번 조치:' 줄을 채우십시오.")
        print()
    elif 앞선조치:
        print("  ■ 지난 점검의 조치")
        print("    %s" % 앞선조치[:200])
        print("    → 그 조치가 겨냥한 부류의 숫자가 아래에서 줄었는지 확인할 것")
        print()

    # ── 부류별로 무엇이 늘었는지 재고 조치 후보를 뽑는다 ──
    부류자료 = 부류_읽기()
    if 부류자료:
        배정 = 부류자료.get("배정", {})
        기준 = datetime.now(timezone.utc) - timedelta(days=최근_일수)
        이번, 모르는것 = 부류별_실패(docs, 배정, 기준)
        지난기준 = 때(지난) if 지난 else None
        옛, _ = (부류별_실패(docs, 배정, 지난기준 - timedelta(days=최근_일수), 지난기준)
                 if 지난기준 else ({}, []))

        if 모르는것:
            print("  ■ 부류가 안 붙은 실패 %d건 — 먼저 부류를 붙이십시오" % len(모르는것))
            for d in 모르는것:
                print("    %s  %s" % (str(d.get("timestamp"))[:10],
                                      " ".join(str(d.get("summary", "")).split())[:60]))
            print("    → 붙인 뒤 %s 의 '배정'에 넣으면 다음 점검이 셉니다" % 부류_파일.name)
            print()

        후보 = 조치_후보(이번, 옛, 부류자료)
        if 후보:
            print("  ■ 이번에 볼 것 — 위 숫자에서 뽑았다 (급한 차례)")
            for i, 줄 in enumerate(후보[:4], 1):
                print("    %d. %s" % (i, 줄))
            print()
        else:
            print("  ■ 이번에 볼 것: 없음 — 최근 %d일에 부류가 붙은 실패가 없습니다" % 최근_일수)
            print()
    else:
        print("  ■ 부류 자료(%s)를 못 읽어 조치 후보를 뽑지 못했습니다" % 부류_파일.name)
        print()

    print("  ■ 나무에 남길 때 본문에 아래 다섯 줄을 그대로 넣는다")
    print("    (다음 점검이 이 줄을 읽어 대조하고, 조치를 안 남기면 잡아낸다)")
    print()
    print("    세션당 어긋남: %.2f" % A)
    print("    세션당 구조 표지: %.2f" % B)
    print("    최근 교훈: %d" % 교훈수)
    print("    상시 규칙 글자: %d" % 규칙글자)
    print("    이번 조치: <무엇을 바꿨는지 한 줄. 안 바꿨으면 '없음 — 이유'>")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(주된흐름())
