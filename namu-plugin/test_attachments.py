"""첨부 기록 그릇 테스트 (namu-file-upload-download 4단계).

이 그릇의 존재 이유는 "파일 몸통은 각 PC로 안 내려와도 이력은 모든 기기에 있다"이며,
그래서 여기서 지켜야 하는 것은 두 가지다.

1. **크기(bytes)를 반드시 적는다.** 목록 도구가 크기를 저장소에 물으면 git이 크기를
   알아내려고 빠진 파일 몸통을 전부 내려받아 격리가 뚫린다(2026-08-07 실측: 파일
   2,548개에 7분 넘게 안 끝나 중단). 그래서 크기는 이 기록에서만 읽는다.
2. **살아 있는 파일 목록은 계산해서 얻는다.** append-only라 지울 수 없으므로
   status(올림/새 판/지움)를 시간순으로 훑어야 "지금 있는 것"이 나온다.

config.py는 import 시점 부작용이 없어 직접 import한다(test_fields.py와 같은 이유).
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import attachments
import config as cfg
import db


@pytest.fixture()
def paths(tmp_path):
    """사용자 폴더를 tmp로 갈아끼운 DataPaths. 실제 ~/.namu를 건드리지 않는다."""
    return cfg.data_paths_for(tmp_path)


def _search(paths, **kwargs):
    """첨부 기록 검색 한 번. 이 그릇도 SQLite 색인을 타므로 연결이 필요하다.

    fts5-memo-tasks-index 전에는 `conn=None`으로 불렀다 — 그때는 검색이 yaml을
    질의마다 통째로 읽었기 때문이다. 색인 통일(설계서 9장)로 다섯 그릇이 모두
    SQLite를 타면서, 연결 없이 조회되는 것이 더 이상 정상이 아니다.
    """
    import sqlite3
    from contextlib import closing

    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(paths.db_path)) as conn:
        return db.search_bowl(conn, bowl="attachments", paths=paths, **kwargs)


def _record(paths, **kwargs):
    base = dict(
        path=f"{cfg.ATTACH_DIR_NAME}/설계.pdf",
        bytes_=284915,
        status=attachments.STATUS_UPLOADED,
        summary="설계 문서",
        reason="대화가 끝나면 사라지므로 파일째 남긴다",
        body="원문",
        paths=paths,
    )
    base.update(kwargs)
    return attachments.record_attachment(**base)


# ---------------------------------------------------------------------------
# 저장 형식
# ---------------------------------------------------------------------------

def test_record_writes_an_appended_yaml_document(paths):
    entry_id = _record(paths)

    docs = list(yaml.safe_load_all(paths.attachments_yaml.read_text(encoding="utf-8")))
    assert len(docs) == 1
    assert docs[0]["id"] == entry_id
    assert docs[0]["path"] == f"{cfg.ATTACH_DIR_NAME}/설계.pdf"
    assert docs[0]["bytes"] == 284915
    assert docs[0]["status"] == "올림"


def test_record_is_append_only(paths):
    first = _record(paths)
    second = _record(paths, status=attachments.STATUS_REVISED, bytes_=331408,
                     supersedes=first)

    entries = attachments.load_all(paths)
    assert [e["id"] for e in entries] == [first, second]
    # 옛 기록이 남아 있어야 "이 문서를 언제부터 몇 번 고쳤나"를 볼 수 있다.
    assert entries[1]["supersedes"] == first
    assert entries[0]["bytes"] == 284915


def test_topic_is_stored_as_task_like_the_other_bowls(paths):
    _record(paths, topic="fts5-memo-tasks-index", project="namu-agent")
    entry = attachments.load_all(paths)[0]
    # 입력 이름은 topic이지만 저장 키는 교훈 그릇과 같은 task다 — 읽는 쪽이
    # 그릇마다 다른 키를 알아야 하면 화면이 그릇 수만큼 갈라진다.
    assert entry["task"] == "fts5-memo-tasks-index"
    assert entry["project"] == "namu-agent"


def test_load_all_is_empty_when_the_file_does_not_exist(paths):
    assert attachments.load_all(paths) == []


def test_broken_yaml_returns_empty_instead_of_raising(paths):
    paths.attachments_yaml.parent.mkdir(parents=True, exist_ok=True)
    paths.attachments_yaml.write_text("--- {망가진: [", encoding="utf-8")
    # 한 항목이 깨졌다고 recall 전체가 실패하면 손해가 훨씬 크다(memo와 같은 판단).
    assert attachments.load_all(paths) == []


# ---------------------------------------------------------------------------
# 입력 거절 — 크기 칸이 이 그릇의 급소다
# ---------------------------------------------------------------------------

def test_bytes_must_be_an_integer(paths):
    with pytest.raises(ValueError, match="bytes"):
        _record(paths, bytes_="큼")


def test_bytes_cannot_be_negative(paths):
    with pytest.raises(ValueError, match="bytes"):
        _record(paths, bytes_=-1)


def test_zero_bytes_is_allowed(paths):
    # 빈 파일도 올릴 수 있어야 한다 — 0을 거절하면 "크기가 없다"와 "크기가 0"을
    # 구분하지 못해 목록에서 그 파일이 사라진다.
    _record(paths, bytes_=0)
    assert attachments.current_files(paths)[0]["bytes"] == 0


def test_path_is_required(paths):
    with pytest.raises(ValueError, match="path"):
        _record(paths, path="   ")


def test_status_outside_the_three_is_rejected(paths):
    with pytest.raises(ValueError, match="status"):
        _record(paths, status="삭제")


def test_status_vocabulary_matches_the_field_declaration():
    # 입력 검증(config.FIELDS)과 계산(attachments)이 갈라지면 "저장은 되는데 목록에
    # 안 잡히는" 값이 생긴다.
    assert attachments.VALID_STATUSES == cfg.allowed_values("status", "attachments")


# ---------------------------------------------------------------------------
# 살아 있는 파일 목록 — 계산으로 얻는다
# ---------------------------------------------------------------------------

def test_current_files_keeps_only_the_latest_record_per_path(paths):
    _record(paths, bytes_=100)
    _record(paths, bytes_=200, status=attachments.STATUS_REVISED)

    alive = attachments.current_files(paths)
    assert len(alive) == 1
    assert alive[0]["bytes"] == 200


def test_current_files_drops_removed_paths_but_history_keeps_them(paths):
    _record(paths)
    _record(paths, status=attachments.STATUS_REMOVED, reason="더 이상 안 쓴다")

    assert attachments.current_files(paths) == []
    # "그 자료 어디 갔지?"에 "언제 뺐고 이유는 이것"이라고 답할 수 있어야 한다.
    history = attachments.history(f"{cfg.ATTACH_DIR_NAME}/설계.pdf", paths=paths)
    assert [e["status"] for e in history] == ["올림", "지움"]
    assert history[-1]["reason"] == "더 이상 안 쓴다"


def test_a_path_uploaded_again_after_removal_comes_back(paths):
    _record(paths)
    _record(paths, status=attachments.STATUS_REMOVED)
    _record(paths, bytes_=500)

    alive = attachments.current_files(paths)
    assert [e["bytes"] for e in alive] == [500]


def test_current_files_lists_the_newest_first(paths):
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/먼저.pdf")
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/나중.pdf")

    names = [e["path"] for e in attachments.current_files(paths)]
    assert names == [f"{cfg.ATTACH_DIR_NAME}/나중.pdf", f"{cfg.ATTACH_DIR_NAME}/먼저.pdf"]


# ---------------------------------------------------------------------------
# 조회 — search_bowl 분기
# ---------------------------------------------------------------------------

def test_search_bowl_reads_attachments(paths):
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/검색설계.pdf", topic="fts5")
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/발표자료.pdf", topic="namu-70")

    result = _search(paths, query="검색설계")
    assert result["bowl"] == "attachments"
    assert result["count"] == 1
    # 파일 이름으로 찾을 수 있어야 한다 — 다시 꺼낼 때 사람이 기억하는 것은
    # 대개 내용 설명이 아니라 파일 이름이다.
    assert result["results"][0]["path"].endswith("검색설계.pdf")


def test_search_bowl_filters_attachments_by_project(paths):
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/a.pdf", project="namu-agent")
    _record(paths, path=f"{cfg.ATTACH_DIR_NAME}/b.pdf", project="다른방")

    result = _search(paths, project="namu-agent")
    assert [e["path"] for e in result["results"]] == [f"{cfg.ATTACH_DIR_NAME}/a.pdf"]


def test_search_bowl_still_rejects_project_on_learnings():
    # project는 tasks·attachments 전용 축이다 — 조용히 무시하면 웹 AI가 필터가
    # 걸린 줄 알고 잘못된 결론을 낸다.
    with pytest.raises(ValueError, match="project"):
        db.search_bowl(None, bowl="learnings", project="namu-agent")


def test_attachments_are_indexed_in_sqlite(paths):
    """이 그릇도 SQLite 색인을 탄다(fts5-memo-tasks-index, 설계서 9장).

    namu-file-upload-download는 색인 여부를 자기 범위 밖으로 미뤄 `cached=False`로
    두었고, 그때 이 자리에는 "연결 없이 조회되는 것이 색인을 타지 않는다는 증거"라는
    반대 방향의 시험이 있었다. 그 미결을 검색 통일 작업이 넘겨받아 뒤집었다.

    색인 표에 행이 실제로 들어갔는지까지 본다 — 검색 결과만 보면 색인을 타든 파일을
    읽든 구분이 안 되기 때문이다.
    """
    import sqlite3
    from contextlib import closing

    _record(paths)
    assert _search(paths)["count"] == 1

    with closing(sqlite3.connect(paths.db_path)) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM bowl_attachments").fetchone()[0]
    assert rows == 1


# ---------------------------------------------------------------------------
# 사용자별 폴더 — 클라우드에서 남의 이력을 읽으면 안 된다
# ---------------------------------------------------------------------------

def test_paths_argument_isolates_users(tmp_path):
    mine = cfg.data_paths_for(tmp_path / "나")
    yours = cfg.data_paths_for(tmp_path / "남")

    _record(mine, path=f"{cfg.ATTACH_DIR_NAME}/내파일.pdf")

    assert attachments.load_all(yours) == []
    assert len(attachments.load_all(mine)) == 1
