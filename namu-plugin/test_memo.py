"""memo 그릇(스틱노트) 테스트 — namu-56.

memo는 NAMU에서 유일하게 **지워지는** 그릇이라, 다른 그릇 테스트와 관심사가 다르다.
여기서 지키려는 성질은 셋이다.

1. 떼면 정말 사라진다(tombstone 없음), 그리고 **다른 메모는 살아남는다**.
2. learnings(지식베이스)를 오염시키지 않는다 — 이 그릇이 존재하는 이유 자체다.
3. git 병합에서 union 라인이 **생기지 않는다** — 줄 단위 union을 걸면 한쪽에서
   뗀 메모가 병합 때 되살아나기 때문이다(mutable 게이트, namu-57 3단계에서 예약).
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import memo
import memory_sync


@pytest.fixture
def paths(tmp_path):
    """실제 ~/.namu를 건드리지 않는 격리 경로(namu-33 교훈)."""
    return cfg.DataPaths(
        learnings_yaml=tmp_path / "memory" / "learnings.yaml",
        profile_yaml=tmp_path / "memory" / "profile.yaml",
        db_path=tmp_path / "db" / "namu.db",
        memo_yaml=tmp_path / "memory" / "memo.yaml",
    )


# ---------------------------------------------------------------------------
# ① 붙이기
# ---------------------------------------------------------------------------


def test_add_creates_file_and_returns_id(paths):
    memo_id = memo.add("영화 8시 20분 롯데시네마", paths=paths)

    assert paths.memo_yaml.exists()
    entries = memo.load_all(paths)
    assert len(entries) == 1
    assert entries[0]["id"] == memo_id
    assert entries[0]["text"] == "영화 8시 20분 롯데시네마"
    assert entries[0]["machine"] == cfg.NAMU_MACHINE


def test_add_keeps_insertion_order(paths):
    """붙인 순서(오래된 것 먼저)를 유지한다 — 스틱노트는 붙인 순서로 보는 게 자연스럽다."""
    memo.add("첫째", paths=paths)
    memo.add("둘째", paths=paths)
    memo.add("셋째", paths=paths)

    assert [m["text"] for m in memo.load_all(paths)] == ["첫째", "둘째", "셋째"]


def test_add_rejects_empty_text(paths):
    with pytest.raises(ValueError):
        memo.add("   ", paths=paths)
    assert memo.load_all(paths) == []


def test_add_records_timestamp_in_reference_timezone(paths):
    """기록 시각은 cfg.now() — 웹 컨테이너(UTC)와 노트북이 같은 벽시계를 쓴다
    (namu-57 5단계와 같은 이유. 여기서 datetime.now()를 쓰면 같은 버그를 재발명한다)."""
    memo.add("시각 확인", paths=paths)
    stamped = memo.load_all(paths)[0]["timestamp"]
    assert stamped.startswith(cfg.now().strftime("%Y-%m-%d"))
    assert stamped.endswith("+09:00")


# ---------------------------------------------------------------------------
# ② 떼기 — 이 그릇의 존재 이유
# ---------------------------------------------------------------------------


def test_remove_deletes_only_that_memo(paths):
    memo.add("남을 메모 1", paths=paths)
    target = memo.add("뗄 메모", paths=paths)
    memo.add("남을 메모 2", paths=paths)

    removed = memo.remove(target, paths=paths)

    assert removed["text"] == "뗄 메모"
    assert [m["text"] for m in memo.load_all(paths)] == ["남을 메모 1", "남을 메모 2"]


def test_remove_leaves_no_tombstone_in_file(paths):
    """뗀 자리에 삭제 표식이 남지 않는다 — append-only 그릇과 정반대 성질이라
    파일 내용으로 직접 확인한다(load_all이 걸러줄 수도 있으므로)."""
    target = memo.add("사라질 것", paths=paths)
    memo.add("남을 것", paths=paths)

    memo.remove(target, paths=paths)

    raw = paths.memo_yaml.read_text(encoding="utf-8")
    assert "사라질 것" not in raw
    assert target not in raw
    assert yaml.safe_load(raw) == memo.load_all(paths)


def test_remove_accepts_id_prefix(paths):
    memo_id = memo.add("접두로 뗀다", paths=paths)
    memo.remove(memo_id[:8], paths=paths)
    assert memo.load_all(paths) == []


def test_remove_ambiguous_prefix_deletes_nothing(paths):
    """접두가 여러 장에 걸리면 아무것도 지우지 않는다 — 메모는 복구 수단이
    없으므로(tombstone 없음) 애매하면 멈추는 쪽이 안전하다."""
    memo.add("하나", paths=paths)
    memo.add("둘", paths=paths)
    common = memo.load_all(paths)[0]["id"][:2]

    with pytest.raises(ValueError, match="여러 장"):
        memo.remove(common, paths=paths)

    assert len(memo.load_all(paths)) == 2


def test_short_ids_are_always_removable(paths):
    """브리핑이 보여주는 짧은 id는 **반드시 그대로 떼기에 쓸 수 있어야** 한다.

    실측에서 나온 문제: ULID 앞 10자는 생성 시각이라 같은 밀리초에 붙인 메모끼리
    앞 8자가 같다. 고정 길이로 자르면 화면의 값이 동작하지 않는다.
    """
    for i in range(5):
        memo.add(f"연속 메모 {i}", paths=paths)  # 같은 밀리초에 몰아서 붙인다

    entries = memo.load_all(paths)
    shorts = memo.short_ids(entries)
    assert len(set(shorts.values())) == len(entries)  # 표시값이 서로 다르다

    for full, short in shorts.items():
        removed = memo.remove(short, paths=paths)  # 거절되지 않는다
        assert removed["id"] == full
    assert memo.load_all(paths) == []


def test_short_ids_stay_minimum_length_when_unambiguous(paths):
    """겹치지 않으면 굳이 길게 보여주지 않는다(본문이 묻히지 않게)."""
    memo.add("하나", paths=paths)
    shorts = memo.short_ids(memo.load_all(paths))
    assert all(len(s) == 8 for s in shorts.values())


def test_remove_unknown_id_raises(paths):
    memo.add("하나", paths=paths)
    with pytest.raises(ValueError):
        memo.remove("ZZZZZZZZ", paths=paths)
    assert len(memo.load_all(paths)) == 1


# ---------------------------------------------------------------------------
# ③ 견고성 — 메모가 세션 브리핑을 죽이지 않는다
# ---------------------------------------------------------------------------


def test_load_all_on_missing_file_returns_empty(paths):
    assert memo.load_all(paths) == []


def test_load_all_on_broken_yaml_returns_empty(paths):
    paths.memo_yaml.parent.mkdir(parents=True, exist_ok=True)
    paths.memo_yaml.write_text("[[[ 깨진 yaml", encoding="utf-8")
    assert memo.load_all(paths) == []


def test_write_is_atomic_and_leaves_no_temp_file(paths):
    memo.add("하나", paths=paths)
    memo.add("둘", paths=paths)
    leftovers = list(paths.memo_yaml.parent.glob(".memo-*.tmp"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# ④ 격리 — learnings 오염 0, union 병합 라인 없음
# ---------------------------------------------------------------------------


def test_memo_does_not_touch_learnings_file(paths):
    memo.add("영화 8시 20분", paths=paths)
    assert not paths.learnings_yaml.exists()
    assert not paths.db_path.exists()


def test_memo_generates_no_gitattributes_union_line():
    """mutable 그릇은 union 라인 파생에서 제외된다 — 줄 단위 병합을 걸면
    한쪽 PC에서 뗀 메모가 다른 PC의 파일에 남아 있다가 되살아난다."""
    lines = memory_sync._gitattributes_union_lines()
    # "memo"로 검사하면 `memory/learnings.yaml`의 memo·ry에 걸린다 — 파일명으로 본다.
    assert not any("memo.yaml" in line for line in lines)
    # 다른 그릇은 그대로 있어야 한다(memo 추가가 기존 라인을 건드리지 않았는지).
    assert any("learnings.yaml" in line for line in lines)
    assert any("profile.yaml" in line for line in lines)
