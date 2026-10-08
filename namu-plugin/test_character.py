"""캐릭터 그릇(나무 캐릭터 v0.1 1·2단계) — 스키마·카드 검사·저장·목록·불러오기·일기·핵심 기억."""
import json
import re
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


# ── 2단계: 일기 ──────────────────────────────────────────────────────────────
def _diary_files(paths, char_id, folder="diary"):
    return sorted((paths.character_dir / char_id / folder).glob("*.yaml"))


def test_diary_is_written_and_moves_the_relationship(paths):
    saved = character.save(_card(), paths=paths)
    out = character.write_diary(
        "린아", "허니가 회사 일로 지쳐 보였다.", 3, "힘든 얘기를 먼저 털어놔줌",
        mood="차분함", topics=["회사", "산책"], via="claude", paths=paths,
    )
    assert out["affection_delta"] == 3 and out["clipped_from"] is None
    assert out["relationship"]["affection"] == 13
    files = _diary_files(paths, saved["id"])
    assert [f.stem for f in files] == [out["id"]]
    doc = character.yaml.safe_load(files[0].read_text(encoding="utf-8"))
    assert doc["summary"] == "허니가 회사 일로 지쳐 보였다."
    assert doc["delta_reason"] == "힘든 얘기를 먼저 털어놔줌"
    assert doc["topics"] == ["회사", "산책"] and doc["archived"] is False
    assert "affection_delta_requested" not in doc
    loaded = character.load("하린", paths)
    assert loaded["relationship"]["affection"] == 13
    assert loaded["recent_diary"][-1]["mood"] == "차분함"


def test_diary_delta_is_clipped_and_the_request_is_kept(paths):
    saved = character.save(_card(), paths=paths)
    out = character.write_diary("하린", "엄청 신났다.", 50, "선물을 받음", paths=paths)
    assert out["affection_delta"] == 5 and out["clipped_from"] == 50
    doc = character.yaml.safe_load(_diary_files(paths, saved["id"])[0].read_text(encoding="utf-8"))
    assert doc["affection_delta"] == 5 and doc["affection_delta_requested"] == 50
    out = character.write_diary("하린", "서운했다.", -9, "약속을 잊음", paths=paths)
    assert out["affection_delta"] == -5 and out["relationship"]["affection"] == 10


@pytest.mark.parametrize("delta", [1, -1])
def test_diary_reason_is_required_when_the_score_moves(paths, delta):
    character.save(_card(), paths=paths)
    with pytest.raises(ValueError, match="delta_reason"):
        character.write_diary("하린", "그냥 수다.", delta, paths=paths)
    # 변화가 0이면 이유 없이도 된다.
    character.write_diary("하린", "그냥 수다.", 0, paths=paths)


@pytest.mark.parametrize("bad", [True, 2.5, "많이", [3]])
def test_diary_delta_must_be_an_integer(paths, bad):
    character.save(_card(), paths=paths)
    with pytest.raises(ValueError, match="affection_delta"):
        character.write_diary("하린", "수다.", bad, "이유", paths=paths)


def test_diary_accepts_integer_text(paths):
    character.save(_card(), paths=paths)
    assert character.write_diary("하린", "수다.", "+2", "즐거움", paths=paths)["affection_delta"] == 2


def test_diary_limits(paths):
    character.save(_card(), paths=paths)
    with pytest.raises(ValueError, match="summary"):
        character.write_diary("하린", "가" * 501, paths=paths)
    with pytest.raises(ValueError, match="summary"):
        character.write_diary("하린", "   ", paths=paths)
    with pytest.raises(ValueError, match="topics"):
        character.write_diary("하린", "수다.", topics=["a", "b", "c", "d", "e", "f"], paths=paths)
    with pytest.raises(ValueError, match="core_candidates"):
        character.write_diary("하린", "수다.", core_candidates=["a", "b", "c", "d"], paths=paths)
    character.write_diary("하린", "가" * 500, paths=paths)


def test_diary_for_unknown_character_is_rejected(paths):
    with pytest.raises(ValueError, match="없습니다"):
        character.write_diary("없는애", "수다.", paths=paths)


def test_stage_change_is_reported_and_shown_on_load(paths):
    character.save(_card(relationship_start="friend", relationship_ceiling="lover"), paths=paths)
    # friend 45 → 55 (단계 그대로) → 60 (crush)
    out = character.write_diary("하린", "산책.", 5, "즐거움", paths=paths)
    out = character.write_diary("하린", "산책.", 5, "즐거움", paths=paths)
    assert out["stage_change"] is None
    out = character.write_diary("하린", "고백 비슷한 말.", 5, "설렘", paths=paths)
    assert out["stage_change"] == {"from": "friend", "to": "crush"}
    change = character.load("하린", paths)["relationship"]["last_stage_change"]
    assert change["from"] == "friend" and change["to"] == "crush" and change["at"]


def test_stage_stays_under_the_ceiling_even_through_diaries(paths):
    character.save(_card(relationship_start="friend", relationship_ceiling="friend"), paths=paths)
    for _ in range(15):
        out = character.write_diary("하린", "수다.", 5, "즐거움", paths=paths)
        assert out["stage_change"] is None
    assert out["relationship"]["affection"] == 100
    assert out["relationship"]["stage"] == "friend"


def test_call_user_change_through_diary(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "호칭을 바꿨다.", 1, "가까워짐", call_user_change="자기",
                                paths=paths)
    assert out["relationship"]["call_user_now"] == "자기"
    assert '"자기"라고 부른다' in character.load("하린", paths)["persona"]


def test_diaries_from_two_places_add_up(paths):
    """웹과 터미널이 따로 쓴 일기(파일 둘)가 덮어쓰지 않고 합산된다(설계서 13장)."""
    character.save(_card(), paths=paths)
    character.write_diary("하린", "웹에서.", 4, "즐거움", via="claude.ai", paths=paths)
    character.write_diary("하린", "터미널에서.", 3, "고마움", via="claude-code", paths=paths)
    assert character.load("하린", paths)["relationship"]["affection"] == 17
    assert character.list_all(paths)[0]["affection"] == 17


# ── 2단계: 핵심 기억 ─────────────────────────────────────────────────────────
def test_candidates_wait_until_confirmed(paths):
    saved = character.save(_card(), paths=paths)
    out = character.write_diary("하린", "처음 같이 영화를 봤다.", 2, "즐거움",
                                core_candidates=["처음 같이 본 영화는 인터스텔라"], paths=paths)
    assert out["pending_count"] == 1
    pid = out["pending_added"][0]["id"]
    loaded = character.load("하린", paths)
    assert loaded["core_memories"] == []
    assert loaded["pending_memories"] == [{"id": pid, "text": "처음 같이 본 영화는 인터스텔라"}]
    assert _diary_files(paths, saved["id"], "core") == []

    res = character.core("하린", "confirm", [pid], paths=paths)
    assert res["confirmed"] == [{"id": pid, "text": "처음 같이 본 영화는 인터스텔라"}]
    assert res["pending"] == [] and res["core"][0]["id"] == pid
    loaded = character.load("하린", paths)
    assert loaded["pending_memories"] == []
    assert loaded["core_memories"] == [{"id": pid, "text": "처음 같이 본 영화는 인터스텔라"}]
    doc = character.yaml.safe_load(_diary_files(paths, saved["id"], "core")[0].read_text(encoding="utf-8"))
    assert doc["diary_id"] == out["id"] and doc["proposed_at"]


def test_reject_deletes_the_candidate(paths):
    saved = character.save(_card(), paths=paths)
    out = character.write_diary("하린", "수다.", core_candidates=["별로인 기억"], paths=paths)
    pid = out["pending_added"][0]["id"]
    res = character.core("하린", "reject", pid, paths=paths)
    assert res["rejected"][0]["id"] == pid and res["core"] == [] and res["pending"] == []
    assert _diary_files(paths, saved["id"], "pending") == []


def test_core_cannot_take_new_text_or_unknown_ids(paths):
    """core로 가는 길은 대기 후보의 id 하나뿐 — 글을 받는 길이 없고, 모르는 id가 섞이면
    아무것도 바꾸지 않는다."""
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "수다.", core_candidates=["좋은 기억"], paths=paths)
    pid = out["pending_added"][0]["id"]
    with pytest.raises(ValueError, match="id 모양"):
        character.core("하린", "confirm", ["우리가 처음 만난 날"], paths=paths)
    unknown = "01" + "A" * 24
    with pytest.raises(ValueError, match="아무것도 바꾸지"):
        character.core("하린", "confirm", [pid, unknown], paths=paths)
    assert character.core("하린", paths=paths)["pending"] == [{"id": pid, "text": "좋은 기억"}]
    with pytest.raises(ValueError, match="ids"):
        character.core("하린", "confirm", paths=paths)
    with pytest.raises(ValueError, match="action"):
        character.core("하린", "add", [pid], paths=paths)


def test_pending_has_a_ceiling_and_the_diary_is_not_half_written(paths):
    saved = character.save(_card(), paths=paths)
    for i in range(3):
        character.write_diary("하린", f"수다 {i}.", core_candidates=[f"기억 {i}-{j}" for j in range(3)],
                              paths=paths)
    assert len(_diary_files(paths, saved["id"], "pending")) == 9
    with pytest.raises(ValueError, match="저장하지 않았습니다"):
        character.write_diary("하린", "넘치는 날.", core_candidates=["a", "b"], paths=paths)
    assert len(_diary_files(paths, saved["id"])) == 3
    # 후보 없이 보내면 일기는 저장된다.
    character.write_diary("하린", "넘치는 날.", paths=paths)
    assert len(_diary_files(paths, saved["id"])) == 4


def test_load_with_diaries_and_memories_stays_small(paths):
    big = _card(
        name="가" * 20, aliases=["나" * 20, "다" * 20, "라" * 20],
        personality=["마" * 40, "바" * 40], speech="사" * 60, emoji="아" * 20,
        call_user="자" * 20, likes=["차" * 20, "카" * 20, "타" * 20, "파" * 20, "하" * 20],
        sample_lines=["거" * 100, "너" * 100, "더" * 100],
    )
    character.save(big, paths=paths)
    name = "가" * 20
    for i in range(30):
        out = character.write_diary(name, "일" * 500, 1, "이" * 100, mood="기" * 20,
                                    core_candidates=["억" * 200], paths=paths)
        character.core(name, "confirm", [out["pending_added"][0]["id"]], paths=paths)
    for _ in range(3):
        character.write_diary(name, "일" * 500, core_candidates=["후" * 200] * 1 + ["보" * 200, "다" * 200],
                              paths=paths)
    out = character.load(name, paths)
    assert len(out["recent_diary"]) == character.LOAD_RECENT_DIARY
    assert len(out["core_memories"]) == character.LOAD_CORE_LIMIT
    assert len(out["pending_memories"]) == 9
    # 모든 칸을 상한까지 채운 최악의 경우 — 2026-10-08 실측 13,272자(일기 5×500,
    # 핵심 기억 20×200, 대기 후보 9×200이 대부분). 설계서 8장 목표("3천 토큰")보다 크지만
    # 상한 값은 초안이라 사람이 정한다. 이 검사는 상한이 말없이 커지는 것을 막는다.
    assert len(json.dumps(out, ensure_ascii=False)) < 14000


def test_guidance_names_only_tools_that_exist():
    import mcp_server  # noqa: F401 — 도구 등록을 위해 불러온다

    text = " ".join(character.GUIDANCE)
    for tool_name in set(re.findall(r"namu_[a-z_]+", text)):
        assert hasattr(mcp_server, tool_name), tool_name
