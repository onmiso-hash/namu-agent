"""3층(summary/reason/body) 저장·검색 테스트 (namu-65 구현 3단계).

임시 폴더에 만든 DataPaths만 쓰므로 실제 ~/.namu를 건드리지 않는다.
검색은 두 경로를 모두 확인한다 — 3자 이상은 전문검색(FTS), 미만은 LIKE 폴백이라
한쪽만 고치면 "짧은 검색어로는 안 나온다"가 조용히 남는다.
"""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import db as _db
import memo as _memo
import profile as _profile


@pytest.fixture()
def paths(tmp_path):
    return cfg.DataPaths(
        learnings_yaml=tmp_path / "memory" / "learnings.yaml",
        profile_yaml=tmp_path / "memory" / "profile.yaml",
        db_path=tmp_path / "db" / "namu.db",
        memo_yaml=tmp_path / "memory" / "memo.yaml",
    )


def _docs(paths):
    text = paths.learnings_yaml.read_text(encoding="utf-8")
    return [d for d in yaml.safe_load_all(text) if d]


def test_record_stores_three_layers_in_yaml(paths):
    _db.record(
        "namu-65", "success", "왜 그런가", paths=paths,
        summary="한 줄 요약", body="그때 무슨 일이 있었나",
    )
    doc = _docs(paths)[0]
    assert doc["summary"] == "한 줄 요약"
    assert doc["reason"] == "왜 그런가"
    assert doc["body"] == "그때 무슨 일이 있었나"


def test_record_stores_three_layers_in_cache(paths):
    _db.record("namu-65", "success", "이유", paths=paths,
               summary="요약", body="본문")
    with closing(sqlite3.connect(paths.db_path)) as conn:
        row = conn.execute("SELECT summary, body FROM learnings").fetchone()
    assert row == ("요약", "본문")


def test_old_call_without_layers_still_works(paths):
    # 3층은 입력 경계에서 강제한다 — 저장 계층은 옛 호출을 거절하지 않는다.
    entry_id = _db.record("namu-65", "success", "이유", paths=paths)
    assert entry_id
    doc = _docs(paths)[0]
    assert doc["summary"] is None and doc["body"] is None


@pytest.mark.parametrize("query", ["방화벽설정", "방화"])
def test_search_finds_text_that_lives_only_in_summary(paths, query):
    # 3자 이상(전문검색)과 미만(LIKE 폴백) 두 경로 모두.
    _db.record("작업이름", "success", "이유만 있는 문장", paths=paths,
               summary="방화벽설정을 고쳤다", body="본문")
    with closing(sqlite3.connect(paths.db_path)) as conn:
        result = _db.search(conn, query)
    assert result["results"], f"{query!r}로 summary를 못 찾았다"


@pytest.mark.parametrize("query", ["재현절차", "재현"])
def test_search_finds_text_that_lives_only_in_body(paths, query):
    _db.record("작업이름", "success", "이유", paths=paths,
               summary="요약", body="재현절차는 이렇다")
    with closing(sqlite3.connect(paths.db_path)) as conn:
        result = _db.search(conn, query)
    assert result["results"], f"{query!r}로 body를 못 찾았다"


def test_rebuild_keeps_three_layers(paths):
    _db.record("작업", "success", "이유", paths=paths, summary="요약", body="본문")
    count = _db.rebuild_from_yaml(paths=paths)
    assert count == 1
    with closing(sqlite3.connect(paths.db_path)) as conn:
        row = conn.execute("SELECT summary, body FROM learnings").fetchone()
        # 재생성 뒤에도 검색 색인이 3층을 훑어야 한다(색인은 트리거로 채워진다).
        found = _db.search(conn, "본문")["results"]
    assert row == ("요약", "본문")
    assert found


def test_cache_is_stale_detects_the_new_columns(tmp_path):
    # 옛 설치본(summary/body 없는 db)은 자동으로 낡음 판정 → 재생성된다.
    db_path = tmp_path / "namu.db"
    yaml_path = tmp_path / "learnings.yaml"
    yaml_path.write_text("", encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            "CREATE TABLE learnings ("
            "id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, task TEXT NOT NULL,"
            "task_type TEXT, outcome TEXT, reason TEXT NOT NULL,"
            "machine TEXT, verified_by TEXT, tags TEXT, kind TEXT, via TEXT);"
        )
    assert _db.cache_is_stale(yaml_path, db_path)


# ---------------------------------------------------------------------------
# 개인 사실 — statement/source가 3층으로
# ---------------------------------------------------------------------------

def test_profile_stores_three_layers(paths):
    _profile.record_fact(
        "출력 규칙", paths=paths,
        summary="답변은 짧게", reason="사용자가 직접 말함", body="스크롤백을 못 되짚기 때문",
    )
    doc = _profile.load_all(paths=paths)[0]
    assert (doc["summary"], doc["reason"], doc["body"]) == (
        "답변은 짧게", "사용자가 직접 말함", "스크롤백을 못 되짚기 때문")
    assert "statement" not in doc and "source" not in doc


def test_profile_old_names_are_moved_not_dropped(paths):
    _profile.record_fact("주제", statement="한 줄", source="어떻게 아는가", paths=paths)
    doc = _profile.load_all(paths=paths)[0]
    assert doc["summary"] == "한 줄"
    assert doc["reason"] == "어떻게 아는가"


def test_profile_layers_reads_old_entries():
    old = {"subject": "주제", "statement": "옛 한 줄", "source": "옛 출처"}
    assert _profile.layers(old) == ("옛 한 줄", "옛 출처", "")


def test_profile_reason_is_required(paths):
    with pytest.raises(ValueError):
        _profile.record_fact("주제", summary="한 줄", paths=paths)


# ---------------------------------------------------------------------------
# 쪽지 — text가 3층으로
# ---------------------------------------------------------------------------

def test_memo_stores_three_layers(paths):
    _memo.add(paths=paths, summary="영화 8시 20분", reason="오늘 저녁 약속",
              body="롯데시네마 3관, 예매번호 1234")
    entry = _memo.load_all(paths)[0]
    assert entry["summary"] == "영화 8시 20분"
    assert entry["reason"] == "오늘 저녁 약속"
    assert entry["body"] == "롯데시네마 3관, 예매번호 1234"


def test_memo_old_call_fills_both_summary_and_body(paths):
    # 옛 text는 붙여둔 내용 전부였다 — 화면(요약)과 원문 양쪽을 채워야 종전과 같다.
    _memo.add("영화 8시 20분", paths=paths)
    entry = _memo.load_all(paths)[0]
    assert entry["summary"] == "영화 8시 20분"
    assert entry["body"] == "영화 8시 20분"


def test_memo_layers_reads_old_entries():
    assert _memo.layers({"text": "옛 메모"}) == ("옛 메모", "", "옛 메모")


def test_memo_rejects_empty(paths):
    with pytest.raises(ValueError):
        _memo.add("   ", paths=paths)


def test_select_column_list_matches_row_mapping(paths):
    # SELECT 절과 _COLS가 어긋나면 값이 한 칸씩 밀려 들어간다(예외 없이 조용히).
    _db.record("작업", "failure", "이유", paths=paths, summary="요약", body="본문")
    with closing(sqlite3.connect(paths.db_path)) as conn:
        rows = _db.recall(conn)
    got = rows[0]
    assert got["task"] == "작업"
    assert got["outcome"] == "failure"
    assert got["summary"] == "요약"
    assert got["body"] == "본문"
