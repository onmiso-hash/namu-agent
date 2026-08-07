"""그릇 검색 색인 테스트 (fts5-memo-tasks-index — docs/search_index_unify.md).

이 작업이 지켜야 하는 것은 넷이다.

1. **색인은 사본이다.** 원본 파일이 진실이고, 색인은 지워도 다시 만들어져야 한다
   (개발 원칙 2). 그래서 결과가 옛 경로와 **글자 그대로** 같아야 한다.
2. **두 글자 검색이 살아 있어야 한다.** trigram 색인은 세 글자씩 겹쳐 잘라 담으므로
   두 글자는 원리상 0건이 된다. 우리말 기술용어는 두 글자가 가장 흔해서(설계·검색·
   기억·작업) 우회가 없으면 검색 품질이 색인 도입으로 **나빠진다**.
3. **원본이 바뀌면 색인도 따라와야 한다.** 특히 쪽지는 유일하게 항목이 사라지는
   그릇이라, 뗀 메모가 색인에 남아 있으면 없는 것이 검색된다.
4. **첨부 기록의 색인은 저장소를 건드리지 않는다.** 파일 목록이나 크기를 저장소에
   물으면 git이 빠진 몸통을 전부 내려받아 격리가 되돌릴 수 없이 뚫린다
   (2026-08-07 실측: 파일 2,548개에 7분 넘게 안 끝나 중단).
"""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import attachments as _attachments  # noqa: E402
import config as cfg  # noqa: E402
import db as _db  # noqa: E402
import memo as _memo  # noqa: E402
import profile as _profile  # noqa: E402
import task_resolve  # noqa: E402


@pytest.fixture()
def paths(tmp_path):
    """사용자 폴더를 tmp로 갈아끼운 DataPaths. 실제 ~/.namu를 건드리지 않는다."""
    p = cfg.data_paths_for(tmp_path)
    p.db_path.parent.mkdir(parents=True, exist_ok=True)
    p.learnings_yaml.parent.mkdir(parents=True, exist_ok=True)
    return p


def search(paths, bowl, **kwargs):
    with closing(sqlite3.connect(paths.db_path)) as conn:
        return _db.search_bowl(conn, bowl=bowl, paths=paths, **kwargs)


def rows_in(paths, bowl):
    with closing(sqlite3.connect(paths.db_path)) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {_db._bowl_table(bowl)}").fetchone()[0]


# ---------------------------------------------------------------------------
# 색인은 사본 — 지워도 다시 만들어지고, 원본은 손대지 않는다
# ---------------------------------------------------------------------------

def test_index_is_a_rebuildable_copy(paths):
    _memo.add(summary="딸기우유", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="딸기우유")["count"] == 1

    # 색인 표를 통째로 지워도 다음 검색에서 다시 만들어진다.
    with closing(sqlite3.connect(paths.db_path)) as conn:
        conn.executescript("DROP TABLE bowl_memo_fts; DROP TABLE bowl_memo;")
    assert search(paths, "memo", query="딸기우유")["count"] == 1

    # 원본 파일은 그대로다 — 색인이 원본을 고치지 않는다.
    assert len(_memo.load_all(paths)) == 1


def test_results_are_the_original_records_unchanged(paths):
    _profile.record_fact(subject="시험", statement="딸기우유를 좋아한다",
                         summary="딸기우유", reason="시험", body="원문", paths=paths)
    got = search(paths, "profile", query="딸기우유")["results"][0]
    original = _profile.active(paths=paths)[0]
    assert got == original


# ---------------------------------------------------------------------------
# 두 글자 우회 — 없으면 색인 도입이 곧 검색 퇴행이다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["설계", "검색", "기억"])
def test_two_letter_query_still_finds(paths, query):
    _memo.add(summary=f"{query} 문서", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query=query)["count"] == 1


def test_two_letter_query_matches_inside_a_word(paths):
    """조사·어미가 붙어도 걸린다 — 옛 경로(파이썬 부분일치)와 같은 성질."""
    _memo.add(summary="재생성되는 캐시로 취급", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="생성")["count"] == 1


# ---------------------------------------------------------------------------
# 낱말 AND — 띄어 쓴 낱말은 순서와 무관해야 한다
# ---------------------------------------------------------------------------

def test_multi_word_query_ignores_word_order(paths):
    _memo.add(summary="검색 인덱스 설계 문서", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="설계 문서")["count"] == 1
    assert search(paths, "memo", query="문서 설계")["count"] == 1


def test_multi_word_query_requires_all_words(paths):
    _memo.add(summary="검색 인덱스", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="검색 인덱스")["count"] == 1
    assert search(paths, "memo", query="검색 첨부")["count"] == 0


def test_multi_word_query_works_across_layers(paths):
    """요약에 있는 낱말과 원문에 있는 낱말을 함께 줘도 걸린다(3층 전부가 검색 대상)."""
    _memo.add(summary="첫째줄", reason="둘째줄", body="셋째줄", paths=paths)
    assert search(paths, "memo", query="첫째줄 셋째줄")["count"] == 1


def test_word_order_is_irrelevant_on_both_paths(paths):
    """긴 낱말만 준 질의(색인 경로)와 짧은 낱말이 섞인 질의(LIKE 경로) **양쪽** 모두.

    두 경로가 따로 있으므로 한쪽만 고치면 나머지에서 같은 결함이 남는다.
    """
    _memo.add(summary="인덱스 재생성 설계", reason="시험", body="원문", paths=paths)

    assert _db._use_index(["인덱스", "재생성"]) is True
    assert search(paths, "memo", query="인덱스 재생성")["count"] == 1
    assert search(paths, "memo", query="재생성 인덱스")["count"] == 1

    assert _db._use_index(["설계", "인덱스"]) is False
    assert search(paths, "memo", query="설계 인덱스")["count"] == 1
    assert search(paths, "memo", query="인덱스 설계")["count"] == 1


# ---------------------------------------------------------------------------
# 원본이 바뀌면 색인도 따라온다
# ---------------------------------------------------------------------------

def test_new_record_is_searchable_immediately(paths):
    _memo.add(summary="첫 메모", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="첫 메모")["count"] == 1

    _memo.add(summary="둘째 메모", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo", query="둘째 메모")["count"] == 1


def test_removed_memo_disappears_from_the_index(paths):
    """쪽지는 유일하게 **떼면 사라지는** 그릇이다.

    건수 비교만으로 낡음을 판정하면 "건수가 같은 채 내용만 바뀐" 경우를 못 잡는데,
    없는 메모가 검색되는 것은 있는 메모가 안 나오는 것보다 더 나쁘다.
    """
    kept = _memo.add(summary="남길 메모", reason="시험", body="원문", paths=paths)
    doomed = _memo.add(summary="뗄 메모", reason="시험", body="원문", paths=paths)
    assert search(paths, "memo")["count"] == 2

    _memo.remove(doomed, paths=paths)
    assert search(paths, "memo", query="뗄 메모")["count"] == 0
    assert [m["id"] for m in search(paths, "memo")["results"]] == [kept]


def test_superseded_fact_leaves_the_index(paths):
    old_id = _profile.record_fact(subject="시험", statement="옛 사실",
                                  summary="옛 사실", reason="시험", body="원문",
                                  paths=paths)
    _profile.record_fact(subject="시험", statement="새 사실",
                         summary="새 사실", reason="시험", body="원문",
                         supersedes=old_id, paths=paths)
    ids = [d["id"] for d in search(paths, "profile")["results"]]
    assert old_id not in ids


# ---------------------------------------------------------------------------
# 첨부 기록 — 파일 이름으로 찾고, 지운 파일의 기록도 남는다
# ---------------------------------------------------------------------------

def _attach(paths, path, status=_attachments.STATUS_UPLOADED, **kw):
    return _attachments.record_attachment(
        path=path, bytes_=kw.pop("bytes_", 1234), status=status,
        summary=kw.pop("summary", "요약"), reason=kw.pop("reason", "이유"),
        body=kw.pop("body", "원문"), paths=paths, **kw,
    )


def test_attachment_is_found_by_file_name(paths):
    _attach(paths, f"{cfg.ATTACH_DIR_NAME}/검색인덱스설계.pdf")
    _attach(paths, f"{cfg.ATTACH_DIR_NAME}/발표자료.pdf")
    got = search(paths, "attachments", query="검색인덱스설계")
    assert got["count"] == 1
    assert got["results"][0]["path"].endswith("검색인덱스설계.pdf")


def test_removed_attachment_history_stays_searchable(paths):
    """지운 파일의 기록과 그 이유는 검색에서 사라지면 안 된다(설계서 9.4 ②).

    색인 행의 단위가 "파일"이 아니라 "기록"이어야 하는 이유다 — 최신 한 줄만 담으면
    "그 자료 어디 갔지"에 답할 수 없게 된다.
    """
    name = f"{cfg.ATTACH_DIR_NAME}/한물간자료.pdf"
    _attach(paths, name, summary="한물간 자료")
    _attach(paths, name, status=_attachments.STATUS_REMOVED,
            summary="한물간 자료", reason="새 판이 나와서 뺐다")

    got = search(paths, "attachments", query="한물간자료")
    assert got["count"] == 2
    assert {a["status"] for a in got["results"]} == {
        _attachments.STATUS_UPLOADED, _attachments.STATUS_REMOVED,
    }
    assert search(paths, "attachments", query="새 판이 나와서")["count"] == 1


def test_attachment_index_reads_only_the_yaml(paths):
    """색인의 입력원은 attachments.yaml 하나뿐이다 — 저장소를 건드리지 않는다.

    이걸 못 박는 이유: 크기를 알아내려고 저장소에 물으면 git이 빠진 파일 몸통을
    전부 내려받는다. "색인 다시 만들기" 한 번으로 그 일이 벌어지면 되돌릴 수 없다
    (한 번 받은 파일은 설정을 바꿔도 안 사라진다).
    """
    sources = _db._bowl_source_files("attachments", paths)
    assert sources == [paths.attachments_yaml]
    assert cfg.ATTACH_DIR_NAME not in str(sources[0])


# ---------------------------------------------------------------------------
# 작업일지 — 파일이 여럿인 유일한 그릇
# ---------------------------------------------------------------------------

@pytest.fixture()
def tasks_home(tmp_path, monkeypatch):
    """작업일지 개인 풀을 tmp로 격리한다(실제 ~/.namu/tasks를 건드리지 않는다)."""
    home = tmp_path / "fake_home"
    (home / ".namu" / "tasks").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home / ".namu" / "tasks"


def _log(tasks_home, project, slug, lines):
    d = tasks_home / project / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_tasks_index_covers_every_log_file(paths, tasks_home):
    _log(tasks_home, "namu-agent", "namu-57-refactor",
         ["[기록] 2026-08-01 10:00:00 hp · 그릇 레지스트리를 만들었다"])
    _log(tasks_home, "namu-agent", "namu-70-cloud",
         ["[기록] 2026-08-02 10:00:00 hp · 클라우드 화면을 고쳤다"])
    _log(tasks_home, "다른방", "무언가",
         ["[기록] 2026-08-03 10:00:00 samsung · 남의 방 기록"])

    assert search(paths, "tasks")["count"] == 3
    assert search(paths, "tasks", project="namu-agent")["count"] == 2
    assert search(paths, "tasks", query="레지스트리")["count"] == 1
    assert search(paths, "tasks", machine="samsung")["count"] == 1


def test_tasks_index_notices_a_new_log_file(paths, tasks_home):
    """파일이 **늘어난 것**도 낡음으로 잡아야 한다 — 한 파일만 보면 못 잡는다."""
    _log(tasks_home, "namu-agent", "첫작업",
         ["[기록] 2026-08-01 10:00:00 hp · 첫 줄"])
    assert search(paths, "tasks")["count"] == 1

    _log(tasks_home, "namu-agent", "새작업",
         ["[기록] 2026-08-02 10:00:00 hp · 새 작업의 첫 줄"])
    assert search(paths, "tasks")["count"] == 2


def test_tasks_task_axis_matches_slug_prefix(paths, tasks_home):
    """`namu-57`처럼 앞부분만 지목해도 걸린다(옛 `_task_matches`와 같은 규칙)."""
    _log(tasks_home, "namu-agent", "namu-57-refactor",
         ["[기록] 2026-08-01 10:00:00 hp · 가"])
    _log(tasks_home, "namu-agent", "namu-570-other",
         ["[기록] 2026-08-01 11:00:00 hp · 나"])

    got = search(paths, "tasks", task="namu-57")
    assert [e["task_slug"] for e in got["results"]] == ["namu-57-refactor"]


def test_tasks_search_looks_into_the_detail_lines(paths, tasks_home):
    """화면에서 뺀 '왜/상세'도 검색 대상이다 — 안 그러면 요약만 보이게 만든 것이
    곧 "그 내용은 검색으로도 못 찾는다"가 된다(namu-65 완료조건 11)."""
    _log(tasks_home, "namu-agent", "어떤작업", [
        "[기록] 2026-08-01 10:00:00 hp · 한 줄 요약",
        "    왜: 숨은낱말 때문에 그랬다",
    ])
    assert search(paths, "tasks", query="숨은낱말")["count"] == 1


# ---------------------------------------------------------------------------
# 작업 설명서(task.md) — 같은 그릇에 tag만 다르게 실린다 (2026-08-08)
#
# 왜 넣었나: 검색은 log.md만 봤고 실물 84개 작업 **전부** task.md에만 있는 줄을
# 갖고 있었다. "그 작업이 뭐였지"(제목·목적·완료조건)가 낱말로 안 찾혔다.
# ---------------------------------------------------------------------------

def _task_md(tasks_home, project, slug, body):
    d = tasks_home / project / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text(body, encoding="utf-8")


def test_task_doc_is_searchable(paths, tasks_home):
    _task_md(tasks_home, "namu-agent", "namu-17-subagent-parity",
             "# namu-17-subagent-parity — 네이티브 서브에이전트 대칭\n"
             "📅 생성 2026-07-01 [hp] · 🔗 관련: __\n"
             "\n## 완료조건\n- [x] 안내서 4종 검토\n")

    got = search(paths, "tasks", query="네이티브 서브에이전트 대칭")
    assert [e["task_slug"] for e in got["results"]] == ["namu-17-subagent-parity"]
    # 완료조건처럼 본문에만 있는 줄도 걸린다(설명서를 넣은 이유 그 자체).
    assert search(paths, "tasks", query="안내서 4종 검토")["count"] == 1


def test_task_doc_is_tagged_so_it_is_distinguishable(paths, tasks_home):
    """일지 줄과 한 목록에 섞이므로, 구분은 오직 tag 칸이 진다."""
    _log(tasks_home, "namu-agent", "어떤작업",
         ["[기록] 2026-08-01 10:00:00 hp · 공통낱말 들어간 일지"])
    _task_md(tasks_home, "namu-agent", "어떤작업",
             "# 어떤작업 — 공통낱말 들어간 설명서\n📅 생성 2026-08-01 [hp]\n")

    tags = {e["tag"] for e in search(paths, "tasks", query="공통낱말")["results"]}
    assert tags == {"기록", task_resolve.TASK_DOC_TAG}


def test_editing_only_the_task_doc_refreshes_the_index(paths, tasks_home):
    """설명서만 고쳐도 색인이 따라와야 한다.

    낡음 판정이 log.md만 보면 완료조건에 체크만 한 경우 서명이 그대로라 색인이
    영영 안 따라온다 — 조용히 옛 내용이 검색되는, 발견이 가장 늦는 종류의 결함이다.
    """
    _task_md(tasks_home, "namu-agent", "어떤작업", "# 어떤작업 — 첫판제목\n")
    assert search(paths, "tasks", query="첫판제목")["count"] == 1

    _task_md(tasks_home, "namu-agent", "어떤작업", "# 어떤작업 — 고친제목\n")
    assert search(paths, "tasks", query="고친제목")["count"] == 1
    assert search(paths, "tasks", query="첫판제목")["count"] == 0


def test_task_doc_obeys_the_same_axes(paths, tasks_home):
    """축(project·task·machine·since)은 일지 줄과 설명서에 똑같이 걸린다 —
    한 그릇에 섞기로 한 이상 축이 종류마다 다르게 들으면 결과를 믿을 수 없다."""
    _task_md(tasks_home, "namu-agent", "namu-57-refactor",
             "# namu-57-refactor — 낱말하나\n📅 생성 2026-08-01 [hp] · 🔗 관련: __\n")
    _task_md(tasks_home, "다른방", "namu-570-other",
             "# namu-570-other — 낱말하나\n📅 생성 2026-08-05 [samsung] · 🔗 관련: __\n")

    assert search(paths, "tasks", query="낱말하나")["count"] == 2
    assert search(paths, "tasks", query="낱말하나", project="namu-agent")["count"] == 1
    assert search(paths, "tasks", query="낱말하나", task="namu-57")["count"] == 1
    assert search(paths, "tasks", query="낱말하나", machine="samsung")["count"] == 1
    assert search(paths, "tasks", query="낱말하나", since="2026-08-03")["count"] == 1


def test_task_doc_does_not_reorder_the_log_lines(paths, tasks_home):
    """설명서는 사이사이 끼어들 뿐, 일지 줄끼리의 순서를 바꾸지 않는다."""
    _log(tasks_home, "namu-agent", "가작업",
         ["[기록] 2026-08-01 10:00:00 hp · 공통 첫 줄"])
    _log(tasks_home, "namu-agent", "나작업",
         ["[기록] 2026-08-03 10:00:00 hp · 공통 둘째 줄"])
    logs_only = [e["ts"] for e in search(paths, "tasks", query="공통")["results"]]

    _task_md(tasks_home, "namu-agent", "가작업",
             "# 가작업 — 공통 설명서\n📅 생성 2026-08-02 [hp] · 🔗 관련: __\n")
    got = search(paths, "tasks", query="공통")["results"]
    assert [e["ts"] for e in got if e["tag"] != task_resolve.TASK_DOC_TAG] == logs_only


# ---------------------------------------------------------------------------
# 낡음 판정
# ---------------------------------------------------------------------------

def test_index_is_stale_before_it_is_built(paths):
    for bowl in _db._INDEXED_BOWLS:
        assert _db.bowl_index_is_stale(bowl, paths) is True


def test_ensure_indexes_covers_every_bowl(paths):
    """부르는 쪽이 그릇 목록을 알 필요가 없어야 여섯 번째 그릇이 생겨도 배선이 안 샌다."""
    built = _db.ensure_indexes(paths)
    assert set(built) == {"learnings", *_db._INDEXED_BOWLS}
    assert all(_db.bowl_index_is_stale(b, paths) is False for b in _db._INDEXED_BOWLS)

    # 두 번째 호출은 아무것도 다시 만들지 않는다.
    assert _db.ensure_indexes(paths) == {k: False for k in built}


def test_schema_version_bump_forces_a_rebuild(paths, monkeypatch):
    """표 모양이 바뀌면 원본이 그대로여도 다시 만들어야 한다.

    옛 스키마 db를 방치해 `no such column`으로 깨진 0.1.26 사고와 같은 경로를
    미리 막는 장치다.
    """
    _memo.add(summary="메모", reason="시험", body="원문", paths=paths)
    _db.ensure_indexes(paths)
    assert _db.bowl_index_is_stale("memo", paths) is False

    monkeypatch.setattr(_db, "_INDEX_SCHEMA_VERSION", _db._INDEX_SCHEMA_VERSION + 1)
    assert _db.bowl_index_is_stale("memo", paths) is True


def test_every_declared_bowl_is_cached(paths):
    """레지스트리의 `cached`와 실제 색인 대상이 어긋나지 않는지."""
    indexed = {"learnings", *_db._INDEXED_BOWLS}
    assert {b.name for b in cfg.BOWLS if b.cached} == indexed


# ---------------------------------------------------------------------------
# 색인을 못 타는 조회도 같은 낱말 규칙을 쓴다
# ---------------------------------------------------------------------------

def test_matches_all_tokens_is_the_shared_word_rule():
    """색인을 못 쓰는 조회(클라우드의 회원별 작업일지)가 부르는 공용 규칙.

    이 함수가 없던 동안 그쪽은 거르는 규칙을 자기 파일에 베껴 두었고, 그래서
    낱말 AND 개선이 거기만 안 들어갔다. 여기서 규칙을 못 박아 두면 두 경로가
    갈라졌을 때 시험이 먼저 잡는다.
    """
    assert _db.matches_all_tokens("설계 문서", "검색 인덱스 설계 문서") is True
    assert _db.matches_all_tokens("문서 설계", "검색 인덱스 설계 문서") is True
    assert _db.matches_all_tokens("설계 첨부", "검색 인덱스 설계 문서") is False
    # 여러 칸에 흩어져 있어도 전부 있으면 걸린다.
    assert _db.matches_all_tokens("요약 상세", "요약줄", None, "상세줄") is True
    # 대소문자 무시.
    assert _db.matches_all_tokens("fts5", "FTS5 트리거") is True
    # 검색어가 없으면 거르지 않는다(축만으로 묻는 질의를 막지 않는다).
    assert _db.matches_all_tokens(None, "아무거나") is True
    assert _db.matches_all_tokens("   ", "아무거나") is True


def test_index_path_and_python_path_agree(paths):
    """같은 자료에 대해 색인 경로와 파이썬 경로의 판정이 같아야 한다."""
    _memo.add(summary="검색 인덱스", reason="설계 문서", body="원문", paths=paths)
    entry = _memo.load_all(paths)[0]
    for q in ("인덱스 문서", "문서 인덱스", "설계 인덱스", "없는말 인덱스"):
        by_index = search(paths, "memo", query=q)["count"] == 1
        by_python = _db.matches_all_tokens(q, *_memo.layers(entry))
        assert by_index == by_python, q


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
