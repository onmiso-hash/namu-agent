"""캐릭터 그릇(나무 캐릭터 v0.1 1단계) — 스키마·카드 검사·저장·목록·불러오기."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import character  # noqa: E402
import config as cfg  # noqa: E402
import memory_sync  # noqa: E402


def _card(**over):
    card = {
        "schema_version": 1, "id": None, "name": "하린", "aliases": ["린아"],
        "personality": ["다정하고 차분함"], "speech": "처음엔 존댓말, 친해지면 반말",
        "emoji": "가끔 써요", "call_user": "허니", "relationship_start": "stranger",
        "relationship_ceiling": "lover", "likes": ["음악", "산책"],
        "sample_lines": ["오늘 점심은 챙겨 먹었어?"], "expression_level": None,
        "promises": list(character.PROMISES),
    }
    card.update(over)
    return card


@pytest.fixture
def paths(tmp_path):
    return cfg.data_paths_for(tmp_path)


# ── 그릇 등록 ────────────────────────────────────────────────────────────────
def test_character_bowl_is_registered_last_and_walled_off():
    assert cfg.BOWLS[-1].name == "character"
    # 칸막이: namu_record로 못 쓰고 검색 색인에도 안 들어간다.
    assert "character" not in cfg.BOWL_NAMES
    assert "character" not in cfg.INDEXED_BOWL_NAMES
    # 잊기가 파일을 지우므로 줄 단위 병합 줄을 만들지 않는다.
    assert not any("character" in line for line in memory_sync._gitattributes_union_lines())


def test_lock_file_is_kept_out_of_git():
    assert "memory/character/.character.lock" in memory_sync.LOCAL_EXCLUDE_LINES


def test_paths_follow_the_data_root(tmp_path):
    assert cfg.data_paths_for(tmp_path).character_dir == tmp_path / "memory" / "character"


# ── 스키마 ───────────────────────────────────────────────────────────────────
def test_schema_questions_match_the_card_keys():
    s = character.schema()
    keys = [q["key"] for q in s["questions"]]
    assert keys == ["name", "aliases", "personality", "speech", "emoji", "call_user",
                    "relationship_start", "likes", "sample_lines", "relationship_ceiling"]
    assert set(keys) <= set(s["card_keys"])
    assert s["promises"] == list(character.PROMISES)
    # 예시 카드는 그대로 저장할 수 있어야 한다.
    character.normalize_card(s["example"])


# ── 카드 검사 ────────────────────────────────────────────────────────────────
def test_promises_are_always_the_fixed_ones():
    clean = character.normalize_card(_card(promises=["아무 말"]))
    assert clean["promises"] == list(character.PROMISES)


def test_json_text_is_accepted():
    clean = character.normalize_card(json.dumps(_card(), ensure_ascii=False))
    assert clean["name"] == "하린"


@pytest.mark.parametrize("field", ["name", "personality", "speech", "call_user",
                                   "relationship_start", "relationship_ceiling"])
def test_required_fields(field):
    with pytest.raises(ValueError):
        character.normalize_card(_card(**{field: None}))


def test_unknown_field_is_rejected_not_dropped():
    with pytest.raises(ValueError, match="없는 칸"):
        character.normalize_card(_card(age=20))


def test_expression_level_must_stay_empty():
    with pytest.raises(ValueError, match="expression_level"):
        character.normalize_card(_card(expression_level="high"))


@pytest.mark.parametrize("start,ceiling,ok", [
    ("stranger", "friend", True), ("friend", "friend", True), ("friend", "crush", True),
    ("lover", "friend", False), ("lover", "crush", False),
    ("lover", "lover", True), ("lover", "open", True),
])
def test_ceiling_cannot_be_below_start(start, ceiling, ok):
    card = _card(relationship_start=start, relationship_ceiling=ceiling)
    if ok:
        character.normalize_card(card)
    else:
        with pytest.raises(ValueError, match="낮습니다"):
            character.normalize_card(card)


def test_list_limits():
    with pytest.raises(ValueError, match="2개까지"):
        character.normalize_card(_card(personality=["가", "나", "다"]))
    with pytest.raises(ValueError, match="20자까지"):
        character.normalize_card(_card(name="가" * 21))


# ── 저장·목록 ────────────────────────────────────────────────────────────────
def test_save_assigns_an_id_and_lists(paths):
    r = character.save(_card(), paths=paths)
    assert r["created"] is True and len(r["id"]) == 26
    listed = character.list_all(paths)
    assert [c["name"] for c in listed] == ["하린"]
    assert listed[0]["stage"] == "stranger" and listed[0]["affection"] == 10
    assert (paths.character_dir / r["id"] / "card" / f"{r['version']}.yaml").is_file()


@pytest.mark.parametrize("other", [
    {"name": "하린"}, {"name": " 하 린 "}, {"name": "도윤", "aliases": ["린아"]},
    {"name": "린아", "aliases": []},
])
def test_names_and_aliases_cannot_collide(paths, other):
    character.save(_card(), paths=paths)
    with pytest.raises(ValueError, match="이미 캐릭터"):
        character.save(_card(**other), paths=paths)


def test_update_needs_the_current_version_and_keeps_old_versions(paths):
    first = character.save(_card(), paths=paths)
    card = _card(id=first["id"], speech="반말")
    with pytest.raises(ValueError, match="base_version"):
        character.save(card, paths=paths)
    second = character.save(card, base_version=first["version"], paths=paths)
    assert second["created"] is False and second["id"] == first["id"]
    # 같은 판에서 또 고치려 하면(다른 곳에서 먼저 고친 경우) 거절된다.
    with pytest.raises(ValueError, match="먼저 고쳤습니다"):
        character.save(_card(id=first["id"], speech="존댓말"), base_version=first["version"],
                       paths=paths)
    versions = sorted((paths.character_dir / first["id"] / "card").glob("*.yaml"))
    assert len(versions) == 2
    assert character.load("하린", paths)["card"]["speech"] == "반말"


def test_update_of_unknown_id_is_rejected(paths):
    with pytest.raises(ValueError, match="없습니다"):
        character.save(_card(id="01KZZZZZZZZZZZZZZZZZZZZZZZ"), base_version="x", paths=paths)


def test_users_do_not_see_each_other(tmp_path):
    a = cfg.data_paths_for(tmp_path / "a")
    b = cfg.data_paths_for(tmp_path / "b")
    character.save(_card(), paths=a)
    assert character.list_all(b) == []
    character.save(_card(), paths=b)  # 다른 사람이면 같은 이름도 된다


# ── 불러오기 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("by", ["하린", "린아", "  린 아 "])
def test_load_by_name_or_alias(paths, by):
    character.save(_card(), paths=paths)
    out = character.load(by, paths)
    assert out["card"]["name"] == "하린"
    assert '너는 지금부터 "하린"이다.' in out["persona"]
    assert '사용자를 "허니"라고 부른다.' in out["persona"]
    assert "처음 만난 사이" in out["persona"]
    assert "자신이 AI라는 걸 숨기지 않는다." in out["persona"]
    assert out["relationship"]["since_last_talk"] == "아직 대화한 적 없음"


def test_load_by_id(paths):
    r = character.save(_card(), paths=paths)
    assert character.load(r["id"], paths)["id"] == r["id"]


def test_load_unknown_lists_who_exists(paths):
    character.save(_card(), paths=paths)
    with pytest.raises(ValueError, match="하린"):
        character.load("도윤", paths)


def test_load_stays_small(paths):
    big = _card(
        name="가" * 20, aliases=["나" * 20, "다" * 20, "라" * 20],
        personality=["마" * 40, "바" * 40], speech="사" * 60, emoji="아" * 20,
        call_user="자" * 20, likes=["차" * 20] * 1 + ["카" * 20, "타" * 20, "파" * 20, "하" * 20],
        sample_lines=["거" * 100, "너" * 100, "더" * 100],
    )
    character.save(big, paths=paths)
    out = character.load("가" * 20, paths)
    # 카드만 있을 때의 크기. 일기·핵심 기억이 붙는 2단계에서 다시 잰다.
    assert len(json.dumps(out, ensure_ascii=False)) < 4000


# ── 관계 계산 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("start,affection", [("stranger", 10), ("friend", 45), ("lover", 80)])
def test_start_values(start, affection):
    card = character.normalize_card(_card(relationship_start=start, relationship_ceiling="open"))
    assert character.compute_state(card, [])["affection"] == affection


def test_deltas_are_clipped_and_score_stays_in_range():
    card = character.normalize_card(_card())
    state = character.compute_state(card, [{"affection_delta": 50}])
    assert state["affection"] == 15
    state = character.compute_state(card, [{"affection_delta": -5}] * 10 + [{"affection_delta": 5}])
    assert state["affection"] == 5


def test_stage_never_passes_the_ceiling():
    card = character.normalize_card(_card(relationship_start="friend", relationship_ceiling="friend"))
    state = character.compute_state(card, [{"affection_delta": 5}] * 20)
    assert state["affection"] == 100 and state["stage"] == "friend"


def test_call_user_change_and_last_talk():
    card = character.normalize_card(_card())
    state = character.compute_state(card, [
        {"affection_delta": 1, "at": "2026-10-01T10:00:00+09:00", "call_user_change": "자기"},
    ])
    assert state["call_user_now"] == "자기"
    assert state["last_talk_at"] == "2026-10-01T10:00:00+09:00"
