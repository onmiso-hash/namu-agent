"""첨부 올리기 실패 경로와 이름 검사의 회귀 검사(2026-09 검수 C-3, C-4).

검수 재현(test_repro_attach.py)을 뒤집었다: 예전에는 원격이 앞서 있어 push가
거절되면 **첨부 기록 없는 첨부 커밋**이 로컬에 남았고(다음 sync_push가 조용히 올렸다),
같은 내용을 다시 올리면 "nothing to commit"으로 실패했다.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import attach_local  # noqa: E402
import config as cfg  # noqa: E402
import memory_sync as ms  # noqa: E402


def _git(path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=check, capture_output=True, encoding="utf-8"
    )


@pytest.fixture()
def repos(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True, capture_output=True)
    _git(a, "config", "user.email", "t@e")
    _git(a, "config", "user.name", "t")
    (a / "memory").mkdir()
    (a / "memory/learnings.yaml").write_text("- id: a\n")
    _git(a, "add", "-A")
    _git(a, "commit", "-qm", "init")
    _git(a, "push", "-q", "-u", "origin", "main")
    ms.ensure_attach_isolation(a)
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True, capture_output=True)
    _git(b, "config", "user.email", "t@e")
    _git(b, "config", "user.name", "t")
    (a / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", a)
    monkeypatch.delenv("NAMU_SYNC", raising=False)
    return {"origin": origin, "a": a, "b": b, "tmp": tmp_path}


def _remote_tree(repos):
    _git(repos["b"], "fetch", "-q")
    return _git(repos["b"], "ls-tree", "-r", "--name-only", "-z", "origin/main").stdout.split("\0")


def _worktree_clean(a):
    status = _git(a, "status", "--porcelain").stdout
    return [ln for ln in status.splitlines() if not ln.endswith(".namu_sync")] == []


def test_upload_when_remote_ahead_pulls_and_retries(repos):
    a, b = repos["a"], repos["b"]
    (b / "memory/learnings.yaml").write_text("- id: a\n- id: fromB\n")
    _git(b, "commit", "-qam", "B")
    _git(b, "push", "-q")

    got = attach_local.upload("보고서.txt", b"hello", "attach: 올림 보고서.txt")
    assert got["path"] == "attach_file/보고서.txt"
    assert "attach_file/보고서.txt" in _remote_tree(repos)
    # 로컬도 원격과 같은 자리(앞서 있는 커밋 없음)
    assert _git(a, "rev-list", "--count", "origin/main..HEAD").stdout.strip() == "0"
    assert not (a / "attach_file" / "보고서.txt").exists()  # 격리 유지
    assert _worktree_clean(a)


def test_upload_permanent_push_failure_leaves_no_orphan_commit(repos):
    """원격이 아예 사라져 push·pull이 다 실패해도 로컬에 첨부 커밋이 남지 않는다 —
    그래야 다음 sync_push가 첨부 기록 없는 파일을 조용히 올리는 일이 없다."""
    a = repos["a"]
    head = _git(a, "rev-parse", "HEAD").stdout
    repos["origin"].rename(repos["tmp"] / "gone.git")
    with pytest.raises(attach_local.AttachError):
        attach_local.upload("a.txt", b"x", "attach: 올림 a.txt")
    assert _git(a, "rev-parse", "HEAD").stdout == head
    assert _git(a, "diff", "--cached", "--name-only").stdout.strip() == ""
    assert not (a / "attach_file" / "a.txt").exists()
    assert "attach_file/a.txt" not in attach_local.list_paths()


def test_reupload_identical_content_succeeds(repos):
    attach_local.upload("a.txt", b"same", "attach: 올림 a.txt")
    got = attach_local.upload("a.txt", b"same", "attach: 새 판 a.txt")
    assert got == {"path": "attach_file/a.txt", "bytes": 4, "replaced": True}
    assert _worktree_clean(repos["a"])


@pytest.mark.parametrize("name", [
    ".", ".git", ".gitattributes", ".GIT", "attach_file/.gitignore",
    "a\nb.txt", "a\rX-Evil: 1.txt", "tab\there.txt", "del\x7f.txt",
    "<img src=x onerror=alert(1)>.txt", 'quote".txt',
])
def test_normalize_name_rejects_dangerous_names(name):
    with pytest.raises(attach_local.AttachError):
        attach_local.normalize_name(name)


@pytest.mark.parametrize("name, expected", [
    ("보고서.pdf", "attach_file/보고서.pdf"),
    ("attach_file/보고서.pdf", "attach_file/보고서.pdf"),
    (".hidden.txt", "attach_file/.hidden.txt"),
    ("a git.txt", "attach_file/a git.txt"),
])
def test_normalize_name_still_accepts_normal_names(name, expected):
    assert attach_local.normalize_name(name) == expected
