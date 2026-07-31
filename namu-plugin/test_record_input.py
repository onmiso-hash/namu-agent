"""기록 입력 검증 테스트 (namu-65 구현 2단계 — record_input.py).

핵심 보증은 완료조건 7 — **조용히 버리는 경로가 하나도 없다**. 그래서 "거절한다"는
테스트만큼이나 "버리지 않고 옮긴 뒤 알린다"는 테스트가 중요하다. 옛 이름을 말없이
무시하는 것도 이번 사고와 같은 종류의 유실이기 때문이다.

거절 메시지는 문구 전체를 못 박지 않고 **핵심 단서만** 확인한다(무엇이 잘못됐는지·
어디로 가야 하는지). 문구를 통째로 고정하면 안내를 다듬을 때마다 테스트가 깨져서,
결국 메시지를 안 고치게 된다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import record_input as ri


def _learning(**over):
    base = {
        "bowl": "learnings",
        "topic": "namu-65",
        "summary": "한 줄 요약",
        "reason": "왜 그런가",
        "body": "그때 무슨 일이 있었나",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# 그릇 확정
# ---------------------------------------------------------------------------

def test_bowl_must_be_given():
    with pytest.raises(ValueError) as err:
        ri.normalize({"summary": "요약", "reason": "이유", "body": "본문"})
    assert "bowl" in str(err.value)
    # 네 그릇을 모두 알려줘야 고를 수 있다.
    for name in cfg.BOWL_NAMES:
        assert name in str(err.value)


def test_missing_bowl_message_suggests_a_candidate():
    with pytest.raises(ValueError) as err:
        ri.normalize({"summary": "요약", "reason": "이유", "body": "본문",
                      "project": "namu-agent"})
    assert "작업일지" in str(err.value)


def test_unknown_bowl_is_rejected():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(bowl="lessons"))
    assert "lessons" in str(err.value)


def test_legacy_kind_still_routes_and_says_so():
    # 옛 호출을 깨뜨리지 않는다 — 대신 어디로 갔는지 알린다.
    result = ri.normalize({
        "kind": "fact", "subject": "사용자", "statement": "한 줄",
        "source": "직접 들음", "body": "경위",
    })
    assert result.bowl == "profile"
    assert any("kind" in note for note in result.notices)


def test_legacy_kind_conflicting_with_bowl_is_rejected():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(kind="fact"))
    assert "어긋" in str(err.value)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        ri.normalize({"kind": "메모", "summary": "요약", "reason": "이유", "body": "본문"})


# ---------------------------------------------------------------------------
# 옛 이름 → 새 이름 (버리지 않고 옮긴 뒤 알린다)
# ---------------------------------------------------------------------------

def test_old_names_are_moved_and_reported():
    result = ri.normalize({
        "bowl": "learnings", "task": "namu-65", "outcome": "success",
        "reason": "왜", "body": "경위", "summary": "한 줄",
        "task_type": "code", "verified_by": "human",
    })
    assert result.values["topic"] == "namu-65"
    assert result.values["status"] == "success"
    assert result.values["category"] == "code"
    assert result.values["confidence"] == "human"
    for old in ("task", "outcome", "task_type", "verified_by"):
        assert any(f"'{old}'" in note for note in result.notices), old


def test_text_is_rescued_into_body_for_learnings():
    # 사고의 재현 방지 — 옛 경로에서 통째로 버려지던 값이다.
    result = ri.normalize({
        "bowl": "learnings", "topic": "조사", "summary": "한 줄", "reason": "왜",
        "text": "조사 자료 원문 전체",
    })
    assert result.values["body"] == "조사 자료 원문 전체"
    assert any("body" in note for note in result.notices)


def test_text_becomes_the_summary_line_for_tasks():
    result = ri.normalize({
        "bowl": "tasks", "project": "namu-agent", "task": "namu-65",
        "text": "진행 한 줄", "reason": "왜", "body": "상세",
    })
    assert result.values["summary"] == "진행 한 줄"


def test_old_and_new_name_together_is_rejected():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(task="namu-65", topic="namu-65"))
    assert "topic" in str(err.value)


def test_retired_kind_alone_is_reported_not_silently_dropped():
    result = ri.normalize(_learning(kind="lesson"))
    assert result.bowl == "learnings"
    assert any("kind" in note for note in result.notices)


def test_unknown_field_name_is_rejected():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(메모="뭔가"))
    assert "메모" in str(err.value)


def test_old_name_from_another_bowl_points_at_that_bowl():
    with pytest.raises(ValueError) as err:
        ri.normalize({"bowl": "memo", "summary": "한 줄", "reason": "왜",
                      "body": "원문", "tag": "기록"})
    assert "작업일지" in str(err.value)


# ---------------------------------------------------------------------------
# 그릇이 받지 않는 칸 — 거절하고 갈 곳을 알려준다
# ---------------------------------------------------------------------------

def test_foreign_field_is_rejected_with_destination():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(project="namu-agent"))
    assert "project" in str(err.value)
    assert "작업일지" in str(err.value)


def test_memo_does_not_take_topic():
    with pytest.raises(ValueError) as err:
        ri.normalize({"bowl": "memo", "summary": "한 줄", "reason": "왜",
                      "body": "원문", "topic": "장보기"})
    assert "topic" in str(err.value)


def test_tasks_do_not_take_tags():
    with pytest.raises(ValueError) as err:
        ri.normalize({"bowl": "tasks", "project": "namu-agent", "topic": "namu-65",
                      "summary": "한 줄", "reason": "왜", "body": "상세",
                      "tags": ["중요"]})
    assert "tags" in str(err.value)


# ---------------------------------------------------------------------------
# 필수 칸 / `생략`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["summary", "reason", "body", "topic"])
def test_required_fields_are_enforced(missing):
    data = _learning()
    del data[missing]
    with pytest.raises(ValueError) as err:
        ri.normalize(data)
    assert missing in str(err.value)
    assert cfg.OMITTED in str(err.value)  # 고치는 법을 함께 알려준다


def test_blank_string_counts_as_missing():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(reason="   "))
    assert "reason" in str(err.value)


def test_omitted_marker_satisfies_a_required_field():
    result = ri.normalize(_learning(body=cfg.OMITTED))
    assert result.values["body"] == cfg.OMITTED


def test_memo_body_cannot_be_omitted():
    # 쪽지는 붙여둔 원문이 본체라, 생략하면 남는 게 없다.
    with pytest.raises(ValueError) as err:
        ri.normalize({"bowl": "memo", "summary": "한 줄", "reason": "왜",
                      "body": cfg.OMITTED})
    assert "body" in str(err.value)


def test_memo_minimal_call_passes():
    result = ri.normalize({"bowl": "memo", "summary": "영화 8시 20분",
                           "reason": "오늘 저녁 약속", "body": "8시 20분 3관 예매 완료"})
    assert result.bowl == "memo"
    assert result.values["summary"] == "영화 8시 20분"


# ---------------------------------------------------------------------------
# 정해진 값
# ---------------------------------------------------------------------------

def test_closed_values_are_enforced_for_learnings_status():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(status="완료"))
    assert "success" in str(err.value)


def test_task_status_stays_free_form():
    # 실제 로그에 30가지 꼬리표가 쓰이고 있어 닫으면 기존 사용이 깨진다.
    result = ri.normalize({
        "bowl": "tasks", "project": "namu-agent", "topic": "namu-65",
        "summary": "한 줄", "reason": "왜", "body": "상세", "status": "분담",
    })
    assert result.values["status"] == "분담"


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError) as err:
        ri.normalize(_learning(category="설계"))
    assert "code" in str(err.value)


# ---------------------------------------------------------------------------
# 통과 경로 — 값이 그대로 살아 나온다
# ---------------------------------------------------------------------------

def test_clean_learning_passes_through_unchanged():
    data = _learning(status="failure", category="code", confidence="human",
                     tags=["회귀"])
    result = ri.normalize(data)
    assert result.bowl == "learnings"
    assert result.notices == []
    assert result.values == data


def test_false_create_flag_does_not_trigger_a_rejection():
    # 도구 기본값(create=False)이 쪽지 호출에 딸려 들어와도 엉뚱한 거절이 나면 안 된다.
    result = ri.normalize({"bowl": "memo", "summary": "한 줄", "reason": "왜",
                           "body": "원문", "create": False})
    assert "create" not in result.values


def test_task_creation_call_passes():
    result = ri.normalize({
        "bowl": "tasks", "project": "namu-agent", "topic": "namu-70",
        "title": "새 작업", "purpose": "왜 만드는가", "body": "착수 지점",
        "create": True, "done_when": ["조건 하나"],
    })
    assert result.values["summary"] == "새 작업"
    assert result.values["reason"] == "왜 만드는가"
    assert result.values["create"] is True
