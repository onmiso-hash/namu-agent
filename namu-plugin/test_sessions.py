"""세션 측정 그릇과 세션 종료 훅 테스트 (namu-self-improvement-loop).

이 그릇의 존재 이유는 "대화 기록이 사라지고 동기화되지 않아도 잰 값은 남는다"이며,
그래서 여기서 지켜야 하는 것은 넷이다.

1. **세션마다 마지막 항목 하나만 센다.** append-only라 `--resume`으로 이어 열면
   항목이 또 붙는데, 둘을 다 세면 어긋남이 두 배로 보인다.
2. **기간은 글자가 아니라 시각으로 가른다.** 대화 기록의 시각은 세계 표준시에 `Z`가
   붙고 나무가 적는 시각은 `+09:00`이 붙는다. 문자열로 견주면 같은 순간이 다른
   순서로 줄을 선다.
3. **사람이 한 마디도 안 한 세션은 남기지 않는다.** 세션 수에 넣으면 분모만 늘어
   평균이 실제보다 낮게 보인다.
4. **훅은 어떤 에러에도 세션 종료를 막지 않는다.**
5. **훅 자체는 1.5초 안에 끝나고, 떼어낸 쪽이 그 뒤에도 살아남아 일을 마친다.**
   세션 종료 훅에 주어지는 시간이 1.5초다. 2026-09-12에 커밋만 남고 원격 올리기가
   통째로 빠진 것이 이 시간을 넘긴 탓이었다.

config.py는 import 시점 부작용이 없어 직접 import한다(test_attachments.py와 같다).
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import sessions

_훅_경로 = Path(__file__).parent / "hooks" / "session_end_naite.py"


@pytest.fixture()
def paths(tmp_path):
    """사용자 폴더를 tmp로 갈아끼운 DataPaths. 실제 ~/.namu를 건드리지 않는다."""
    return cfg.data_paths_for(tmp_path)


@pytest.fixture()
def 훅():
    """훅 모듈을 파일 경로로 불러온다(hooks 폴더는 패키지가 아니다)."""
    spec = importlib.util.spec_from_file_location("session_end_naite", _훅_경로)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _발화(글, 시각, **덧붙임):
    줄 = {
        "type": "user",
        "timestamp": 시각,
        "cwd": "/home/onmiso/project/namu-agent",
        "message": {"content": 글},
    }
    줄.update(덧붙임)
    return 줄


def _기록파일(tmp_path, 줄들, 이름="세션.jsonl"):
    파일 = tmp_path / 이름
    파일.write_text(
        "\n".join(json.dumps(줄, ensure_ascii=False) for 줄 in 줄들) + "\n",
        encoding="utf-8",
    )
    return 파일


# ---------------------------------------------------------------------------
# 그릇 자체
# ---------------------------------------------------------------------------

def test_기록한_값이_그대로_다시_읽힌다(paths):
    항목_id = sessions.record_session(
        session_id="s1",
        misalignments=3,
        structural_marks=1,
        utterances=[{"at": "2026-09-12T01:00:00.000Z", "text": "아니지 그게 아니야"}],
        interrupts=["2026-09-12T01:05:00.000Z"],
        denials=[],
        project="namu-agent",
        title="시험 세션",
        started_at="2026-09-12T01:00:00.000Z",
        ended_at="2026-09-12T01:10:00.000Z",
        paths=paths,
    )
    assert 항목_id

    쌓인 = sessions.load_all(paths)
    assert len(쌓인) == 1
    하나 = 쌓인[0]
    assert 하나["session_id"] == "s1"
    assert 하나["misalignments"] == 3
    assert 하나["structural_marks"] == 1
    assert 하나["utterance_count"] == 1
    assert 하나["utterances"][0]["text"] == "아니지 그게 아니야"
    assert 하나["machine"] == cfg.NAMU_MACHINE


def test_yaml이_다중_문서로_쌓인다(paths):
    sessions.record_session(session_id="s1", misalignments=0, structural_marks=0,
                            utterances=[], paths=paths)
    sessions.record_session(session_id="s2", misalignments=1, structural_marks=0,
                            utterances=[], paths=paths)
    글 = paths.sessions_yaml.read_text(encoding="utf-8")
    assert 글.count("---\n") == 2
    assert len(list(yaml.safe_load_all(글))) == 2


def test_같은_세션은_마지막_항목만_센다(paths):
    """`--resume`으로 이어 열면 항목이 또 붙는다. 둘을 다 세면 두 배가 된다."""
    sessions.record_session(session_id="s1", misalignments=2, structural_marks=0,
                            utterances=[{"at": "t1", "text": "가"}], paths=paths)
    sessions.record_session(session_id="s1", misalignments=5, structural_marks=1,
                            utterances=[{"at": "t1", "text": "가"},
                                        {"at": "t2", "text": "나"}], paths=paths)

    assert len(sessions.load_all(paths)) == 2
    마지막 = sessions.latest_by_session(paths)
    assert list(마지막) == ["s1"]
    assert 마지막["s1"]["misalignments"] == 5
    assert 마지막["s1"]["utterance_count"] == 2


def test_기간은_글자가_아니라_시각으로_가른다(paths):
    """세계 표준시 `Z` 표기와 우리 시각 `+09:00` 표기가 섞여도 순서가 맞아야 한다.

    글자로 견주면 '2026-09-12T01:00:00.000Z'가 '2026-09-12T09:30:00+09:00'보다
    앞선 것으로 읽히는데, 실제로는 둘이 같은 순간(09-12 10시)의 전후 30분이다.
    """
    sessions.record_session(session_id="옛것", misalignments=1, structural_marks=0,
                            utterances=[], started_at="2026-09-12T00:30:00.000Z",
                            paths=paths)
    sessions.record_session(session_id="새것", misalignments=1, structural_marks=0,
                            utterances=[], started_at="2026-09-12T10:30:00+09:00",
                            paths=paths)

    기준 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone(timedelta(hours=9)))
    골라낸 = {e["session_id"] for e in sessions.since(기준, paths)}
    assert 골라낸 == {"새것"}


def test_시각을_읽을_수_없는_항목은_기간에서_뺀다(paths):
    sessions.record_session(session_id="깨진것", misalignments=9, structural_marks=0,
                            utterances=[], started_at="언제인지모름", paths=paths)
    # timestamp도 못 읽게 직접 깨뜨린다.
    글 = paths.sessions_yaml.read_text(encoding="utf-8")
    paths.sessions_yaml.write_text(글.replace("timestamp: '", "timestamp: 'X"),
                                   encoding="utf-8")

    기준 = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert sessions.since(기준, paths) == []


def test_깨진_yaml에_예외를_던지지_않는다(paths):
    paths.sessions_yaml.parent.mkdir(parents=True, exist_ok=True)
    paths.sessions_yaml.write_text("---\n이건: [깨진\n", encoding="utf-8")
    assert sessions.load_all(paths) == []


def test_session_id가_없으면_거절한다(paths):
    with pytest.raises(ValueError):
        sessions.record_session(session_id="  ", misalignments=0, structural_marks=0,
                                utterances=[], paths=paths)


# ---------------------------------------------------------------------------
# 훅의 재기
# ---------------------------------------------------------------------------

def test_훅이_어긋남과_발화를_센다(훅, tmp_path):
    파일 = _기록파일(tmp_path, [
        _발화("나이테 고쳐줘", "2026-09-12T01:00:00.000Z", aiTitle="나이테 손보기"),
        _발화("아니지 그게 아니야", "2026-09-12T01:01:00.000Z"),
        _발화("[Request interrupted by user]", "2026-09-12T01:02:00.000Z"),
        _발화("고마워", "2026-09-12T01:03:00.000Z", toolDenialKind="reject"),
    ])
    잰값 = 훅.재기(파일, "s1", "clear")

    assert 잰값["session_id"] == "s1"
    assert [u["text"] for u in 잰값["utterances"]] == [
        "나이테 고쳐줘", "아니지 그게 아니야", "고마워",
    ]
    # 되돌림 1건(되물음) + 요청 중단 1건 + 도구 거절 1건
    assert 잰값["misalignments"] == 3
    assert 잰값["structural_marks"] == 2
    assert 잰값["interrupts"] == ["2026-09-12T01:02:00.000Z"]
    assert 잰값["denials"] == ["2026-09-12T01:03:00.000Z"]
    assert 잰값["project"] == "namu-agent"
    assert 잰값["title"] == "나이테 손보기"
    assert 잰값["started_at"] == "2026-09-12T01:00:00.000Z"
    assert 잰값["ended_at"] == "2026-09-12T01:03:00.000Z"
    assert 잰값["end_reason"] == "clear"


def test_첫_발화는_어긋남으로_세지_않는다(훅, tmp_path):
    """세션의 첫 마디는 AI가 아직 아무것도 안 한 시점이라 되돌림일 수 없다."""
    파일 = _기록파일(tmp_path, [
        _발화("아니지 이거 왜 이래", "2026-09-12T01:00:00.000Z"),
    ])
    assert 훅.재기(파일, "s1", None)["misalignments"] == 0


def test_사람이_한_마디도_안_한_세션은_남기지_않는다(훅, tmp_path):
    파일 = _기록파일(tmp_path, [
        _발화("<command-name>/clear</command-name>", "2026-09-12T01:00:00.000Z"),
        _발화("훅이 넣은 안내", "2026-09-12T01:00:01.000Z", isMeta=True),
    ])
    assert 훅.재기(파일, "s1", None) is None


def test_발화가_안_늘었으면_다시_남기지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "SESSIONS_YAML_PATH", tmp_path / "sessions.yaml")
    sessions.record_session(session_id="s1", misalignments=1, structural_marks=0,
                            utterances=[{"at": "t1", "text": "가"},
                                        {"at": "t2", "text": "나"}])

    assert sessions.already_recorded("s1", 2) is True    # 그대로다
    assert sessions.already_recorded("s1", 3) is False   # 이어서 열어 발화가 늘었다
    assert sessions.already_recorded("처음보는세션", 1) is False


# ---------------------------------------------------------------------------
# 재는 규칙은 한 벌이다
#
# 훅은 대화 기록 파일에서 발화를 뽑고, 웹의 namu_record_session은 대화 안의 AI가
# 발화를 넘겨준다. 들어오는 길이 둘이라도 재는 함수는 sessions.measure 하나여야
# 한다 — 갈라지면 같은 대화도 어디서 넣었느냐에 따라 숫자가 달라져서, 합산한 값이
# 무엇을 뜻하는지 알 수 없게 된다.
# ---------------------------------------------------------------------------

def test_웹으로_넘긴_대화도_훅과_같은_값이_나온다(훅, tmp_path):
    """같은 대화를 파일로 읽었을 때와 발화 목록으로 넘겼을 때가 같아야 한다."""
    줄들 = [
        _발화("나이테 고쳐줘", "2026-09-12T01:00:00.000Z", aiTitle="나이테 손보기"),
        _발화("아니지 그게 아니야", "2026-09-12T01:01:00.000Z"),
        _발화("고마워", "2026-09-12T01:02:00.000Z"),
    ]
    훅이_잰값 = 훅.재기(_기록파일(tmp_path, 줄들), "s1", "clear")

    웹이_잰값 = sessions.measure(
        session_id="s1",
        utterances=[{"at": u["at"], "text": u["text"]} for u in 훅이_잰값["utterances"]],
        interrupts=훅이_잰값["interrupts"],
        denials=훅이_잰값["denials"],
        project=훅이_잰값["project"],
        title=훅이_잰값["title"],
        end_reason="clear",
    )

    assert 웹이_잰값 == 훅이_잰값


def test_시각을_모르면_빈_칸으로_받는다():
    """웹의 AI가 발언 시각을 모를 때 빈 문자열을 넘겨도 재기가 끝나야 한다.

    나이테가 마지막에 시각으로 정렬하므로 None이 섞이면 거기서 예외가 난다.
    """
    잰값 = sessions.measure(
        session_id="s1",
        utterances=[{"at": "", "text": "고쳐줘"}, {"at": "", "text": "아니 그게 아니고"}],
    )

    assert 잰값["misalignments"] == 1
    assert 잰값["started_at"] is None
    assert 잰값["ended_at"] is None


def test_사람_말이_하나도_없으면_재지_않는다():
    assert sessions.measure(session_id="s1", utterances=[]) is None
    assert sessions.measure(session_id="s1", utterances=[{"at": "t", "text": "  "}]) is None


# ---------------------------------------------------------------------------
# 훅을 실제로 실행했을 때
# ---------------------------------------------------------------------------

def _훅_실행(들어온값, 인자=(), 집=None):
    """훅을 별도 프로세스로 돌린다. 종료값과 출력을 돌려준다.

    집을 주면 그 폴더를 사용자 폴더로 삼는다. 나무는 기억 저장소를
    `Path.home() / ".namu"`로 고정해 두어 환경변수로 바꿀 수 없으므로, 진짜 기억을
    건드리지 않으려면 사용자 폴더 자체를 갈아끼우는 길밖에 없다.
    """
    환경 = dict(os.environ, HOME=str(집)) if 집 is not None else None
    return subprocess.run(
        [sys.executable, str(_훅_경로), *인자],
        input=json.dumps(들어온값, ensure_ascii=False),
        capture_output=True, text=True, timeout=60, env=환경,
    )


def _격리된_집(tmp_path):
    집 = tmp_path / "집"
    집.mkdir()
    return 집


def _남은_값들(집):
    파일 = 집 / ".namu" / "memory" / "sessions.yaml"
    return list(yaml.safe_load_all(파일.read_text(encoding="utf-8")))


def test_들어온_값이_비어도_세션_종료를_막지_않는다():
    for 들어온값 in ({}, {"session_id": "s1"}, {"transcript_path": "/없는/파일.jsonl"}):
        결과 = _훅_실행(들어온값)
        assert 결과.returncode == 0, 결과.stderr


def test_망가진_입력에도_종료값은_0이다():
    결과 = subprocess.run(
        [sys.executable, str(_훅_경로)],
        input="이건 JSON이 아니다", capture_output=True, text=True, timeout=60,
    )
    assert 결과.returncode == 0, 결과.stderr


def test_훅은_일을_떼어내고_곧바로_끝난다(tmp_path):
    """훅 자체는 1.5초 예산 안에 끝나고, 떼어낸 쪽은 그 뒤에도 일을 마쳐야 한다."""
    집 = _격리된_집(tmp_path)
    파일 = _기록파일(tmp_path, [
        _발화("나이테 고쳐줘", "2026-09-12T01:00:00.000Z"),
        _발화("아니 그게 아니고", "2026-09-12T01:01:00.000Z"),
    ])

    시작 = time.monotonic()
    결과 = _훅_실행({"transcript_path": str(파일), "session_id": "s1"}, 집=집)
    걸린시간 = time.monotonic() - 시작

    assert 결과.returncode == 0, 결과.stderr
    assert 걸린시간 < 1.5, f"훅이 {걸린시간:.2f}초 걸렸다 — 예산 1.5초를 넘는다"

    남을_파일 = 집 / ".namu" / "memory" / "sessions.yaml"
    마감 = time.monotonic() + 30
    while time.monotonic() < 마감 and not 남을_파일.exists():
        time.sleep(0.1)
    assert 남을_파일.exists(), "떼어낸 쪽이 값을 남기지 못한 채 사라졌다"

    assert [u["text"] for u in _남은_값들(집)[-1]["utterances"]] == [
        "나이테 고쳐줘", "아니 그게 아니고",
    ]


def test_일꾼으로_부르면_그_자리에서_남긴다(tmp_path):
    """떼어낸 쪽이 하는 일을 기다리면서 그대로 확인한다."""
    집 = _격리된_집(tmp_path)
    파일 = _기록파일(tmp_path, [_발화("가", "2026-09-12T01:00:00.000Z")])

    결과 = _훅_실행({"transcript_path": str(파일), "session_id": "s2"},
                    인자=["--worker"], 집=집)

    assert 결과.returncode == 0, 결과.stderr
    assert _남은_값들(집)[-1]["session_id"] == "s2"
