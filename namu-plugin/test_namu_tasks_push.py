"""scripts/namu_tasks_push.py CLI 테스트(namu-34 ③-b).

대상은 항상 `Path.home()/".namu"`(NAMU_HOME과 무관)이므로, 실제 ~/.namu를 절대
건드리지 않도록 모든 테스트에서 subprocess 호출 시 HOME 환경변수를 tmp 아래
가짜 홈으로 격리한다(namu_statusline.py 관례와 동일). 원격은 tmp bare repo로
격리해 실제 네트워크 접근이 없다.
"""
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "namu_tasks_push.py"


def _run_cli(fake_home: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"], check=True, capture_output=True
    )


def _commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message], check=True, capture_output=True
    )


# ---------------------------------------------------------------------------
# no-op 조건 — 신규 sync 미개통 환경(항상 exit 0)
# ---------------------------------------------------------------------------

def test_noop_exit_zero_when_namu_dir_missing(tmp_path):
    """~/.namu 자체가 없으면(git init조차 안 된 상태) 조용히 no-op, exit 0."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()

    result = _run_cli(fake_home)

    assert result.returncode == 0
    assert result.stdout == ""
    assert not (fake_home / ".namu").exists()


def test_noop_exit_zero_when_not_git_repo(tmp_path):
    """~/.namu는 있지만 git repo가 아니면 no-op, exit 0."""
    fake_home = tmp_path / "fake_home"
    (fake_home / ".namu").mkdir(parents=True)

    result = _run_cli(fake_home)

    assert result.returncode == 0


def test_noop_exit_zero_when_no_origin_remote(tmp_path):
    """~/.namu가 git repo여도 origin 원격이 없으면 no-op, exit 0."""
    fake_home = tmp_path / "fake_home"
    home_namu = fake_home / ".namu"
    _init_git_repo(home_namu)

    result = _run_cli(fake_home)

    assert result.returncode == 0


# ---------------------------------------------------------------------------
# 정상 push 경로 — 실전 bare 원격
# ---------------------------------------------------------------------------

def test_pushes_tasks_dir_to_bare_remote(tmp_path):
    """git repo + origin 원격이 갖춰진 ~/.namu는 tasks/ 변경을 실제로 push한다."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    fake_home = tmp_path / "fake_home"
    home_namu = fake_home / ".namu"
    _init_git_repo(home_namu)
    (home_namu / "README.md").write_text("x", encoding="utf-8")
    _commit_all(home_namu, "init")
    subprocess.run(
        ["git", "-C", str(home_namu), "remote", "add", "origin", str(bare)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(home_namu), "push", "-q", "-u", "origin", "main"],
        check=True, capture_output=True,
    )

    task_dir = home_namu / "tasks" / "proj-a"
    task_dir.mkdir(parents=True)
    (task_dir / "log.md").write_text("# log\n[시작] ...\n", encoding="utf-8")

    result = _run_cli(fake_home)
    assert result.returncode == 0

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    assert (clone / "tasks" / "proj-a" / "log.md").exists()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
