"""터미널 첨부 주고받기 테스트 — **진짜 git으로 돈다**(대역 없음).

이 모듈이 다루는 것은 전부 "격리된 폴더에서 git이 어떻게 움직이는가"다. 그런
동작은 흉내로는 검증되지 않는다 — 실제로 `git add`가 sparse 제외 경로를 조용히
무시하는 것이 이 구현의 출발점이었고, 흉내를 냈다면 그 사실을 영영 몰랐을 것이다.

각 시험은 tmp에 원격(bare) 하나와 작업 사본 하나를 만들고 `cfg.NAMU_DATA_ROOT`를
그 사본으로 갈아끼운다 — 실제 `~/.namu`는 건드리지 않는다.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import attach_local
import config as cfg


def _git(cwd, *args):
    res = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
    )
    assert res.returncode == 0, f"git {args} 실패: {res.stderr}"
    return res.stdout


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """첨부 격리가 걸린 작업 사본 + 그 원격. cfg.NAMU_DATA_ROOT를 여기로 돌린다."""
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, timeout=60)

    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(home)], check=True, timeout=60
    )
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "tester")
    (home / "memory").mkdir()
    (home / "memory" / "learnings.yaml").write_text("[]\n", encoding="utf-8")
    _git(home, "add", "-A")
    _git(home, "commit", "-q", "-m", "init")
    _git(home, "remote", "add", "origin", str(origin))
    _git(home, "push", "-q", "-u", "origin", "HEAD:main")
    # 첨부 격리 — 이 시험들이 겨냥하는 조건 그 자체다.
    _git(home, "sparse-checkout", "set", "--no-cone", *cfg.ATTACH_SPARSE_PATTERNS)

    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", home)
    return home


def _remote_paths(home) -> list[str]:
    # `-z`가 없으면 git이 한글 이름을 이스케이프해 돌려준다 — 그 값과 비교하면
    # 시험이 늘 실패하거나(운 나쁘면) 엉뚱한 것을 통과시킨다.
    out = _git(home, "ls-tree", "-r", "--name-only", "-z", "origin/main")
    return [name for name in out.split("\0") if name.strip()]


# ---------------------------------------------------------------------------
# 이름 규칙
# ---------------------------------------------------------------------------

def test_name_is_placed_under_the_attach_folder():
    assert attach_local.normalize_name("보고서.pdf") == f"{cfg.ATTACH_DIR_NAME}/보고서.pdf"
    assert (
        attach_local.normalize_name(f"{cfg.ATTACH_DIR_NAME}/보고서.pdf")
        == f"{cfg.ATTACH_DIR_NAME}/보고서.pdf"
    )


@pytest.mark.parametrize("bad", ["", "   ", "../밖.txt", "하위/폴더.txt", "a\\b.txt"])
def test_names_that_escape_the_folder_are_rejected(bad):
    # 거슬러 올라가는 이름을 받으면 첨부가 저장소의 다른 폴더에 쓰인다.
    with pytest.raises(attach_local.AttachError):
        attach_local.normalize_name(bad)


# ---------------------------------------------------------------------------
# 올리기 — 격리된 폴더라 평범한 add로는 안 된다
# ---------------------------------------------------------------------------

def test_upload_lands_in_the_remote(repo):
    result = attach_local.upload("설계.txt", "내용입니다".encode(), "attach: 올림")

    assert result["path"] == f"{cfg.ATTACH_DIR_NAME}/설계.txt"
    assert result["replaced"] is False
    assert f"{cfg.ATTACH_DIR_NAME}/설계.txt" in _remote_paths(repo)


def test_upload_does_not_leave_the_file_on_this_computer(repo):
    """첨부가 각 PC에 쌓이지 않게 하는 것이 격리의 목적이다 — 올린 뒤 이 PC의
    작업트리에 파일이 남으면 그 목적이 깨진다."""
    attach_local.upload("설계.txt", b"x", "attach: 올림")

    assert not (repo / cfg.ATTACH_DIR_NAME / "설계.txt").exists()
    # 상태도 깨끗해야 한다 — 손으로 지우면 ' D'가 영구히 남는다.
    assert _git(repo, "status", "--porcelain").strip() == ""


def test_uploading_the_same_name_again_is_a_revision(repo):
    attach_local.upload("설계.txt", b"1", "attach: 올림")
    second = attach_local.upload("설계.txt", b"22", "attach: 올림")

    assert second["replaced"] is True
    assert second["bytes"] == 2
    assert attach_local.download("설계.txt") == b"22"


def test_later_memory_push_does_not_delete_the_attachment(repo):
    """기억을 올릴 때 첨부가 삭제로 딸려가면 안 된다 — 이 저장소에서 첨부가
    사라지는 가장 위험한 경로다."""
    attach_local.upload("설계.txt", b"x", "attach: 올림")

    (repo / "memory" / "learnings.yaml").write_text("- a\n", encoding="utf-8")
    _git(repo, "add", "memory/")
    _git(repo, "commit", "-q", "-m", "learn")
    _git(repo, "push", "-q")

    assert f"{cfg.ATTACH_DIR_NAME}/설계.txt" in _remote_paths(repo)


# ---------------------------------------------------------------------------
# 목록 — 크기를 저장소에 묻지 않는다
# ---------------------------------------------------------------------------

def test_list_returns_names_only(repo):
    attach_local.upload("가.txt", b"1", "attach: 올림")
    attach_local.upload("나.txt", b"22", "attach: 올림")

    paths = attach_local.list_paths()

    assert sorted(paths) == [
        f"{cfg.ATTACH_DIR_NAME}/가.txt", f"{cfg.ATTACH_DIR_NAME}/나.txt",
    ]


def test_list_is_empty_before_anything_is_uploaded(repo):
    # 첨부 폴더가 아직 없는 것은 오류가 아니라 "아직 아무것도 안 올렸다"이다.
    assert attach_local.list_paths() == []


def test_list_does_not_ask_the_repository_for_sizes():
    """`-l`(크기 포함)을 붙이면 git이 크기를 알아내려고 빠진 파일 몸통을 전부
    내려받아 첨부 격리가 뚫린다(2026-08-07 실측: 파일 2,548개에 7분 넘게 안 끝남).
    그래서 명령 자체에 그 옵션이 없어야 한다 — 동작으로는 드러나지 않는 계약이라
    소스로 못 박는다."""
    source = (Path(__file__).parent / "attach_local.py").read_text(encoding="utf-8")
    listing = source[source.index("def list_paths"):source.index("def download")]
    assert "--name-only" in listing
    assert '"-l"' not in listing


# ---------------------------------------------------------------------------
# 받기 — 몸통이 없는 사본에서 그 하나만
# ---------------------------------------------------------------------------

def test_download_returns_raw_bytes(repo):
    blob = bytes(range(256))  # 텍스트가 아닌 파일 — 디코딩하면 깨진다
    attach_local.upload("그림.bin", blob, "attach: 올림")

    assert attach_local.download("그림.bin") == blob


def test_download_of_a_missing_file_says_so(repo):
    with pytest.raises(attach_local.AttachError, match="없습니다"):
        attach_local.download("없는파일.txt")


# ---------------------------------------------------------------------------
# 지우기
# ---------------------------------------------------------------------------

def test_delete_removes_it_from_the_remote(repo):
    attach_local.upload("설계.txt", b"x", "attach: 올림")

    attach_local.delete("설계.txt", "attach: 지움")

    assert f"{cfg.ATTACH_DIR_NAME}/설계.txt" not in _remote_paths(repo)
    assert attach_local.list_paths() == []
    assert _git(repo, "status", "--porcelain").strip() == ""


def test_delete_keeps_the_file_in_history(repo):
    """완전 삭제가 아니라는 사실을 시험으로 못 박는다 — 도구 설명문이 회원에게
    알리는 내용이므로, 실제로 그런지 여기서 확인해 둔다."""
    attach_local.upload("설계.txt", "내용".encode(), "attach: 올림")
    before = _git(repo, "rev-parse", "HEAD").strip()

    attach_local.delete("설계.txt", "attach: 지움")

    older = _git(repo, "cat-file", "blob", f"{before}:{cfg.ATTACH_DIR_NAME}/설계.txt")
    assert older.strip() == "내용"


def test_delete_of_a_missing_file_says_so(repo):
    with pytest.raises(attach_local.AttachError, match="없습니다"):
        attach_local.delete("없는파일.txt", "attach: 지움")


# ---------------------------------------------------------------------------
# 저장소가 아닌 곳
# ---------------------------------------------------------------------------

def test_without_a_git_repo_it_explains_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", tmp_path / "빈폴더")
    with pytest.raises(attach_local.AttachError, match="namu_sync_setup"):
        attach_local.list_paths()
