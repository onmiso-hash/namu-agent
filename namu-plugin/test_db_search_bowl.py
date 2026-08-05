

def test_search_bowl_memo_profile_read_the_given_paths(tmp_path, monkeypatch):
    """memo/profile 검색이 `paths`가 가리키는 폴더를 읽는지 못 박는다.

    왜: 클라우드는 요청마다 사용자 폴더가 다르다. paths를 안 보고 서버 자신의 홈을
    읽으면 **남의 기억을 돌려준다**. 이 인자가 없던 동안 클라우드는 두 그릇 검색을
    아예 막아 두었고, 그것이 셀프호스팅과의 기능 차이로 남아 있었다(2026-08-05).
    """
    import sqlite3
    import config as cfg
    import db as _db

    paths = cfg.data_paths_for(tmp_path)
    paths.learnings_yaml.parent.mkdir(parents=True, exist_ok=True)
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    _db.init_db(paths=paths)

    import memo as _memo
    import profile as _profile
    _memo.add(summary="임시 쪽지", reason="시험", body="딸기우유", paths=paths)
    _profile.record_fact(subject="시험", statement="딸기우유를 좋아한다",
                         summary="딸기우유", reason="시험", body="딸기우유", paths=paths)

    with sqlite3.connect(paths.db_path) as conn:
        got_memo = _db.search_bowl(conn, bowl="memo", query="딸기우유", paths=paths)
        got_profile = _db.search_bowl(conn, bowl="profile", query="딸기우유", paths=paths)
    assert got_memo["count"] == 1, got_memo
    assert got_profile["count"] == 1, got_profile
