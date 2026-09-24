"""저장 계층 고침 셋 — 쪽지 잠금(항목 3)·개인 사실 방어 읽기(항목 5)·칸 검사 모아
알리기(항목 4)·인증 헤더(항목 6). 모두 순수 모듈이라 tmp 경로로 바로 돈다.
"""
import asyncio
import multiprocessing
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg  # noqa: E402
import http_server  # noqa: E402
import memo  # noqa: E402
import profile  # noqa: E402
import record_input  # noqa: E402


def _paths(tmp_path: Path) -> "cfg.DataPaths":
    return cfg.DataPaths(
        learnings_yaml=tmp_path / "l.yaml", profile_yaml=tmp_path / "profile.yaml",
        db_path=tmp_path / "n.db", memo_yaml=tmp_path / "memo.yaml",
    )


# ── 항목 3: 쪽지 동시 붙이기·떼기 ─────────────────────────────────────


def test_memo_concurrent_adds_in_threads_keep_every_note(tmp_path):
    """잠금 전에는 40장을 동시에 붙이면 5장만 남았다(2026-09-25 실측)."""
    paths = _paths(tmp_path)
    n = 40
    barrier = threading.Barrier(n)

    def work(i):
        barrier.wait()
        memo.add(summary=f"메모 {i}", body=f"본문 {i}", paths=paths)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(e["summary"] for e in memo.load_all(paths)) == sorted(
        f"메모 {i}" for i in range(n)
    )


def _proc_add(memo_path: str, start: int, count: int) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import config as c
    import memo as m
    p = Path(memo_path)
    paths = c.DataPaths(
        learnings_yaml=p.parent / "l.yaml", profile_yaml=p.parent / "p.yaml",
        db_path=p.parent / "n.db", memo_yaml=p,
    )
    for i in range(start, start + count):
        m.add(summary=f"p{i}", body="b", paths=paths)


def test_memo_concurrent_adds_across_processes_keep_every_note(tmp_path):
    """stdio 서버와 웹 서버는 따로 뜬 프로세스라 파일 잠금이 있어야 한다."""
    paths = _paths(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(target=_proc_add, args=(str(paths.memo_yaml), k * 10, 10))
        for k in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    assert len(memo.load_all(paths)) == 40


def test_memo_remove_during_adds_loses_nothing_else(tmp_path):
    paths = _paths(tmp_path)
    keep_ids = [memo.add(summary=f"k{i}", body="b", paths=paths) for i in range(10)]
    doomed = keep_ids.pop(0)
    barrier = threading.Barrier(11)

    def adder(i):
        barrier.wait()
        memo.add(summary=f"new{i}", body="b", paths=paths)

    def remover():
        barrier.wait()
        memo.remove(doomed, paths=paths)

    threads = [threading.Thread(target=adder, args=(i,)) for i in range(10)]
    threads.append(threading.Thread(target=remover))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = {e["id"] for e in memo.load_all(paths)}
    assert doomed not in ids
    assert set(keep_ids) <= ids
    assert len(ids) == 9 + 10


def test_memo_lock_released_after_error(tmp_path):
    """떼기가 거절(ValueError)돼도 잠금이 풀려 다음 붙이기가 막히지 않는다."""
    paths = _paths(tmp_path)
    with pytest.raises(ValueError):
        memo.remove("없는아이디", paths=paths)
    memo.add(summary="s", body="b", paths=paths)
    assert len(memo.load_all(paths)) == 1


# ── 항목 5: 개인 사실 파일이 일부 깨져도 읽기는 산다 ─────────────────


@pytest.mark.parametrize("bad_doc", [
    "- 목록 문서\n",                 # 사전이 아닌 문서
    "subject: a\n  summary: [깨짐\n",  # 파싱 오류(ScannerError 계열)
])
def test_profile_skips_broken_doc_and_reports_it(tmp_path, bad_doc):
    paths = _paths(tmp_path)
    good_a = profile.record_fact("a", summary="첫 사실", reason="r", paths=paths)
    with paths.profile_yaml.open("a", encoding="utf-8") as f:
        f.write("---\n" + bad_doc)
    good_b = profile.record_fact("b", summary="둘째 사실", reason="r", paths=paths)

    ids = [d["id"] for d in profile.active(paths)]
    assert ids == [good_a, good_b]
    problems = profile.problems(paths)
    assert len(problems) == 1 and "건너뛰었습니다" in problems[0]


def test_profile_healthy_file_has_no_problems(tmp_path):
    paths = _paths(tmp_path)
    profile.record_fact("a", summary="s", reason="r", paths=paths)
    assert profile.problems(paths) == []
    assert profile.problems(_paths(tmp_path / "없음")) == []


def test_recall_surfaces_profile_problem_in_warnings(tmp_path):
    """recall 전체가 죽지 않고, 건너뛴 사실은 warnings로 사람에게 닿는다."""
    import os
    import subprocess
    home = tmp_path / "home"
    mem = home / ".namu" / "memory"
    mem.mkdir(parents=True)
    (mem / "learnings.yaml").write_text("", encoding="utf-8")
    (mem / "profile.yaml").write_text(
        "---\nid: A\nsubject: a\nsummary: 성한 사실\nreason: r\n---\nsubject: b\n  summary: [깨짐\n",
        encoding="utf-8",
    )
    code = (
        f"import sys; sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "import mcp_server\n"
        "r = mcp_server.namu_recall(project='*')\n"
        "print('PROFILE', [d['id'] for d in r['profile']])\n"
        "print('WARN', any('개인 사실' in w for w in r['warnings']))\n"
    )
    env = dict(os.environ, HOME=str(home))
    env.pop("NAMU_HOME", None)
    r = subprocess.run([sys.executable, "-c", code], cwd=str(home), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "PROFILE ['A']" in r.stdout
    assert "WARN True" in r.stdout


# ── 항목 4: 칸 검사가 걸린 칸을 모두 알린다 ───────────────────────────


def test_missing_fields_are_all_reported_at_once():
    with pytest.raises(ValueError) as e:
        record_input.normalize({"bowl": "learnings"})
    msg = str(e.value)
    for name in ("summary", "reason", "body", "topic"):
        assert f"'{name}' 칸이 필요합니다" in msg
    assert "네 가지" in msg
    assert "'이 필요합니다" not in msg   # 조사가 칸 이름에 붙지 않는다


def test_foreign_fields_are_all_reported_at_once():
    with pytest.raises(ValueError) as e:
        record_input.normalize({
            "bowl": "memo", "summary": "s", "reason": "r", "body": "b",
            "topic": "t", "project": "p",
        })
    msg = str(e.value)
    assert "'topic' 칸을 받지 않습니다" in msg
    assert "'project' 칸을 받지 않습니다" in msg
    assert "두 가지" in msg


def test_single_problem_message_has_no_numbering():
    with pytest.raises(ValueError) as e:
        record_input.normalize({"bowl": "memo", "summary": "s", "body": "b"})
    msg = str(e.value)
    assert "'reason' 칸이 필요합니다" in msg
    assert "가지입니다" not in msg


# ── 항목 6: 인증 헤더 ─────────────────────────────────────────────────


def _probe(headers, token):
    seen = {}

    async def app(scope, receive, send):
        seen["ok"] = True

    sent = []

    async def send(m):
        sent.append(m)

    mw = http_server.AuthMiddleware(app, token)
    asyncio.run(mw({"type": "http", "headers": headers, "client": ("1.2.3.4", 1)}, None, send))
    return "ok" if seen else sent[0]["status"]


@pytest.mark.parametrize("scheme", [b"Bearer", b"bearer", b"BEARER"])
def test_bearer_scheme_is_case_insensitive(scheme):
    assert _probe([(b"authorization", scheme + b" s3cret")], "s3cret") == "ok"


def test_non_ascii_token_matches_utf8_header():
    tok = "나무토큰"
    assert _probe([(b"x-api-key", tok.encode("utf-8"))], tok) == "ok"
    assert _probe([(b"authorization", b"Bearer " + tok.encode("utf-8"))], tok) == "ok"


@pytest.mark.parametrize("headers", [
    [(b"authorization", b"Bearer wrong")],
    [(b"authorization", b"Basic s3cret")],
    [(b"authorization", b"Bearer")],
    [(b"authorization", b"s3cret")],
    [(b"x-api-key", b"s3cre")],
    [],
])
def test_wrong_credentials_still_rejected(headers):
    assert _probe(headers, "s3cret") == 401
