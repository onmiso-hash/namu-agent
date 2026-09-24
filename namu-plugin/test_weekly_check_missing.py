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

    빠짐 = wc.어긋남_재기().빠짐

    assert 빠짐 == 1, "그릇이 생긴 뒤에 끝난 'missed' 하나만 세어야 한다"


def test_아직_안_끝난_세션은_세지_않는다(대화기록, monkeypatch):
    """지금 돌고 있는 세션은 종료 훅이 아직 돌 차례가 아니다.

    그릇을 비워 두어 시작 시각 기준이 없는 상태로 만든다. 그래도 'live'는 빠져야
    하므로, 남는 것은 이미 끝난 'old'와 'missed' 둘이다.
    """
    monkeypatch.setattr(sessions, "load_all", lambda: [])

    빠짐 = wc.어긋남_재기().빠짐

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


# ---------------------------------------------------------------------------
# 분모 — 사람이 한 마디라도 한 세션 전부
#
# 2026-09-25까지는 어긋남이 한 건이라도 있던 세션만 분모로 셌다. 그러면 어긋남 없이
# 끝난 세션이 늘어도 "세션당 어긋남"이 줄지 않는다 — 나아졌는지 재려고 만든 지표가
# 나아진 것을 못 본다. 옛 정의 값도 함께 돌려 지난 점검과 이어 보게 한다.
# ---------------------------------------------------------------------------

def test_분모는_어긋남_없는_세션까지_사람이_말한_세션_전부다(tmp_path, monkeypatch):
    지금 = datetime.now(timezone.utc)
    그릇 = [
        # 그릇에 남은 세션 셋 — 어긋남 2건, 0건, 0건
        {"session_id": "a", "misalignments": 2, "structural_marks": 1, "utterance_count": 5},
        {"session_id": "b", "misalignments": 0, "structural_marks": 0, "utterance_count": 3},
        {"session_id": "c", "misalignments": 0, "structural_marks": 0, "utterance_count": 1},
    ]
    monkeypatch.setattr(sessions, "since", lambda 기준: 그릇)
    monkeypatch.setattr(sessions, "load_all", lambda: [])
    # 대화 기록에만 있는 세션 둘 — 사람 말이 있는 것 하나(어긋남 1건), 없는 것 하나
    for 이름 in ("d", "e"):
        (tmp_path / f"{이름}.jsonl").write_text("", encoding="utf-8")
    # 서브에이전트 기록은 세션으로 세지 않는다
    (tmp_path / "d" / "subagents").mkdir(parents=True)
    (tmp_path / "d" / "subagents" / "agent-x.jsonl").write_text("", encoding="utf-8")

    def 세션_읽기(파일):
        assert "subagents" not in 파일.parts, "서브에이전트 기록을 읽으면 안 된다"
        if 파일.stem == "e":
            return {"발화": []}
        시작 = 지금 - timedelta(hours=2)
        return {"발화": [(시작.isoformat(), "첫 말"), ((시작 + timedelta(minutes=5)).isoformat(), "아니지")]}

    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)
    monkeypatch.setattr(naite, "세션_읽기", 세션_읽기)
    monkeypatch.setattr(naite, "되돌림_찾기",
                        lambda 세션: [{"갈래": "말로 반박"}])

    잰값 = wc.어긋남_재기()

    assert 잰값.건수 == 3
    assert 잰값.세션수 == 4, "a·b·c·d — 어긋남 없는 b·c도 분모에 든다"
    assert 잰값.옛_세션수 == 2, "옛 정의는 어긋남 있던 a·d만"


def test_분모가_바뀐_첫_점검은_옛_정의끼리만_견준다(monkeypatch, capsys):
    """지난 점검의 '세션당 어긋남'은 옛 분모로 잰 값이다. 새 값과 견주면 정의가
    바뀐 것만으로 크게 좋아진 것처럼 보인다."""
    monkeypatch.setattr(wc, "어긋남_재기",
                        lambda: wc.어긋남_잰값(6, 6, 0, 0, 2))
    monkeypatch.setattr(wc, "교훈_읽기", lambda: [{
        "tags": ["나무점검"], "timestamp": "2026-09-18T00:00:00+09:00",
        "body": "세션당 어긋남: 3.10\n세션당 구조 표지: 1.00\n이번 조치: 없음 — 시험",
    }])
    monkeypatch.setattr(wc, "상시규칙_재기", lambda: (0, 0))
    monkeypatch.setattr(wc, "부류_읽기", lambda: None)
    monkeypatch.setattr(naite, "대화_기록_파일들", lambda 뿌리=None: [])

    wc.주된흐름()
    나온것 = capsys.readouterr().out

    assert "세션당 어긋남: 1.00 건   (분모 정의가 바뀌어" in 나온것
    assert "옛 정의(어긋남 있던 세션 2개로 나눔): 3.00 건   ▼ -0.10 (좋아짐)" in 나온것
    assert "    세션당 어긋남(옛 정의): 3.00" in 나온것


# ---------------------------------------------------------------------------
# 저장된 숫자 대신 지금 규칙으로 다시 잰다
# ---------------------------------------------------------------------------

def test_그릇의_숫자를_그대로_더하지_않고_다시_잰다(tmp_path, monkeypatch):
    """거절 종류가 있는 항목은 그릇의 원문으로, 없는 옛 항목은 대화 기록이 있으면
    그것으로, 없으면 원문으로 다시 잰다. 원문도 없으면 저장값이다."""
    지금 = datetime.now(timezone.utc)
    t = (지금 - timedelta(hours=3)).isoformat()
    원문 = [{"at": t, "text": "첫 말"}, {"at": t, "text": "아니지"}]
    그릇 = [
        {"session_id": "새것", "misalignments": 14, "structural_marks": 0,
         "utterances": 원문, "denial_kinds": []},
        {"session_id": "옛것_기록있음", "misalignments": 14, "structural_marks": 11,
         "utterances": 원문, "denials": ["x"] * 11},
        {"session_id": "옛것_기록없음", "misalignments": 14, "structural_marks": 11,
         "utterances": 원문, "denials": []},
        {"session_id": "숫자만", "misalignments": 5, "structural_marks": 0,
         "utterance_count": 2},
    ]
    monkeypatch.setattr(sessions, "since", lambda 기준: 그릇)
    monkeypatch.setattr(sessions, "load_all", lambda: [])
    (tmp_path / "옛것_기록있음.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)
    # 대화 기록에는 되돌림이 없다 — 옛 항목의 저장값(14)이 아니라 이것이 쓰여야 한다
    monkeypatch.setattr(naite, "세션_읽기", lambda 파일: {
        "발화": [(t, "첫 말"), (t, "고마워")], "중단": [], "거절": []})

    잰값 = wc.어긋남_재기()

    # 새것 1(원문) + 옛것_기록있음 0(대화 기록) + 옛것_기록없음 1(원문·옛 거절) + 숫자만 5
    assert 잰값.건수 == 7
    assert 잰값.근거 == {"원문": 1, "대화 기록": 1, "원문·옛 거절": 1, "저장값": 1}
    assert 잰값.빠짐 == 0, "그릇에 있는 세션은 대화 기록이 있어도 빠짐이 아니다"


def test_어떻게_쟀는지_출력에_밝힌다(monkeypatch, capsys):
    monkeypatch.setattr(wc, "어긋남_재기", lambda: wc.어긋남_잰값(
        3, 3, 0, 0, 1, {"대화 기록": 2, "저장값": 1}))
    monkeypatch.setattr(wc, "교훈_읽기", lambda: [])
    monkeypatch.setattr(wc, "상시규칙_재기", lambda: (0, 0))
    monkeypatch.setattr(wc, "부류_읽기", lambda: None)
    monkeypatch.setattr(naite, "대화_기록_파일들", lambda 뿌리=None: [])

    wc.주된흐름()
    나온것 = capsys.readouterr().out
    assert "지금 규칙으로 잰 근거: 대화 기록을 다시 읽음 2세션 · 저장된 숫자 그대로 1세션" in 나온것
    assert "실제보다 높게 나올 수 있습니다" in 나온것
