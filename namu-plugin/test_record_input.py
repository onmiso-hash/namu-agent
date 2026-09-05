"""기록 입력 검증 테스트 (namu-65 구현 2단계 — record_input.py).

핵심 보증은 완료조건 7 — **조용히 버리는 경로가 하나도 없다**. 그래서 "거절한다"는
테스트만큼이나 "버리지 않고 옮긴 뒤 알린다"는 테스트가 중요하다. 옛 이름을 말없이
무시하는 것도 이번 사고와 같은 종류의 유실이기 때문이다.

거절 메시지는 문구 전체를 못 박지 않고 **핵심 단서만** 확인한다(무엇이 잘못됐는지·
어디로 가야 하는지). 문구를 통째로 고정하면 안내를 다듬을 때마다 테스트가 깨져서,
결국 메시지를 안 고치게 된다.
"""
import ast
import re
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


# ---------------------------------------------------------------------------
# 도구 설명이 AI에게 온전히 닿는가 (2026-09-05)
#
# 붙는 쪽은 도구 설명을 앞에서부터 2,048자만 쓰고 나머지는 버린다. 버려진 뒤는
# 오류도 경고도 없이 그냥 없는 것이 되므로, 넘쳤다는 사실 자체가 보이지 않는다.
# 실제로 3,226자까지 자라 36%가 잘렸고, 하필 그 뒤에 "옛 이름을 새로 쓰지 말라"는
# 유일한 경고문이 있었다 — 그 한 달간 기록 거절 113건 중 36건이 옛 이름 때문이었다.
# 칸을 늘리는 것은 앞으로도 계속 있을 일이라, 넘침을 사람이 눈치채는 대신 여기서 막는다.
# ---------------------------------------------------------------------------


def test_tool_description_fits_in_the_client_limit():
    text = ri.tool_description()
    assert len(text) <= ri.DESCRIPTION_LIMIT, (
        f"도구 설명이 {len(text)}자로 한도({ri.DESCRIPTION_LIMIT}자)를 "
        f"{len(text) - ri.DESCRIPTION_LIMIT}자 넘었습니다 — 넘친 만큼은 "
        "AI에게 닿지 않습니다. 칸 설명을 줄이거나 첫 문장만 싣도록 고치세요."
    )


def test_must_keep_rules_come_before_the_field_list():
    # 잘려도 규칙만은 살아남게 하는 구조다. 칸 목록이 먼저 오면 그 보장이 깨진다.
    text = ri.tool_description()
    assert text.index("꼭 지킬 것") < text.index("칸 목록:")


def test_rules_name_every_trap_that_actually_bit_us():
    # 한 달간 실제로 거절을 부른 넷. 설명에 없는 규칙은 부딪혀야만 알 수 있다.
    text = ri.tool_description()
    for token in ("옛 이름(", "summary", "reason", "body"):
        assert token in text
    assert str(ri._title_limit()) in text


def test_legacy_names_in_the_warning_come_from_the_table():
    # 손으로 적어 두면 표와 어긋난다 — 실제로 어긋난 채 한 달을 지났다.
    listed = set(ri._legacy_field_names())
    alive = {e.old for e in cfg.FIELD_ALIASES if e.new}
    assert listed == alive


# ---------------------------------------------------------------------------
# 거절 문구가 실재하는 칸을 가리키는가 (2026-09-05)
#
# 이것이 이번 조사에서 찾은 가장 고약한 함정이다. 새 작업을 만들 때 제목이 길면
# 서버가 "설명은 purpose(목적) 칸으로 옮기세요"라고 안내했는데, purpose는 두 달 전에
# 없앤 이름이다. 그 안내를 따르면 이번에는 "옛 이름과 새 이름을 함께 주셨습니다"로
# 거절당한다 — 서버가 제 손으로 순환을 만들고 있었다. 실측으로 제목 거절 24건과
# purpose 거절 23건이 거의 같은 수였고 시계열에서 늘 짝을 이뤘다.
#
# 칸 이름은 앞으로도 바뀐다. 바뀔 때마다 안내문을 손으로 뒤지는 대신 여기서 막는다.
# ---------------------------------------------------------------------------

def _rejection_messages(filename: str) -> list:
    """소스에서 `raise ValueError(...)` 한 덩어리씩 뽑는다(한국어가 든 것만)."""
    src = Path(__file__).with_name(filename).read_text(encoding="utf-8").splitlines()
    blocks, buf, depth = [], None, 0
    for line in src:
        if buf is None:
            if "raise ValueError(" not in line:
                continue
            buf = [line]
            depth = line.count("(") - line.count(")")
            if depth <= 0:
                blocks.append("\n".join(buf))
                buf = None
            continue
        buf.append(line)
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            blocks.append("\n".join(buf))
            buf = None
    return [b for b in blocks if re.search(r"[가-힣]", b)]


def test_rejection_messages_never_tell_the_caller_to_use_a_dead_field():
    dead = {e.old for e in cfg.FIELD_ALIASES}
    offenders = []
    for filename in ("mcp_server.py", "record_input.py"):
        for block in _rejection_messages(filename):
            # 그 이름이 없어졌다고 **설명하는** 문구는 정당하다.
            if "없앤 칸" in block or "옛 이름" in block:
                continue
            for name in dead:
                # `이름=` 또는 `이름(` 처럼 "이 칸에 적으라"는 형태만 잡는다.
                if re.search(rf"[\"'][^\"']*\b{name}=(?!\{{)", block) or re.search(
                    rf"[\"'][^\"']*\b{name}\(", block
                ):
                    offenders.append(f"{filename}: {name} — {re.sub(r'0s+', ' ', block)[:120]}")
    assert not offenders, (
        "거절 문구가 이미 없앤 칸 이름으로 안내하고 있습니다 — 그 안내를 따르면 "
        "다시 거절당합니다:\n  " + "\n  ".join(offenders)
    )


def test_all_remaining_problems_are_reported_at_once():
    # 첫 오류에서 멈추면 호출자는 한 번에 하나씩만 알게 되어 되풀이해 거절당한다.
    # 실측: 실패한 기록 시도 60건이 평균 1.9회, 많게는 5회까지 거절당했다.
    with pytest.raises(ValueError) as caught:
        ri.normalize(
            {
                "bowl": "learnings",
                "topic": "t",
                "summary": "s",
                "reason": "r",
                "body": "b",
                "project": "namu-agent",   # 교훈이 안 받는 칸
                "category": "debug",       # 목록에 없는 값
            }
        )
    message = str(caught.value)
    assert "project" in message and "debug" in message
    assert "1." in message and "2." in message


# ---------------------------------------------------------------------------
# 칸 목록에 옛 이름이 돌아오지 않는가 (2026-09-05)
#
# 옛 이름은 "그대로 불러도 받아 준다"는 친절로 남겨 둔 다리였다. 그런데 한 달간
# 실측에서 그 다리를 건넌 호출은 **0건**이고, 다리가 보인다는 이유로 AI가 새 이름과
# 함께 채워 거절당한 것이 36건이었다 — 기록 거절 113건 중 1위. 그래서 목록에서 뺐다.
# 이관 로직(normalize)은 그대로 두었으므로 다른 진입점에서 들어오면 여전히 옮겨진다.
#
# 다시 넣고 싶어지면 이 시험을 지우기 전에 위 실측부터 다시 하라.
# ---------------------------------------------------------------------------


def _tool_parameters(path: Path, func_name: str) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            args = node.args
            return {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    raise AssertionError(f"{func_name}을 {path.name}에서 찾지 못했습니다")


def test_record_tool_hides_every_dead_field_name():
    exposed = _tool_parameters(Path(__file__).with_name("mcp_server.py"), "namu_record")
    dead = {e.old for e in cfg.FIELD_ALIASES}
    leaked = sorted(exposed & dead)
    assert not leaked, (
        f"옛 이름 {leaked}가 칸 목록에 다시 보입니다 — 아무도 쓰지 않으면서 "
        "새 이름과 함께 채워져 거절만 부릅니다."
    )


def test_normalize_still_accepts_dead_names_from_other_callers():
    # 감춘 것이지 없앤 것이 아니다 — 다른 진입점에서 들어오면 새 칸으로 옮겨야 한다.
    parsed = ri.normalize(
        {"bowl": "learnings", "topic": "t", "statement": "s", "body": "b", "source": "r"}
    )
    assert parsed.values["summary"] == "s"
    assert parsed.values["reason"] == "r"
    assert any("옮겨 저장" in n for n in parsed.notices)
