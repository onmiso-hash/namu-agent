#!/usr/bin/env python3
"""나이테가 진짜 사고 지점을 짚는지 확인한다.

나무에 교훈으로 남은 사고 네 건을 골라, 그 사고를 촉발한 사용자 발화가
`되돌림`에 실제로 잡히는지 본다. 규칙을 고친 뒤 이것을 돌려서, 오탐을
줄이려다 사고를 놓치게 되지는 않았는지 확인한다.

    python3 check_incidents.py
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import naite  # noqa: E402

# (사고 이름, 날짜, 그 사고를 촉발한 발화에 반드시 들어 있는 글귀, 나무 교훈 번호)
사고들 = [
    ("건네받은 수정을 확인 없이 반영·배포", "2026-08-18",
     "이게 수정이 안되었어", "01M08ZWE8JG59114WHDHF4XXBG"),
    ("guest1이 admin으로 갤러리에 들어간 신분 유출", "2026-08-18",
     "썅~~ 이게 뭐야", "01M09VDP3TYZJEPH2Z9ZGM946F"),
    ("내가 잰 숫자를 내가 뒤집어 말함", "2026-08-22",
     "첨부파일은 미니PC로 저장되지 않고", "01M0JPTS1EERX4F9GX40V2MW1C"),
    ("히트맵은 깃 배포가 자동으로 남기는데 손으로 남기려 함", "2026-09-03",
     "github에 직접 배포한게 맞아", "01M1KEW0BNC6WCSRSTDXPM5VHS"),
]


def 그날_잡힌것(날짜):
    잡힌것 = []
    for 파일 in sorted(naite.기록_뿌리.rglob("*.jsonl")):
        세션 = naite.세션_읽기(파일)
        for 건 in naite.되돌림_찾기(세션):
            from datetime import datetime
            try:
                t = datetime.fromisoformat(건["시각"].replace("Z", "+00:00"))
            except Exception:
                continue
            if t.astimezone().strftime("%Y-%m-%d") == 날짜:
                잡힌것.append(건)
    return 잡힌것


def 주된흐름():
    통과 = 0
    print()
    for 이름, 날짜, 글귀, 교훈번호 in 사고들:
        잡힌것 = 그날_잡힌것(날짜)
        맞은것 = [건 for 건 in 잡힌것 if 글귀 in 건["글"]]
        if 맞은것:
            통과 += 1
            신호 = 맞은것[0]["신호"]
            print(f"  잡음   {이름}")
            print(f"         {날짜} · 신호 [{신호}] · 그날 총 {len(잡힌것)}건")
        else:
            print(f"  놓침   {이름}")
            print(f"         {날짜} · 찾던 글귀 \"{글귀}\" · 그날 총 {len(잡힌것)}건")
        print(f"         나무 교훈 {교훈번호}")
        print()
    print(f"  {len(사고들)}건 중 {통과}건을 짚었습니다.\n")
    return 0 if 통과 == len(사고들) else 1


if __name__ == "__main__":
    sys.exit(주된흐름())
