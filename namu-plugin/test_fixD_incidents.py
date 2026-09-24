"""사고 네 건의 원문이 판정 규칙에 여전히 잡히는지 본다(naite/check_incidents.py와 같은 것).

대화 기록은 약 28일이면 사라진다. 그래서 사고를 촉발한 발화의 원문을
`check_incidents.사고들`에 박아 두고, 판정 함수에 직접 넣어 본다 — 기록이 사라져도
이 시험의 결론은 바뀌지 않는다. **판정 규칙을 고쳐서 이 시험이 빨개지면, 오탐을
줄이려다 사고를 놓치게 된 것이다.** 규칙을 되돌리거나 사고 발화를 다시 잡게 고친다.

아울러 대화 기록을 읽을 때 그날 기록이 아예 없으면 '놓침'이 아니라 '기록 없음'으로
찍는지도 본다 — 둘을 같은 말로 찍던 것이 이 검사가 늘 실패하던 까닭이었다.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "naite"))
import check_incidents as ci  # noqa: E402
import naite  # noqa: E402


@pytest.mark.parametrize("사고", ci.사고들, ids=[사고[1] + " " + 사고[0] for 사고 in ci.사고들])
def test_사고_원문이_말로_반박으로_잡힌다(사고):
    이름, 날짜, _, 글귀, 원문 = 사고
    if 원문 is None:
        pytest.skip(f"{날짜} {이름} — 원문 소실, 검사 불가")
    assert 글귀 in 원문, "찾는 글귀가 원문 안에 있어야 --기록 대조가 같은 발화를 가리킨다"
    assert ci.원문_판정(원문), f"{날짜} 사고 발화를 판정 규칙이 놓쳤다: {원문[:40]}…"


def test_사고_발화가_첫_발화면_판정에서_빠진다():
    """앞에 첫 발화를 까는 이유를 못박는다 — 나이테는 세션의 첫 발화를 건너뛴다."""
    원문 = ci.사고들[1][4]
    세션 = {"발화": [("2026-01-01T00:00:00Z", 원문)], "중단": [], "거절": []}
    assert naite.되돌림_찾기(세션) == []
    assert ci.원문_판정(원문)


def test_앞에_까는_첫_발화는_신호에_걸리지_않는다():
    """깔아 둔 첫 발화가 신호를 가지면 판정이 그 발화 때문에 통과한 것처럼 보일 수 있다."""
    assert not any(패턴.search(ci.앞선_발화) for _, 패턴 in naite.강한_신호)


def test_네_건이_모두_원문을_갖는다():
    """2026-09-25 기준 네 건 모두 원문이 있다. 하나라도 None이 되면 검사 범위가 줄어든 것이다."""
    assert len(ci.사고들) == 4
    assert all(사고[4] for 사고 in ci.사고들)


def test_주된흐름은_네_건을_모두_짚으면_0을_돌려준다(capsys):
    assert ci.주된흐름([]) == 0
    assert "4건 중 4건을 짚었습니다" in capsys.readouterr().out


def test_원문_소실은_놓침으로_세지_않는다(monkeypatch, capsys):
    사고들 = list(ci.사고들) + [("원문을 잃은 사고", "2026-08-01", "X", "글귀", None)]
    monkeypatch.setattr(ci, "사고들", 사고들)

    assert ci.주된흐름([]) == 0
    나온것 = capsys.readouterr().out
    assert "원문 소실 — 검사 불가" in 나온것
    assert "원문 소실로 검사 못 한 1건 제외" in 나온것


def test_판정이_놓치면_1을_돌려준다(monkeypatch, capsys):
    monkeypatch.setattr(ci, "사고들", [("가짜 사고", "2026-08-01", "X", "고마워", "고마워 잘했어")])
    assert ci.주된흐름([]) == 1
    assert "놓침" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --기록: 대화 기록 대조
# ---------------------------------------------------------------------------

def _줄(글, 시각, **덧붙임):
    줄 = {"type": "user", "timestamp": 시각, "cwd": "/x/proj", "message": {"content": 글}}
    줄.update(덧붙임)
    return json.dumps(줄, ensure_ascii=False)


def test_그날_기록이_없으면_놓침이_아니라_기록_없음이다(tmp_path, monkeypatch):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "s.jsonl").write_text(
        _줄("시작", "2026-09-20T01:00:00Z") + "\n", encoding="utf-8")
    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)

    assert ci.기록_대조("2026-08-18", "이게 수정이 안되었어").startswith("기록 없음")


def test_그날_기록이_있으면_거기서도_찾는다(tmp_path, monkeypatch):
    (tmp_path / "p").mkdir()
    원문 = ci.사고들[3][4]
    (tmp_path / "p" / "s.jsonl").write_text(
        _줄("히트맵 확인해줘", "2026-09-03T10:50:00Z") + "\n"
        + _줄(원문, "2026-09-03T10:55:16Z") + "\n", encoding="utf-8")
    # 서브에이전트 기록의 거절 표지는 세지 않는다
    (tmp_path / "p" / "s" / "subagents").mkdir(parents=True)
    (tmp_path / "p" / "s" / "subagents" / "agent-1.jsonl").write_text(
        _줄("지시", "2026-09-03T10:56:00Z", toolDenialKind="user-rejected") + "\n",
        encoding="utf-8")
    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)

    결과 = ci.기록_대조("2026-09-03", ci.사고들[3][3])
    assert 결과.startswith("기록에서도 잡음"), 결과
    assert "그날 총 1건" in 결과
