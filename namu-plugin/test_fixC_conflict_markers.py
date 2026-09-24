"""멈춘 병합이 충돌 표시를 원격에 올리던 사고의 회귀 검사(2026-09 검수 C-1, C-7, C-9).

검수 재현(test_repro_conflict_markers.py)을 뒤집었다: 예전에는 sync_push 복구 pull·
sync_pull·sync_setup 병합이 충돌로 멈춘 채 돌아가 다음 커밋이 `<<<<<<<`를 원격에
올렸다. 지금은 ① memo.yaml만 부딪히면 3-way id 병합으로 풀고 ② 그 밖은 되돌리며
③ 커밋 직전 가드가 멈춘 병합 위에서는 커밋하지 않는다.

실제 임시 저장소(원격 bare + 클론 둘)로 돈다 — 진짜 ~/.namu는 건드리지 않는다.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg  # noqa: E402
import memory_sync as ms  # noqa: E402
import startup_sync  # noqa: E402

MARK = "<<<<<<<"


def _git(path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=check, capture_output=True, encoding="utf-8"
    )


def _w(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _memo(*entries):
    """memo.py(_write_all)와 같은 형식 — YAML 리스트 한 문서."""
    return yaml.safe_dump(
        [{"id": i, "timestamp": "2026-09-01T00:00:00+09:00", "summary": s} for i, s in entries],
        allow_unicode=True, default_flow_style=False, sort_keys=False,
    )


# id는 ULID처럼 시간순으로 정렬되는 값을 쓴다(병합 결과가 id 순이다).
M0, MA, MB = "01K00000000000000000000000", "01K00000000000000000000AAA", "01K00000000000000000000BBB"


@pytest.fixture()
def repos(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True, capture_output=True)
    _git(a, "config", "user.email", "t@e")
    _git(a, "config", "user.name", "t")
    ms.ensure_gitattributes_union(a)
    _w(a, ".gitignore", "db/\n")
    _w(a, "memory/learnings.yaml", "- id: a\n")
    _w(a, "memory/memo.yaml", _memo((M0, "처음")))
    _w(a, "config/x.json", '{"v": 0}\n')
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "init")
    _git(a, "push", "-q", "-u", "origin", "main")
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True, capture_output=True)
    _git(b, "config", "user.email", "t@e")
    _git(b, "config", "user.name", "t")
    (a / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", a)
    monkeypatch.delenv("NAMU_SYNC", raising=False)
    return {"origin": origin, "a": a, "b": b}


def _remote(repos, rel):
    _git(repos["b"], "fetch", "-q")
    return _git(repos["b"], "show", f"origin/main:{rel}").stdout


def _remote_ids(repos):
    return [e["id"] for e in yaml.safe_load(_remote(repos, "memory/memo.yaml"))]


def _clean(a):
    assert not (Path(a) / ".git" / "MERGE_HEAD").exists()
    assert ms.unmerged_paths(a) == []
    for rel in ("memory/memo.yaml", "config/x.json"):
        p = Path(a) / rel
        if p.exists():
            assert MARK not in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# memo 3-way 자동 병합 (오케스트레이터 결정 1(c))
# ---------------------------------------------------------------------------
def test_two_clones_add_and_remove_memo_merge_cleanly(repos):
    """B는 메모 mB를 붙여 먼저 올리고, A는 오프라인에서 m0을 떼고 mA를 붙였다.
    병합 결과에는 두 붙이기가 모두 있고 뗀 m0은 없어야 하며, 충돌 표시 없이 올라간다."""
    a, b = repos["a"], repos["b"]
    _w(b, "memory/memo.yaml", _memo((M0, "처음"), (MB, "B의 메모")))
    _git(b, "commit", "-qam", "memo B")
    _git(b, "push", "-q")

    _w(a, "memory/memo.yaml", _memo((MA, "A의 메모")))  # m0 뗌 + mA 붙임
    assert ms.sync_push("memo: A") is True

    _clean(a)
    assert _remote_ids(repos) == [MA, MB]
    assert MARK not in _remote(repos, "memory/memo.yaml")
    local = yaml.safe_load((a / "memory/memo.yaml").read_text(encoding="utf-8"))
    assert [e["id"] for e in local] == [MA, MB]


def test_sync_pull_resolves_memo_only_conflict(repos):
    a, b = repos["a"], repos["b"]
    _w(b, "memory/memo.yaml", _memo((M0, "처음"), (MB, "B")))
    _git(b, "commit", "-qam", "memo B")
    _git(b, "push", "-q")
    _w(a, "memory/memo.yaml", _memo((M0, "처음"), (MA, "A")))
    _git(a, "commit", "-qam", "memo A (push 실패로 남은 로컬 커밋)")

    assert ms.sync_pull() is True
    _clean(a)
    ids = [e["id"] for e in yaml.safe_load((a / "memory/memo.yaml").read_text(encoding="utf-8"))]
    assert ids == [M0, MA, MB]


def test_merge_memo_entries_rules():
    base = [{"id": "1"}, {"id": "2"}]
    ours = [{"id": "1"}, {"id": "3"}]            # 2 뗌, 3 붙임
    theirs = [{"id": "2"}, {"id": "1"}, {"id": "4"}]  # 4 붙임
    assert [e["id"] for e in ms.merge_memo_entries(base, ours, theirs)] == ["1", "3", "4"]
    # base가 없는 경우(양쪽이 새로 만든 파일) — 합집합
    assert [e["id"] for e in ms.merge_memo_entries([], [{"id": "b"}], [{"id": "a"}])] == ["a", "b"]
    with pytest.raises(ValueError):
        ms.merge_memo_entries([], [{"summary": "id 없음"}], [])
    with pytest.raises(ValueError):
        ms.merge_memo_entries([], {"id": "x"}, [])


# ---------------------------------------------------------------------------
# memo가 아닌 충돌 — 되돌리고, 충돌 표시를 절대 커밋하지 않는다
# ---------------------------------------------------------------------------
def _diverge_config(repos):
    a, b = repos["a"], repos["b"]
    _w(b, "config/x.json", '{"v": "B"}\n')
    _git(b, "commit", "-qam", "cfg B")
    _git(b, "push", "-q")
    _w(a, "config/x.json", '{"v": "A"}\n')


def test_runtime_push_non_memo_conflict_is_aborted_and_never_pushed(repos):
    a = repos["a"]
    _diverge_config(repos)
    assert ms.sync_push("cfg A") is False
    _clean(a)  # 예전: MERGE_HEAD + <<<<<<< 가 남았다
    # 다음 기록 → sync_push. 예전에는 여기서 충돌 표시가 원격으로 올라갔다.
    _w(a, "memory/learnings.yaml", "- id: a\n- id: next\n")
    ms.sync_push("learn: next")
    assert MARK not in _remote(repos, "config/x.json")
    assert MARK not in _remote(repos, "memory/memo.yaml")


def test_sync_pull_non_memo_conflict_is_aborted(repos):
    a = repos["a"]
    _diverge_config(repos)
    _git(a, "commit", "-qam", "cfg A")
    assert ms.sync_pull() is False
    _clean(a)
    assert "PULL FAIL" in (a / "db" / "sync.log").read_text(encoding="utf-8")


def test_push_guard_refuses_to_commit_on_top_of_stuck_merge(repos, monkeypatch):
    """되돌리기마저 실패해 병합이 멈춘 채면 _push_steps는 커밋하지 않는다(가드 1(b))."""
    a = repos["a"]
    _diverge_config(repos)
    _git(a, "commit", "-qam", "cfg A")
    _git(a, "pull", "--no-rebase", "--no-edit", check=False)  # 충돌로 멈춘 상태를 만든다
    assert ms.merge_in_progress(a)
    head = _git(a, "rev-parse", "HEAD").stdout
    monkeypatch.setattr(ms, "abort_merge", lambda home: "충돌 되돌리기 실패: 흉내")
    assert ms.sync_push("x") is False
    assert _git(a, "rev-parse", "HEAD").stdout == head
    assert "커밋하지 않음" in (a / "db" / "sync.log").read_text(encoding="utf-8")


def test_commit_pending_settles_stuck_merge_before_committing(repos):
    """컨테이너 재시작 경로: 멈춘 병합 위에서 commit_pending이 충돌 표시를 '보존'
    커밋하던 것을 막는다 — 먼저 되돌리고 나서 진짜 미커밋 변경만 커밋한다."""
    a = repos["a"]
    _diverge_config(repos)
    _git(a, "commit", "-qam", "cfg A")
    _git(a, "pull", "--no-rebase", "--no-edit", check=False)
    assert MARK in (a / "config/x.json").read_text(encoding="utf-8")
    startup_sync.commit_pending(a, "보존")
    _clean(a)
    shown = _git(a, "show", "HEAD:config/x.json").stdout
    assert MARK not in shown


def test_container_restart_path_never_pushes_markers(repos):
    """검수 재현 3번을 뒤집었다: startup_pull → sync_setup → (재시작) → startup_pull →
    sync_setup 어디에서도 충돌 표시가 원격에 가지 않는다. 충돌 문장(stdout)이 결과에
    실린다(1(d))."""
    a, origin = repos["a"], repos["origin"]
    _diverge_config(repos)
    _git(a, "commit", "-qam", "cfg A")

    r1 = startup_sync.startup_pull(a)
    assert r1["ok"] is False
    _clean(a)
    rep = ms.sync_setup_report(str(origin))
    _clean(a)
    assert any("CONFLICT" in n for n in rep["network"]), rep["network"]
    assert rep["fatal"] == []

    startup_sync.startup_pull(a)
    ms.sync_setup(str(origin))
    _clean(a)
    assert MARK not in _remote(repos, "config/x.json")


def test_startup_pull_resolves_memo_only_conflict(repos):
    a, b = repos["a"], repos["b"]
    _w(b, "memory/memo.yaml", _memo((M0, "처음"), (MB, "B")))
    _git(b, "commit", "-qam", "memo B")
    _git(b, "push", "-q")
    _w(a, "memory/memo.yaml", _memo((MA, "A")))  # 커밋 안 된 변경 — commit_pending이 보존
    r = startup_sync.startup_pull(a)
    assert r["ok"] is True, r
    _clean(a)
    assert startup_sync.read_status(a) is None


# ---------------------------------------------------------------------------
# C-7: sync_setup은 `add -A`를 쓰지 않는다
# ---------------------------------------------------------------------------
def test_sync_setup_does_not_commit_stray_files(repos):
    a, origin = repos["a"], repos["origin"]
    _w(a, "stray_secret.txt", "이건 올라가면 안 된다\n")
    _w(a, "memory/learnings.yaml", "- id: a\n- id: setup\n")
    rep = ms.sync_setup_report(str(origin))
    assert rep["fatal"] == [] and rep["network"] == [], rep
    tree = _git(a, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert "stray_secret.txt" not in tree
    assert "memory/learnings.yaml" in tree and ".namu_sync" in tree
    assert "- id: setup" in _remote(repos, "memory/learnings.yaml")


# ---------------------------------------------------------------------------
# C-9: 개인 PC의 sync_pull도 오래된 잠금을 치운다
# ---------------------------------------------------------------------------
def test_sync_pull_clears_only_stale_locks(repos):
    a = repos["a"]
    stale = a / ".git" / "refs" / "heads" / "main.lock"
    fresh = a / ".git" / "index.lock"
    stale.write_text("")
    old = time.time() - ms.PERSONAL_STALE_LOCK_AGE_SECONDS - 60
    os.utime(stale, (old, old))
    fresh.write_text("")
    ms.sync_pull()
    assert not stale.exists()
    assert fresh.exists()  # 갓 생긴 잠금은 살아 있는 git의 것일 수 있다
    fresh.unlink()
    assert ms.sync_pull() is True


# ---------------------------------------------------------------------------
# 추가 요청: memo.py의 잠금 파일(memory/.memo.lock)은 커밋되지 않는다
# ---------------------------------------------------------------------------
def test_memo_lock_file_is_never_committed_by_sync_push(repos):
    """이미 개통된 기기(sync_setup을 다시 안 돈다)에서도 `git add memory/`가 잠금
    파일을 줍지 않는다 — 제외 줄을 .git/info/exclude에 add 직전마다 보장한다."""
    a = repos["a"]
    (a / "memory" / ".memo.lock").write_text("", encoding="utf-8")
    _w(a, "memory/learnings.yaml", "- id: a\n- id: with-lock\n")
    assert ms.sync_push("learn: lock") is True
    tree = _git(a, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert "memory/.memo.lock" not in tree
    assert "memory/.memo.lock" in (a / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    # commit_pending(컨테이너 시작 경로)도 마찬가지
    _w(a, "memory/learnings.yaml", "- id: a\n- id: with-lock\n- id: pending\n")
    startup_sync.commit_pending(a, "보존")
    assert "memory/.memo.lock" not in _git(a, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
