"""나이테 명령줄(되돌림)의 도구 거절 가르기와 서브에이전트 기록 제외(2026-09-25 리뷰 D).

toolDenialKind에는 사람이 거절한 것(user-rejected)과 자동 모드 분류기가 막은 것
(automode-blocked)이 섞여 온다. 전부 '도구 거절'로 세던 것을 사람의 거절만 세도록
고쳤고, 자동 모드가 막은 것은 되돌림에 넣지 않되 숨기지 않고 따로 보여준다.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "naite"))
import naite  # noqa: E402


def _줄(시각, 글=None, **덧붙임):
    줄 = {"type": "user", "timestamp": 시각, "cwd": "/x/proj",
          "message": {"content": 글 or [{"type": "tool_result", "content": "x"}]}}
    줄.update(덧붙임)
    return json.dumps(줄, ensure_ascii=False)


def _깔기(tmp_path):
    지금 = datetime.now(timezone.utc)
    t = [(지금 - timedelta(hours=1, minutes=-i)).isoformat().replace("+00:00", "Z")
         for i in range(5)]
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "s1.jsonl").write_text("\n".join([
        _줄(t[0], "작업 시작하자"),
        _줄(t[1], toolDenialKind="user-rejected"),
        _줄(t[2], toolDenialKind="automode-blocked"),
        _줄(t[3], toolDenialKind="automode-blocked"),
    ]) + "\n", encoding="utf-8")
    # 서브에이전트 기록 — 세지 않는다
    (tmp_path / "p" / "s1" / "subagents").mkdir(parents=True)
    (tmp_path / "p" / "s1" / "subagents" / "agent-a.jsonl").write_text(
        _줄(t[4], toolDenialKind="user-rejected") + "\n", encoding="utf-8")
    return tmp_path / "p" / "s1.jsonl"


def test_세션_읽기는_거절을_종류대로_가른다(tmp_path):
    파일 = _깔기(tmp_path)
    세션 = naite.세션_읽기(파일)
    assert len(세션["거절"]) == 1
    assert len(세션["자동차단"]) == 2
    assert [종류 for _, 종류, _ in 세션["거절_표지"]] == [
        "user-rejected", "automode-blocked", "automode-blocked"]
    갈래 = [건["갈래"] for 건 in naite.되돌림_찾기(세션)]
    assert 갈래 == ["도구 거절"]


def test_되돌림_명령은_자동_차단을_따로_보여주고_서브에이전트를_뺀다(tmp_path, monkeypatch, capsys):
    _깔기(tmp_path)
    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)

    assert naite.주된흐름(["되돌림"]) == 0
    나온것 = capsys.readouterr().out
    assert "되돌림 1건" in 나온것
    assert "자동 모드가 막은 도구 호출 2건은 되돌림에 넣지 않았습니다" in 나온것
    assert "도구 거절 1건" in 나온것


def test_대화_기록_파일들은_서브에이전트_기록을_뺀다(tmp_path):
    _깔기(tmp_path)
    assert [p.name for p in naite.대화_기록_파일들(tmp_path)] == ["s1.jsonl"]


def test_요약의_오탐률은_README의_최신_실측과_같다():
    """요약 끝의 숫자와 README '지금까지 잰 정확도'의 '고친 뒤' 값이 갈라지지 않게 한다."""
    readme = (Path(__file__).parent / "naite" / "README.md").read_text(encoding="utf-8")
    코드 = (Path(__file__).parent / "naite" / "naite.py").read_text(encoding="utf-8")
    assert "12 (19%)" in readme
    assert "실측 19%" in 코드


# ---------------------------------------------------------------------------
# 2026-09-25 분석에서 드러난 셈의 결함
# ---------------------------------------------------------------------------

def _ai_도구(시각, 도구_id, 이름):
    return json.dumps({"type": "assistant", "timestamp": 시각, "message": {
        "role": "assistant", "content": [{"type": "tool_use", "id": 도구_id, "name": 이름}]}},
        ensure_ascii=False)


def _거절(시각, 도구_id):
    return json.dumps({"type": "user", "timestamp": 시각, "toolDenialKind": "user-rejected",
                       "message": {"role": "user", "content": [
                           {"type": "tool_result", "tool_use_id": 도구_id, "content": "rejected"}]}},
                      ensure_ascii=False)


def _기록(tmp_path, 줄들):
    파일 = tmp_path / "s.jsonl"
    파일.write_text("\n".join(줄들) + "\n", encoding="utf-8")
    return naite.세션_읽기(파일)


def test_거절과_같은_순간의_중단은_한_건이다(tmp_path):
    세션 = _기록(tmp_path, [
        _줄("2026-09-12T07:50:00.000Z", "고쳐줘"),
        _ai_도구("2026-09-12T07:53:32.000Z", "t1", "Bash"),
        _거절("2026-09-12T07:53:38.999Z", "t1"),
        _줄("2026-09-12T07:53:39.002Z", "[Request interrupted by user for tool use]"),
        # 짝이 아닌 중단 — 따로 센다
        _줄("2026-09-12T08:10:00.000Z", "[Request interrupted by user]"),
    ])
    갈래 = sorted(건["갈래"] for 건 in naite.되돌림_찾기(세션))
    assert 갈래 == ["도구 거절", "요청 중단"]
    assert len(세션["중단"]) == 2, "중단 원본은 그대로 둔다 — 거두는 것은 판정 때다"


def test_선택지_창을_닫은_것은_되돌림이_아니다(tmp_path):
    세션 = _기록(tmp_path, [
        _줄("2026-09-03T16:10:00.000Z", "작업 고르자"),
        _ai_도구("2026-09-03T16:12:50.000Z", "q1", "AskUserQuestion"),
        _거절("2026-09-03T16:13:17.238Z", "q1"),
        _줄("2026-09-03T16:13:17.241Z", "[Request interrupted by user for tool use]"),
        _줄("2026-09-03T16:13:40.000Z", "접속자 주소는 로그인한 상태에서만 볼 수 있게 해줘."),
    ])
    assert 세션["거절"] == []
    assert 세션["선택창"] == ["2026-09-03T16:13:17.238Z"]
    assert 세션["거절_표지"] == [("2026-09-03T16:13:17.238Z", "user-rejected", "AskUserQuestion")]
    assert naite.되돌림_찾기(세션) == []


def test_덧붙여_곧바로_다시_보낸_말은_한_번만_센다():
    앞 = "지도에 왜 나무클라우드만을 넣는데? 그냥 이 이미지 처럼 추가해 달라니깐?"
    세션 = {"발화": [("2026-09-03T22:20:00Z", "지도 고쳐줘"),
                     ("2026-09-03T22:23:28Z", 앞),
                     ("2026-09-03T22:24:09Z", 앞 + " 이해가 안되면 질문을 해!")],
            "중단": [], "거절": []}
    건들 = naite.되돌림_찾기(세션)
    assert [건["시각"] for 건 in 건들] == ["2026-09-03T22:24:09Z"]

    # 창을 넘기면 따로 센다
    세션["발화"][2] = ("2026-09-03T22:30:00Z", 세션["발화"][2][1])
    assert len(naite.되돌림_찾기(세션)) == 2


@pytest.mark.parametrize("글", [
    "배포절차서가 있지않아? 그걸 찾아서 보라고~",
    "이미 그렇게 되어 있지 않아? 확인해 보고 안되어 있으면 해줘",
    "정확히.. 갈라? <--- 이런말 쓰지마! 나눠서 말하라고",
    "거짓말 하지말고 답을 읽어서 보고해~",
    "그만해",
    "아냐.. 시험하지 말고 소스를 확인해!~!!!",
])
def test_새_신호가_분명한_반박을_잡는다(글):
    세션 = {"발화": [("2026-09-01T00:00:00Z", "작업하자"), ("2026-09-01T00:01:00Z", 글)],
            "중단": [], "거절": []}
    assert naite.되돌림_찾기(세션), 글


@pytest.mark.parametrize("글", ["하지만 그건 다음에 하자", "쓰지 않는 파일은 지워줘", "아냐?"])
def test_새_신호가_평범한_말은_잡지_않는다(글):
    세션 = {"발화": [("2026-09-01T00:00:00Z", "작업하자"), ("2026-09-01T00:01:00Z", 글)],
            "중단": [], "거절": []}
    assert not any(set(건["신호"].split("·")) & {"있던 것 짚기", "금지", "멈춤"}
                   for 건 in naite.되돌림_찾기(세션)), 글


def test_방_이름은_대소문자를_가리지_않는다(tmp_path, monkeypatch, capsys):
    (tmp_path / "p").mkdir()
    지금 = datetime.now(timezone.utc)
    t0 = (지금 - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    t1 = (지금 - timedelta(minutes=50)).isoformat().replace("+00:00", "Z")
    (tmp_path / "p" / "s.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": t0, "cwd": "/x/Project",
                    "message": {"content": "시작"}}, ensure_ascii=False) + "\n"
        + json.dumps({"type": "user", "timestamp": t1, "cwd": "/x/Project",
                      "message": {"content": "아니지 그게 아니야"}}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(naite, "기록_뿌리", tmp_path)

    assert naite.주된흐름(["되돌림", "--방", "project"]) == 0
    assert "되돌림 1건" in capsys.readouterr().out
    assert naite.방_열쇠("Project") == naite.방_열쇠(" project ")
