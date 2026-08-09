"""config.FIELDS 그릇별 허용 칸 선언 테스트 (namu-65 구현 1단계).

이 표에서 입력 검증(2단계)·거절 메시지·도구 설명문·저장 계층 칸 목록(3단계)이 전부
파생되므로, 표 자체가 앞뒤가 맞는지를 여기서 못 박는다. 특히 **선언끼리 어긋나는
경우**(없는 그릇 이름, bowls에 없는데 required_in에 있는 칸, 옛 이름과 새 이름이
겹치는 경우)는 사람이 눈으로 놓치기 쉬운데 파생된 뒤에는 "그릇마다 다르게 거절한다"
같은 형태로만 드러나 원인을 찾기 어렵다.

config.py는 import 시점 부작용이 없어(경로 상수·순수 함수 정의뿐) 직접 import한다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg

_LAYERS = ("summary", "reason", "body")


# ---------------------------------------------------------------------------
# 표 자체의 정합성
# ---------------------------------------------------------------------------

def test_field_names_are_unique():
    assert len(cfg.FIELD_NAMES) == len(set(cfg.FIELD_NAMES))


def test_field_count_matches_design():
    # 설계서 4장: 19개 → 13개로 줄이는 것이 namu-65의 완료조건 1이었다.
    # +2 = 첨부 기록 그릇 전용 path·bytes(namu-file-upload-download 4단계).
    # +1 = new_project(작업일지 전용) — 처음 보는 project 이름으로 새 작업을
    # 만들 때 사용자 확인 없이는 거절하는 게이트의 확인 칸이다.
    assert len(cfg.FIELDS) == 16


def test_every_field_references_only_declared_bowls():
    known = set(cfg.BOWL_NAMES)
    for field in cfg.FIELDS:
        assert set(field.bowls) <= known, field.name
        assert set(field.required_in) <= known, field.name
        assert set(field.values) <= known, field.name


def test_required_bowls_are_a_subset_of_accepting_bowls():
    # "받지도 않는 그릇에서 필수"는 어떤 입력으로도 통과할 수 없는 선언이다.
    for field in cfg.FIELDS:
        assert set(field.required_in) <= set(field.bowls), field.name


def test_every_field_has_description_and_example():
    # 완료조건 2 — 항목마다 개별 설명과 예시 한 줄. 도구 설명문을 여기서 만든다.
    for field in cfg.FIELDS:
        assert field.desc.strip(), field.name
        assert field.example.strip(), field.name


def test_field_is_frozen():
    with pytest.raises(Exception):
        cfg.FIELDS[0].name = "changed"


# ---------------------------------------------------------------------------
# 3층 — 네 그릇 공통, 전부 필수 (설계 원칙 2)
# ---------------------------------------------------------------------------

def test_three_layers_are_required_in_every_bowl():
    for bowl in cfg.BOWL_NAMES:
        assert set(_LAYERS) <= cfg.allowed_fields(bowl), bowl
        assert set(_LAYERS) <= cfg.required_fields(bowl), bowl


def test_layers_accept_all_four_bowls():
    for name in _LAYERS:
        assert set(cfg.bowls_accepting(name)) == set(cfg.BOWL_NAMES)


# ---------------------------------------------------------------------------
# 그릇 선택은 생략할 수 없다 (2026-07-31 사용자 결정)
# ---------------------------------------------------------------------------

def test_bowl_is_required_in_every_bowl():
    # 옛 동작(안 적으면 조용히 교훈행)을 그대로 두면, kind를 없애는 순간 "말없이
    # 잘못된 그릇에 담긴다"는 이번 작업의 표적 결함이 그릇 선택 자체에 남는다.
    for bowl in cfg.BOWL_NAMES:
        assert "bowl" in cfg.required_fields(bowl), bowl


def test_suggest_bowl_uses_exclusive_fields():
    assert cfg.suggest_bowl(["summary", "create"]) == "tasks"
    assert cfg.suggest_bowl(["summary", "done_when"]) == "tasks"
    assert cfg.suggest_bowl(["summary", "category"]) == "learnings"
    assert cfg.suggest_bowl(["summary", "path"]) == "attachments"
    assert cfg.suggest_bowl(["summary", "bytes"]) == "attachments"


def test_shared_fields_are_no_longer_evidence_for_a_bowl():
    # project·supersedes는 첨부 기록 그릇이 생기며 두 그릇이 함께 받는 칸이 됐다.
    # 근거가 하나로 좁혀지지 않으면 짐작하지 않는 것이 이 함수의 규칙이다 —
    # 옛 기대값(project→tasks)을 그대로 두면 빗나간 추천을 시험이 보증하게 된다.
    assert cfg.suggest_bowl(["summary", "project"]) is None
    assert cfg.suggest_bowl(["summary", "supersedes"]) is None


def test_suggest_bowl_reads_bowl_scoped_old_names():
    assert cfg.suggest_bowl(["text", "tag"]) == "tasks"
    assert cfg.suggest_bowl(["title", "purpose"]) == "tasks"


def test_suggest_bowl_returns_none_when_evidence_is_absent_or_split():
    # 3층만으로는 어느 그릇인지 알 수 없다 — 네 그릇 공통이기 때문이다.
    assert cfg.suggest_bowl(["summary", "reason", "body"]) is None
    # 근거가 갈리면 짐작하지 않는다.
    assert cfg.suggest_bowl(["project", "supersedes"]) is None
    # 사고의 원인이던 이름은 갈 곳이 그릇마다 달라 근거로 쓰지 않는다.
    assert cfg.suggest_bowl(["text"]) is None
    assert cfg.suggest_bowl([]) is None
    assert cfg.suggest_bowl(["없는칸"]) is None


# ---------------------------------------------------------------------------
# 그릇별 배치 (설계서 4장)
# ---------------------------------------------------------------------------

def test_bowl_specific_fields_are_not_shared():
    # 그릇을 나눈 이유가 사라지지 않도록, 전용 칸은 그 그릇에서만 받는다.
    assert cfg.bowls_accepting("create") == ("tasks",)
    assert cfg.bowls_accepting("done_when") == ("tasks",)
    assert cfg.bowls_accepting("category") == ("learnings",)
    # 첨부 기록 전용 2칸 — 여기 다른 그릇이 붙으면 그 그릇도 파일 이력을 받는다는
    # 뜻이고, 그러면 그릇을 새로 만든 이유가 사라진다(설계서 2판 7절).
    assert cfg.bowls_accepting("path") == ("attachments",)
    assert cfg.bowls_accepting("bytes") == ("attachments",)


def test_attachments_reuse_shared_fields_instead_of_new_ones():
    # 설계서 2판 7절: "기존 그릇의 칸을 그대로 쓴다. 새로 만드는 것은 셋뿐이다."
    # project·supersedes·tags·topic은 새로 만들지 않고 첨부 기록이 함께 쓴다.
    for name in ("project", "supersedes", "tags", "topic", "status"):
        assert "attachments" in cfg.bowls_accepting(name), name


def test_memo_takes_only_the_three_layers_plus_bowl_and_tags():
    # 쪽지는 쓰고 버리는 그릇이라 분류 칸을 늘리지 않는다 — 늘리면 지식베이스와
    # 구분이 흐려지고, 그 구분이 이 그릇의 존재 이유다.
    assert cfg.allowed_fields("memo") == frozenset({*_LAYERS, "bowl", "tags"})


def test_topic_is_required_where_it_routes_the_record():
    assert set(cfg.bowls_accepting("topic")) == {
        "learnings", "profile", "tasks", "attachments"
    }
    for bowl in ("learnings", "profile", "tasks"):
        assert "topic" in cfg.required_fields(bowl)
    # 첨부 기록에서만 선택이다 — 대화 중 만든 파일이 늘 작업에 속하지는 않는데,
    # 필수로 두면 작업 이름을 지어내 채우게 된다.
    assert "topic" not in cfg.required_fields("attachments")


def test_tasks_do_not_take_tags_and_memo_does():
    assert "tags" not in cfg.allowed_fields("tasks")
    assert "tags" in cfg.allowed_fields("memo")


# ---------------------------------------------------------------------------
# 허용값 — 그릇마다 다르다
# ---------------------------------------------------------------------------

def test_status_values_are_closed_for_learnings_but_open_for_tasks():
    assert cfg.allowed_values("status", "learnings") == ("success", "failure", "partial")
    # 실제 로그에 30가지 꼬리표가 쓰이고 있어 닫으면 기존 사용을 깬다.
    assert cfg.allowed_values("status", "tasks") == ()


def test_status_is_closed_and_required_for_attachments():
    # 첨부 기록은 고칠 수 없어서 "지금 살아 있는 파일 목록"을 status로 계산한다 —
    # 값이 열려 있으면 계산이 모르는 말이 섞이고, 비어 있으면 새 판을 첫 올림으로
    # 세어 같은 파일이 목록에 두 번 뜬다.
    assert cfg.allowed_values("status", "attachments") == ("올림", "새 판", "지움")
    assert "status" in cfg.required_fields("attachments")


def test_allowed_values_is_empty_for_free_fields_and_unknown_names():
    assert cfg.allowed_values("summary", "learnings") == ()
    assert cfg.allowed_values("없는칸", "learnings") == ()


def test_confidence_values_match_the_stored_vocabulary():
    # 저장 계층(db/profile)이 이미 쓰는 값 집합과 어긋나면 3단계에서 조용히 깨진다.
    for bowl in ("learnings", "profile"):
        assert cfg.allowed_values("confidence", bowl) == ("human", "ai", "unverified")


# ---------------------------------------------------------------------------
# 조회 도우미
# ---------------------------------------------------------------------------

def test_fields_for_keeps_declaration_order():
    names = [field.name for field in cfg.fields_for("learnings")]
    assert names == [n for n in cfg.FIELD_NAMES if n in set(names)]


def test_bowls_accepting_unknown_field_is_empty():
    # 거절 메시지가 "이 칸은 ○○ 그릇으로 보내세요"라고 말하려면, 갈 곳이 없는 경우를
    # 빈 값으로 구분할 수 있어야 한다(빈 목록을 '아무 데나 된다'로 읽으면 안 된다).
    assert cfg.bowls_accepting("text") == ()


def test_field_by_name_roundtrip():
    for name in cfg.FIELD_NAMES:
        assert cfg.field_by_name(name).name == name
    assert cfg.field_by_name("없는칸") is None


# ---------------------------------------------------------------------------
# 옛 이름 → 새 이름
# ---------------------------------------------------------------------------

def test_alias_targets_exist_and_old_names_are_retired():
    for alias in cfg.FIELD_ALIASES:
        assert set(alias.bowls) <= set(cfg.BOWL_NAMES), alias.old
        if alias.new is None:
            continue
        assert alias.new in cfg.FIELD_NAMES, alias.old
        # 옛 이름이 새 이름 목록에도 있으면 "옮기기"와 "그대로 받기"가 충돌한다.
        assert alias.old not in cfg.FIELD_NAMES, alias.old


def test_text_goes_to_different_layers_per_bowl():
    # 이 이름 하나가 이번 사고의 원인이다 — 작업일지에서는 줄에 적히는 한 줄이지만
    # 나머지 그릇에서는 통째로 버려지던 원문이라 body로 살려야 한다.
    assert cfg.resolve_field_alias("text", "tasks").new == "summary"
    for bowl in ("learnings", "profile", "memo"):
        assert cfg.resolve_field_alias("text", bowl).new == "body"


def test_bowl_scoped_alias_wins_over_global_one():
    assert cfg.resolve_field_alias("tag", "tasks").new == "status"
    # tag는 작업일지 전용 대응이라, 다른 그릇에는 전체 적용 항목이 없으면 대응이 없다.
    assert cfg.resolve_field_alias("tag", "memo") is None


def test_common_renames():
    assert cfg.resolve_field_alias("task", "learnings").new == "topic"
    assert cfg.resolve_field_alias("subject", "profile").new == "topic"
    assert cfg.resolve_field_alias("source", "profile").new == "reason"
    assert cfg.resolve_field_alias("outcome", "learnings").new == "status"
    assert cfg.resolve_field_alias("task_type", "learnings").new == "category"
    assert cfg.resolve_field_alias("verified_by", "learnings").new == "confidence"
    assert cfg.resolve_field_alias("statement", "profile").new == "summary"


def test_kind_is_retired_with_no_replacement():
    alias = cfg.resolve_field_alias("kind", "learnings")
    assert alias is not None and alias.new is None
    assert alias.note


def test_resolve_unknown_alias_is_none():
    assert cfg.resolve_field_alias("없는칸", "learnings") is None


# ---------------------------------------------------------------------------
# `생략` 한 단어 (설계 원칙 3)
# ---------------------------------------------------------------------------

def test_omitted_marker():
    assert cfg.OMITTED == "생략"
    assert cfg.is_omitted("생략")
    assert cfg.is_omitted("  생략  ")
    assert not cfg.is_omitted("")
    assert not cfg.is_omitted(None)
    assert not cfg.is_omitted("생략된 이유는 없다")


# ---------------------------------------------------------------------------
# 그릇 이름표
# ---------------------------------------------------------------------------

def test_bowl_labels_are_filled_for_every_bowl():
    for bowl in cfg.BOWLS:
        assert bowl.label.strip(), bowl.name
    assert cfg.bowl_label("profile") == "개인 사실"
    assert cfg.bowl_label("모르는그릇") == "모르는그릇"


def test_bowl_names_match_registry():
    assert cfg.BOWL_NAMES == tuple(bowl.name for bowl in cfg.BOWLS)
