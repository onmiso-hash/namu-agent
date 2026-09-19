"""주간 점검이 '종료 훅이 안 돌았다'고 알리는 세션을 제대로 가리는지 본다.

2026-09-19 점검에서 도구가 세션 40개를 두고 "종료 훅이 돌지 않았다"고 알렸다.
실제로 훅이 빠진 것은 2개였다. 나머지 38개 가운데 36개는 세션 측정 그릇이 생기기
전에 끝난 세션이라 잴 수단 자체가 없었고, 2개는 지금 돌고 있는 세션이었다.

거짓 경보를 고치지 않으면 두 가지가 무너진다. 첫째, 매주 같은 경보가 나오므로
사람이 경보를 읽지 않게 된다. 둘째, 주된 지표가 고장 난 장치에서 나온 값처럼
보여 "지난주보다 나아졌는가"라는 물음의 답을 믿을 수 없게 된다.

그래서 이 시험은 세 갈래를 각각 세운다 — 그릇이 생기기 전에 끝난 세션, 그 뒤에
끝났는데 값이 없는 세션, 아직 안 끝난 세션.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "naite"))
import naite  # noqa: E402
import sessions  # noqa: E402
import weekly_check as wc  # noqa: E402

그릇_시작 = datetime(2026, 9, 12, 5, 53, tzinfo=timezone.utc)

# 이름 -> 그 세션의 마지막 발화 시각
세션들 = {
    "old": 그릇_시작 - timedelta(days=3),      # 그릇이 생기기 전에 끝났다
    "missed": 그릇_시작 + timedelta(hours=2),  # 그 뒤에 끝났는데 값이 없다
    "live": None,                              # 방금까지 말이 오갔다(아직 안 끝남)
}


@pytest.fixture
def 대화기록(tmp_path, monkeypatch):
    """가짜 대화 기록 세 개를 깔고, 나이테가 그것을 읽도록 갈아끼운다."""
    지금 = datetime.now(timezone.utc)
    때 = {이름: (끝 if 끝 else 지금 - timedelta(minutes=5))
          for 이름, 끝 in 세션들.items()}
    for 이름 in 세션들:
        (tmp_path / ("%s.jsonl" % 이름)).write_text("", encoding="utf-8")

    def 세션_읽기(파일):
        끝 = 때[파일.stem]
        시작 = 끝 - timedelta(minutes=10)
        return {"발화": [(시작.isoformat(), "첫 말"), (끝.isoformat(), "끝 말")]}

    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)
    monkeypatch.setattr(naite, "세션_읽기", 세션_읽기)
    monkeypatch.setattr(naite, "되돌림_찾기", lambda 세션: [])
    monkeypatch.setattr(sessions, "since", lambda 기준: [])
    return tmp_path


def test_그릇이_생기기_전에_끝난_세션은_훅의_실패가_아니다(대화기록, monkeypatch):
    """잴 수단이 없었던 때의 세션을 세면 도구가 매주 거짓 경보를 낸다."""
    monkeypatch.setattr(
        sessions, "load_all", lambda: [{"timestamp": 그릇_시작.isoformat()}])

    _, _, _, 빠짐 = wc.어긋남_재기()

    assert 빠짐 == 1, "그릇이 생긴 뒤에 끝난 'missed' 하나만 세어야 한다"


def test_아직_안_끝난_세션은_세지_않는다(대화기록, monkeypatch):
    """지금 돌고 있는 세션은 종료 훅이 아직 돌 차례가 아니다.

    그릇을 비워 두어 시작 시각 기준이 없는 상태로 만든다. 그래도 'live'는 빠져야
    하므로, 남는 것은 이미 끝난 'old'와 'missed' 둘이다.
    """
    monkeypatch.setattr(sessions, "load_all", lambda: [])

    _, _, _, 빠짐 = wc.어긋남_재기()

    assert 빠짐 == 2, "끝난 세션 둘만 세고 돌고 있는 세션은 빼야 한다"


def test_측정_시작_시각은_그릇에서_가장_이른_적은_시각이다(monkeypatch):
    """여러 항목 가운데 가장 이른 것이 기준이다. 읽을 수 없는 시각은 건너뛴다."""
    monkeypatch.setattr(sessions, "load_all", lambda: [
        {"timestamp": "2026-09-14T00:00:00+09:00"},
        {"timestamp": "말이 안 되는 시각"},
        {"timestamp": "2026-09-12T14:53:44+09:00"},
    ])

    assert wc.측정_시작_시각() == datetime.fromisoformat("2026-09-12T14:53:44+09:00")


def test_그릇이_비면_시작_시각이_없다(monkeypatch):
    """기준을 지어내지 않는다 — 없으면 없다고 답하고, 부르는 쪽이 가린다."""
    monkeypatch.setattr(sessions, "load_all", lambda: [])

    assert wc.측정_시작_시각() is None
