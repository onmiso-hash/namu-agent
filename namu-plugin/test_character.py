"""캐릭터 그릇(나무 캐릭터 v0.1 1~3단계) — 스키마·카드 검사·저장·목록·불러오기·일기·핵심 기억·원문 보관·잊기."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import attachments  # noqa: E402
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


# ── 대표사진·감정별 사진 ──────────────────────────────────────────────────────
def _attach(paths, path="attach_file/portrait.png"):
    attachments.record_attachment(path, 100, attachments.STATUS_UPLOADED, "사진", "등록", "생략",
                                   paths=paths)
    return path


def test_portrait_and_emotion_photos_default_to_empty(paths):
    clean = character.normalize_card(_card(), paths)
    assert clean["portrait"] is None
    assert clean["emotion_photos"] == {}


def test_portrait_with_existing_attachment_round_trips(paths):
    path = _attach(paths)
    r = character.save(_card(portrait=path), paths=paths)
    out = character.load("하린", paths)
    assert out["card"]["portrait"] == path


def test_portrait_with_unknown_path_is_rejected(paths):
    with pytest.raises(ValueError, match="그런 첨부 파일이 없습니다"):
        character.normalize_card(_card(portrait="attach_file/nope.png"), paths)


def test_emotion_photos_with_existing_attachments_round_trip(paths):
    happy = _attach(paths, "attach_file/happy.png")
    sad = _attach(paths, "attach_file/sad.png")
    character.save(_card(emotion_photos={"기쁨": happy, "슬픔": sad}), paths=paths)
    out = character.load("하린", paths)
    assert out["card"]["emotion_photos"] == {"기쁨": happy, "슬픔": sad}


def test_emotion_photos_with_one_unknown_path_is_rejected(paths):
    happy = _attach(paths, "attach_file/happy.png")
    with pytest.raises(ValueError, match="그런 첨부 파일이 없습니다"):
        character.normalize_card(
            _card(emotion_photos={"기쁨": happy, "슬픔": "attach_file/nope.png"}), paths
        )


def test_emotion_photos_over_the_item_limit_is_rejected(paths):
    photos = {}
    for i in range(character.PHOTO_EMOTION_MAX + 1):
        p = _attach(paths, f"attach_file/e{i}.png")
        photos[f"감정{i}"] = p
    with pytest.raises(ValueError, match=f"{character.PHOTO_EMOTION_MAX}개까지"):
        character.normalize_card(_card(emotion_photos=photos), paths)


def test_emotion_photos_label_over_the_length_limit_is_rejected(paths):
    path = _attach(paths)
    label = "감" * (character.PHOTO_EMOTION_LABEL_MAX + 1)
    with pytest.raises(ValueError, match=f"{character.PHOTO_EMOTION_LABEL_MAX}자까지"):
        character.normalize_card(_card(emotion_photos={label: path}), paths)


def test_emotion_photos_duplicate_label_after_whitespace_is_rejected(paths):
    x = _attach(paths, "attach_file/x.png")
    y = _attach(paths, "attach_file/y.png")
    # 공백만 다른 이름 — 정리하면 같은 이름이라 뒤엣것이 앞엣것을 말없이 덮으면 안 된다.
    with pytest.raises(ValueError, match="겹칩니다"):
        character.normalize_card(_card(emotion_photos={"기  쁨": x, "기 쁨": y}), paths)
    # 대소문자만 다른 이름도 같은 이름이다.
    with pytest.raises(ValueError, match="겹칩니다"):
        character.normalize_card(_card(emotion_photos={"Happy": x, "happy": y}), paths)


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
    assert doc["topics"] == ["회사", "산책"] and "archived" not in doc
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
    # 모든 칸을 상한까지 채운 최악의 경우 — 2026-10-08 1차 실측 13,272자(일기 5×500,
    # 핵심 기억 20×200, 대기 후보 9×200)가 설계서 8장 목표("3천 토큰")보다 커서 허니와
    # 상한을 다시 정했다(일기 5→3개, 핵심 기억 20→10개). 재측정 9,590자. 이 검사는 상한이
    # 말없이 다시 커지는 것을 막는다.
    # 같은 날 화면용 글(display)과 읽는 시각(when)을 더해 11,346자가 됐다(display 958자 —
    # 일기 요약·핵심 기억을 줄여 싣는다). 원래 기록 칸을 줄이지 않고 상한을 올렸다.
    assert len(json.dumps(out, ensure_ascii=False)) < 12000


def test_guidance_names_only_tools_that_exist():
    import mcp_server  # noqa: F401 — 도구 등록을 위해 불러온다

    text = " ".join(character.GUIDANCE)
    for tool_name in set(re.findall(r"namu_[a-z_]+", text)):
        assert hasattr(mcp_server, tool_name), tool_name


# ── 3단계: 원문 보관 ─────────────────────────────────────────────────────────
def _char_dir(paths, name="하린"):
    return paths.character_dir / character.find(name, paths)["character_id"]


def test_archive_is_kept_as_given_and_linked(paths):
    character.save(_card(), paths=paths)
    text = "허니: 안녕\n하린:  반가워\n\n(끝)"
    out = character.write_diary("하린", "인사를 나눴다.", archive=text, paths=paths)
    assert out["archived"] is True
    assert out["archive"]["part"] == 1 and out["archive"]["chars"] == len(text)
    d = _char_dir(paths)
    [archive] = character._read_entries(d / "archive")
    assert archive["text"] == text  # 줄바꿈·띄어쓰기를 다듬지 않는다
    assert archive["diary_id"] == out["id"] and archive["part"] == 1 and archive["at"]
    # 원문이 있는지는 일기에 적지 않고 원문 폴더에서 센다.
    [diary] = character._read_entries(d / "diary")
    assert "archived" not in diary and "archive_id" not in diary
    assert character.load("하린", paths)["recent_diary"][0]["archive_parts"] == 1


def test_no_archive_unless_sent(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "인사를 나눴다.", archive="   ", paths=paths)
    assert out["archived"] is False
    assert not (_char_dir(paths) / "archive").exists()


def test_oversize_archive_still_saves_the_diary(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "길었다.", 2, "오래 얘기함",
                                archive="가" * (character.ARCHIVE_TEXT_MAX + 1), paths=paths)
    # 대화가 있었다는 기록은 원문 크기 때문에 사라지지 않는다. 원문만 돌려보낸다.
    assert out["archived"] is False and out["archive"] is None
    assert "append_to" in out["archive_rejected"]
    assert out["relationship"]["affection"] == 12
    d = _char_dir(paths)
    assert len(character._read_entries(d / "diary")) == 1
    assert not (d / "archive").exists()
    # 거절된 원문은 그 일기에 첫 조각부터 이어 붙일 수 있다.
    piece = character.write_diary("하린", archive="가" * 10, append_to=out["id"], paths=paths)
    assert piece["archive"]["part"] == 1 and piece["archive_parts"] == 1


def test_archive_pieces_are_numbered_and_count_affection_once(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "긴 대화를 했다.", 3, "속 얘기", archive="첫 조각",
                                paths=paths)
    two = character.write_diary("하린", archive="둘째 조각", append_to=out["id"], paths=paths)
    three = character.write_diary("하린", archive="셋째 조각", append_to=out["id"], paths=paths)
    assert two["appended"] is True and two["id"] == out["id"]
    assert (two["archive"]["part"], three["archive"]["part"]) == (2, 3)
    assert three["archive_parts"] == 3
    assert three["archive_chars"] == len("첫 조각") + len("둘째 조각") + len("셋째 조각")
    d = _char_dir(paths)
    parts = character._archive_parts(d)[out["id"]]
    assert [p["text"] for p in parts] == ["첫 조각", "둘째 조각", "셋째 조각"]
    assert all(p["at"] for p in parts)  # 조각마다 받은 시각이 붙는다
    # 일기는 한 편 그대로 — 호감도는 한 번만 센다.
    assert len(character._read_entries(d / "diary")) == 1
    loaded = character.load("하린", paths)
    assert loaded["relationship"]["affection"] == 13
    assert loaded["recent_diary"][0]["archive_parts"] == 3


def test_append_takes_only_the_archive(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "인사를 나눴다.", paths=paths)
    with pytest.raises(ValueError, match="summary"):
        character.write_diary("하린", "또 요약", archive="조각", append_to=out["id"], paths=paths)
    with pytest.raises(ValueError, match="affection_delta"):
        character.write_diary("하린", affection_delta=2, archive="조각", append_to=out["id"],
                              paths=paths)
    with pytest.raises(ValueError, match="archive"):
        character.write_diary("하린", append_to=out["id"], paths=paths)
    with pytest.raises(ValueError, match="일기가 없습니다"):
        character.write_diary("하린", archive="조각", append_to="01" + "A" * 24, paths=paths)
    with pytest.raises(ValueError, match="저장하지 않았습니다"):
        character.write_diary("하린", archive="가" * (character.ARCHIVE_TEXT_MAX + 1),
                              append_to=out["id"], paths=paths)
    assert not (_char_dir(paths) / "archive").exists()


def test_archive_pieces_have_a_limit(paths, monkeypatch):
    monkeypatch.setattr(character, "ARCHIVE_PARTS_MAX", 2)
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "인사", archive="1", paths=paths)
    character.write_diary("하린", archive="2", append_to=out["id"], paths=paths)
    with pytest.raises(ValueError, match="2개까지"):
        character.write_diary("하린", archive="3", append_to=out["id"], paths=paths)


# ── 3단계: 잊기 ─────────────────────────────────────────────────────────────
def _two_diaries(paths):
    character.save(_card(), paths=paths)
    a = character.write_diary("하린", "산책 얘기를 했다.", 5, "산책 약속", archive="원문 A",
                              core_candidates=["첫 산책 약속", "좋아하는 노래"], paths=paths)
    character.core("하린", "confirm", [a["pending_added"][0]["id"]], paths=paths)
    b = character.write_diary("하린", "영화 얘기를 했다.", 2, "영화 추천", paths=paths)
    return a, b


def test_forget_lists_choices_without_deleting(paths):
    a, b = _two_diaries(paths)
    out = character.forget("하린", "diary", paths=paths)
    assert out["step"] == "choose"
    assert [e["id"] for e in out["entries"]] == [b["id"], a["id"]]  # 최근 순
    assert out["entries"][1]["archive_parts"] == 1
    assert out["entries"][1]["when"].endswith("오늘")
    found = character.forget("하린", "diary", query="산책", paths=paths)
    assert [e["id"] for e in found["entries"]] == [a["id"]]
    assert len(character._read_entries(_char_dir(paths) / "diary")) == 2


def test_forget_diary_takes_what_came_from_it(paths):
    a, b = _two_diaries(paths)
    d = _char_dir(paths)
    preview = character.forget("하린", "diary", [a["id"]], paths=paths)
    assert preview["step"] == "preview"
    will = preview["will_delete"]
    assert [x["id"] for x in will["diary"]] == [a["id"]]
    assert len(will["archive"]) == 1 and len(will["core"]) == 1 and len(will["pending"]) == 1
    assert preview["notice"] == character.HISTORY_NOTICE
    # 미리 보기만으로는 아무것도 지우지 않는다. 지운 뒤의 관계를 미리 보여 준다.
    assert len(character._read_entries(d / "diary")) == 2
    assert preview["relationship_after"]["affection"] == 10 + 2

    done = character.forget("하린", "diary", [a["id"]], confirm=preview["confirm"], paths=paths)
    assert done["step"] == "done"
    assert done["deleted"] == {"diary": 1, "archive": 1, "pending": 1, "core": 1}
    assert done["relationship"]["affection"] == 12
    for sub in ("archive", "pending", "core"):
        assert character._read_entries(d / sub) == []
    [left] = character._read_entries(d / "diary")
    assert left["id"] == b["id"]
    loaded = character.load("하린", paths)
    assert loaded["relationship"]["affection"] == 12
    assert [x["id"] for x in loaded["recent_diary"]] == [b["id"]]
    assert loaded["core_memories"] == [] and loaded["pending_memories"] == []


def test_forget_core_only(paths):
    a, _ = _two_diaries(paths)
    d = _char_dir(paths)
    [mem] = character._read_entries(d / "core")
    preview = character.forget("하린", "core", [mem["id"]], paths=paths)
    assert set(preview["will_delete"]) == {"core"}
    character.forget("하린", "core", [mem["id"]], confirm=preview["confirm"], paths=paths)
    assert character._read_entries(d / "core") == []
    assert len(character._read_entries(d / "diary")) == 2
    assert len(character._read_entries(d / "archive")) == 1


def test_forget_archive_keeps_the_diary(paths):
    a, _ = _two_diaries(paths)
    d = _char_dir(paths)
    [arc] = character._read_entries(d / "archive")
    preview = character.forget("하린", "archive", [arc["id"]], paths=paths)
    character.forget("하린", "archive", [arc["id"]], confirm=preview["confirm"], paths=paths)
    assert character._read_entries(d / "archive") == []
    diary = next(x for x in character._read_entries(d / "diary") if x["id"] == a["id"])
    assert diary["summary"] == "산책 얘기를 했다."
    loaded = character.load("하린", paths)
    assert [x["archive_parts"] for x in loaded["recent_diary"]] == [0, 0]


def test_forget_one_piece_keeps_the_others_and_diary_takes_all(paths):
    a, _ = _two_diaries(paths)
    d = _char_dir(paths)
    character.write_diary("하린", archive="원문 B", append_to=a["id"], paths=paths)
    first, second = character._archive_parts(d)[a["id"]]
    rows = character.forget("하린", "archive", paths=paths)["entries"]
    assert [r["part"] for r in rows] == [2, 1]
    preview = character.forget("하린", "archive", [first["id"]], paths=paths)
    character.forget("하린", "archive", [first["id"]], confirm=preview["confirm"], paths=paths)
    assert [p["id"] for p in character._archive_parts(d)[a["id"]]] == [second["id"]]
    # 남은 조각까지 일기를 잊으면 함께 지워진다.
    character.write_diary("하린", archive="원문 C", append_to=a["id"], paths=paths)
    preview = character.forget("하린", "diary", [a["id"]], paths=paths)
    assert len(preview["will_delete"]["archive"]) == 2
    character.forget("하린", "diary", [a["id"]], confirm=preview["confirm"], paths=paths)
    assert character._read_entries(d / "archive") == []


# ── 사람이 읽는 시각·화면용 글 ─────────────────────────────────────────────────
@pytest.mark.parametrize("at,label", [
    ("2026-10-08T19:57:57+09:00", "10월 8일(목) 저녁 7시 57분 · 오늘"),
    ("2026-10-07T00:30:00+09:00", "10월 7일(수) 새벽 12시 30분 · 어제"),
    ("2026-10-05T07:00:00+09:00", "10월 5일(월) 아침 7시 · 3일 전"),
    ("2026-10-05T12:05:00+09:00", "10월 5일(월) 낮 12시 5분 · 3일 전"),
    ("2026-10-05T15:00:00+09:00", "10월 5일(월) 오후 3시 · 3일 전"),
    ("2026-10-08T10:57:57+00:00", "10월 8일(목) 저녁 7시 57분 · 오늘"),  # 세계표준시로 받아도
    ("2025-12-31T23:00:00+09:00", "2025년 12월 31일(수) 밤 11시 · 281일 전"),
])
def test_when_reads_like_a_person(at, label):
    now = character.datetime.fromisoformat("2026-10-08T21:00:00+09:00")
    assert character._when(at, now) == label
    assert character._when(None, now) is None and character._when("엉터리", now) is None


def test_display_is_a_quote_box_with_dates(paths):
    character.save(_card(), paths=paths)
    out = character.write_diary("하린", "산책 얘기를 했다.\n# 줄바꿈", 3, "산책 약속",
                                mood="설렘", core_candidates=["첫 산책은 한강"], paths=paths)
    character.core("하린", "confirm", [out["pending_added"][0]["id"]], paths=paths)
    loaded = character.load("하린", paths)
    shown = loaded["display"]
    assert all(line.startswith(">") for line in shown.splitlines())
    assert "**🌸 하린**" in shown and "호감도 13/100" in shown
    assert f"**{out['when']}** (설렘)" in shown
    assert "산책 얘기를 했다. # 줄바꿈" in shown and "첫 산책은 한강" in shown
    assert loaded["relationship"]["last_talk_when"] == out["when"]
    assert any("display" in g for g in loaded["guidance"])
    assert character.list_all(paths)[0]["last_talk_when"] == out["when"]


def test_display_shortens_what_the_data_keeps_whole(paths):
    character.save(_card(), paths=paths)
    for i in range(7):
        out = character.write_diary("하린", "일" * 300, core_candidates=[f"{i}" + "억" * 100],
                                    paths=paths)
        character.core("하린", "confirm", [out["pending_added"][0]["id"]], paths=paths)
    loaded = character.load("하린", paths)
    shown = loaded["display"]
    assert "일" * 120 + "…" in shown and "일" * 121 not in shown
    assert "> - 외 2개" in shown and "> - 6" in shown and "> - 1" not in shown
    assert loaded["recent_diary"][0]["summary"] == "일" * 300


def test_forget_needs_the_matching_confirm(paths):
    a, b = _two_diaries(paths)
    d = _char_dir(paths)
    preview = character.forget("하린", "diary", [a["id"]], paths=paths)
    with pytest.raises(ValueError, match="확인표"):
        character.forget("하린", "diary", [b["id"]], confirm=preview["confirm"], paths=paths)
    # 미리 보기 뒤 그 일기에서 나온 것이 바뀌면 옛 확인표로는 지우지 못한다.
    pend = character._read_entries(d / "pending")[0]
    character.core("하린", "confirm", [pend["id"]], paths=paths)
    with pytest.raises(ValueError, match="확인표"):
        character.forget("하린", "diary", [a["id"]], confirm=preview["confirm"], paths=paths)
    assert len(character._read_entries(d / "diary")) == 2


def test_forget_rejects_unknown_ids_and_targets(paths):
    _two_diaries(paths)
    with pytest.raises(ValueError, match="아무것도 지우지"):
        character.forget("하린", "diary", ["01M4DDG0AD7DV5V37Y8DQFCEEG"], paths=paths)
    with pytest.raises(ValueError, match="target"):
        character.forget("하린", "pending", paths=paths)
    with pytest.raises(ValueError, match="id 모양"):
        character.forget("하린", "diary", ["산책"], paths=paths)
    with pytest.raises(ValueError, match="ids"):
        character.forget("하린", "diary", confirm="abc", paths=paths)


def test_forget_whole_character(paths):
    _two_diaries(paths)
    character.save(_card(name="다른 아이", aliases=[]), paths=paths)
    d = _char_dir(paths)
    with pytest.raises(ValueError, match="ids"):
        character.forget("하린", "character", ["01M4DDG0AD7DV5V37Y8DQFCEEG"], paths=paths)
    preview = character.forget("린아", "character", paths=paths)
    assert preview["will_delete"]["character"] == "하린"
    assert preview["will_delete"]["diary"] == 2 and preview["will_delete"]["archive"] == 1
    assert d.exists()
    done = character.forget("린아", "character", confirm=preview["confirm"], paths=paths)
    assert done["step"] == "done" and done["deleted"]["card_versions"] == 1
    assert not d.exists()
    assert [c["name"] for c in character.list_all(paths)] == ["다른 아이"]
    # 이름과 별명이 다시 비어 새 캐릭터가 쓸 수 있다.
    character.save(_card(), paths=paths)
