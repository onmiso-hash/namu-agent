"""startup_sync.py 테스트 — 2026-08-16 무한 재시작 사고의 회귀 방지
(namu-entrypoint-pull-resilience).

가짜 git이 아니라 실제 임시 저장소(원격 bare + 두 기기 클론)로 사고를 그대로
재현한다 — 사고의 급소가 "커밋 안 된 파일이 있을 때 git pull이 거부한다"는 git의
실제 동작이라, 그걸 흉내 내면 검사가 검사하는 게 없어진다.

테스트 repo에는 로컬(--global 아님) git config로 user.name/email을 심는다
(test_memory_sync.py와 동일 관례 — CI의 전역 git 설정 유무에 의존하지 않는다).
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import memory_sync as ms  # noqa: E402
import startup_sync  # noqa: E402

UNION_ATTRS = "memory/learnings.yaml merge=union\ntasks/**/log.md merge=union\n"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, encoding="utf-8"
    )


def _identity(path: Path) -> None:
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")


def _write(path: Path, rel: str, text: str) -> None:
    target = path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture()
def repos(tmp_path):
    """원격(bare) 하나 + 클론 둘(hp, web). web이 사고를 겪은 컨테이너 자리다."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)],
        check=True, capture_output=True,
    )

    hp = tmp_path / "hp"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(hp)], check=True, capture_output=True
    )
    _identity(hp)
    _write(hp, ".gitattributes", UNION_ATTRS)
    _write(hp, "memory/learnings.yaml", "- id: a\n")
    _git(hp, "add", "-A")
    _git(hp, "commit", "-q", "-m", "init")
    _git(hp, "push", "-q", "-u", "origin", "main")

    web = tmp_path / "web"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(web)], check=True, capture_output=True
    )
    _identity(web)
    return {"origin": origin, "hp": hp, "web": web}


# ---------------------------------------------------------------------------
# 완료조건 ③ — 커밋 안 된 파일이 남아 있어도 시작이 막히지 않는다
# ---------------------------------------------------------------------------


def test_plain_pull_really_fails_with_staged_changes(repos):
    """사고의 전제부터 실측한다 — 이게 실패하면 나머지 테스트는 아무것도 안 지킨다.

    양쪽이 같은 파일을 만들고 한쪽이 커밋을 안 하면, 맨 git pull은 거부한다.
    (사고 로그: "Your local changes to the following files would be overwritten by merge")
    """
    hp, web = repos["hp"], repos["web"]
    _write(hp, "tasks/proj/t1/log.md", "[시작] hp가 적은 줄\n")
    _git(hp, "add", "-A")
    _git(hp, "commit", "-q", "-m", "hp task")
    _git(hp, "push", "-q")

    _write(web, "tasks/proj/t1/log.md", "[기록] web이 적은 줄\n")
    _git(web, "add", "-A")  # add까지만 — commit 안 됨(사고 때의 `A` 상태)

    res = subprocess.run(
        ["git", "-C", str(web), "pull", "--no-rebase", "--no-edit"],
        capture_output=True, encoding="utf-8",
    )
    assert res.returncode != 0


def test_startup_pull_commits_pending_and_succeeds(repos):
    """같은 상황에서 startup_pull은 성공한다 — 커밋 안 된 변경을 커밋해 보존한 뒤
    받아오므로, 줄 단위 병합(union) 대상인 log.md는 양쪽 줄이 모두 남는다."""
    hp, web = repos["hp"], repos["web"]
    _write(hp, "tasks/proj/t1/log.md", "[시작] hp가 적은 줄\n")
    _git(hp, "add", "-A")
    _git(hp, "commit", "-q", "-m", "hp task")
    _git(hp, "push", "-q")

    _write(web, "tasks/proj/t1/log.md", "[기록] web이 적은 줄\n")
    _git(web, "add", "-A")

    result = startup_sync.startup_pull(web)

    assert result["ok"] is True
    merged = (web / "tasks/proj/t1/log.md").read_text(encoding="utf-8")
    assert "hp가 적은 줄" in merged
    assert "web이 적은 줄" in merged  # 남의 기억을 버리지 않았다
    assert startup_sync.read_status(web) is None


def test_startup_pull_never_discards_local_memory_on_conflict(repos):
    """진짜 충돌(union 대상이 아닌 task.md)이면 받아오기를 되돌리고 실패로 남긴다 —
    그래도 이 기기의 기억은 그대로고, 워킹트리에 충돌 표시가 박히지 않는다.

    사고 때 막힌 파일 둘 중 task.md는 `.gitattributes`의 union 목록에 없다 —
    "커밋만 해주면 다 풀린다"가 성립하지 않는 자리라 따로 지킨다."""
    hp, web = repos["hp"], repos["web"]
    _write(hp, "tasks/proj/t1/task.md", "# hp가 만든 설명서\n")
    _git(hp, "add", "-A")
    _git(hp, "commit", "-q", "-m", "hp task.md")
    _git(hp, "push", "-q")

    _write(web, "tasks/proj/t1/task.md", "# web이 만든 설명서\n")
    _git(web, "add", "-A")

    result = startup_sync.startup_pull(web)

    assert result["ok"] is False
    body = (web / "tasks/proj/t1/task.md").read_text(encoding="utf-8")
    assert "web이 만든 설명서" in body
    assert "<<<<<<<" not in body  # merge --abort로 되돌아갔다
    assert not (web / ".git" / "MERGE_HEAD").exists()


def test_startup_pull_is_noop_safe_when_nothing_pending(repos):
    """받아올 것도 커밋할 것도 없을 때 조용히 성공한다(빈 커밋을 만들지 않는다)."""
    web = repos["web"]
    before = _git(web, "rev-list", "--count", "HEAD").stdout.strip()

    result = startup_sync.startup_pull(web)

    assert result["ok"] is True
    assert _git(web, "rev-list", "--count", "HEAD").stdout.strip() == before


# ---------------------------------------------------------------------------
# 완료조건 ③ — 오래된 잠금 파일이 시작을 막지 않는다
# ---------------------------------------------------------------------------


def test_stale_locks_removed_including_nested_ones(repos):
    """`.git` 바로 아래만 보면 안 된다 — 사고 때 사람을 두 번 막은
    `refs/heads/main.lock`이 하위 폴더에 있었다."""
    web = repos["web"]
    nested = web / ".git" / "refs" / "heads" / "main.lock"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("", encoding="utf-8")
    top = web / ".git" / "gc.pid.lock"
    top.write_text("", encoding="utf-8")
    import os

    old = 1_000_000.0  # 1970년대 — 확실히 오래된 것
    os.utime(nested, (old, old))
    os.utime(top, (old, old))

    removed = startup_sync.clear_stale_git_locks(web)

    assert not nested.exists()
    assert not top.exists()
    assert len(removed) == 2


def test_fresh_locks_are_left_alone(repos):
    """갓 생긴 잠금은 지금 돌고 있는 git의 것일 수 있으므로 손대지 않는다."""
    web = repos["web"]
    fresh = web / ".git" / "index.lock"
    fresh.write_text("", encoding="utf-8")

    removed = startup_sync.clear_stale_git_locks(web)

    assert fresh.exists()
    assert removed == []


def test_startup_pull_recovers_from_stale_lock(repos):
    """오래된 index.lock이 남아 있으면 커밋 자체가 막힌다 — 시작 절차가 이걸
    스스로 치우고 끝까지 간다(사람이 손으로 rm 하지 않아도 된다)."""
    import os

    web = repos["web"]
    _write(web, "memory/learnings.yaml", "- id: a\n- id: b\n")
    lock = web / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    os.utime(lock, (1_000_000.0, 1_000_000.0))

    result = startup_sync.startup_pull(web)

    assert result["ok"] is True
    assert not lock.exists()
    # 기억 그릇은 전부 커밋됐다. db/(sync.log 등 기기별 물증)는 대상이 아니라 그대로
    # 남는다 — 실제 ~/.namu에서는 sync_setup이 gitignore에 넣는 폴더다.
    assert _git(web, "status", "--porcelain", "--", "memory", "tasks").stdout.strip() == ""


# ---------------------------------------------------------------------------
# 완료조건 ①② — 실패해도 죽지 않고, 실패 사실이 눈에 보이는 곳에 남는다
# ---------------------------------------------------------------------------


def test_failure_is_not_an_exception_and_leaves_a_status_file(tmp_path):
    """원격이 아예 없는 저장소 — 받아오기는 실패하지만 예외는 나지 않고, 상태 파일이
    남는다. 이 두 가지가 "서버는 뜬다"의 실제 내용이다."""
    lonely = tmp_path / "lonely"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(lonely)], check=True, capture_output=True
    )
    _identity(lonely)

    result = startup_sync.startup_pull(lonely)

    assert result["ok"] is False
    status = startup_sync.read_status(lonely)
    assert status is not None
    assert status["ok"] is False
    assert status["step"] == "pull"
    assert status["reason"]


def test_warnings_appear_for_human_and_for_the_web(tmp_path):
    """실패 사실은 로그 한 줄로 흘러가지 않는다 — 브리핑 경고 문단과 recall용 문장
    양쪽에서 다시 나타난다(웹에는 세션 훅이 없어 recall이 유일한 통로다)."""
    home = tmp_path / "home"
    home.mkdir()
    assert startup_sync.warning_markdown(home) is None
    assert startup_sync.warning_text(home) is None

    startup_sync.write_status(home, "pull", "권한 없음(403)", ["받아오기 실패"])

    md = startup_sync.warning_markdown(home)
    assert md is not None and "⚠" in md and "권한 없음(403)" in md
    text = startup_sync.warning_text(home)
    assert text is not None and "권한 없음(403)" in text


def test_status_is_cleared_only_by_a_real_success(repos):
    """경고는 받아오기가 실제로 성공할 때만 사라진다 — 그래야 오래 못 맞춘 채
    굴러가는 상태를 사람이 계속 본다."""
    web = repos["web"]
    startup_sync.write_status(web, "pull", "이전 실패", ["받아오기 실패"])
    assert startup_sync.read_status(web) is not None

    assert startup_sync.startup_pull(web)["ok"] is True
    assert startup_sync.read_status(web) is None


def test_runtime_sync_pull_success_also_clears_the_warning(monkeypatch, repos):
    """시작 때 실패했더라도 런타임 pull이 회복시키면 경고가 사라져야 한다 —
    안 그러면 낡은 경고가 영영 남아 다음번 진짜 실패를 사람이 무시하게 된다."""
    import config as cfg

    web = repos["web"]
    (web / ".namu_sync").write_text("", encoding="utf-8")
    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", web)
    monkeypatch.delenv("NAMU_SYNC", raising=False)
    startup_sync.write_status(web, "pull", "이전 실패", ["받아오기 실패"])

    assert ms.sync_pull() is True
    assert startup_sync.read_status(web) is None


def test_main_returns_nonzero_but_does_not_raise(tmp_path):
    """entrypoint가 부르는 진입점 — 실패해도 예외로 죽지 않고 exit code 3만 준다.
    셸은 그 값으로 경고 한 줄을 찍고 서버 기동을 계속한다."""
    lonely = tmp_path / "lonely2"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(lonely)], check=True, capture_output=True
    )
    _identity(lonely)

    assert startup_sync.main([str(lonely)]) == 3


# ---------------------------------------------------------------------------
# 완료조건 ④ — 되돌아가지 않게 막는다(entrypoint.sh 회귀 검사)
# ---------------------------------------------------------------------------


def _entrypoint_text() -> str:
    return (
        Path(__file__).resolve().parent.parent / "deploy" / "entrypoint.sh"
    ).read_text(encoding="utf-8")


def test_entrypoint_does_not_die_on_pull_failure():
    """받아오기 실패 자리에 `exit`이 다시 들어오면 무한 재시작 사고가 그대로
    되살아난다. 셸은 단위 테스트가 어려우니 이 한 가지만은 글자로 못 박는다."""
    text = _entrypoint_text()
    assert "namu_startup_sync.py" in text

    lines = text.splitlines()
    start = next(
        i for i, ln in enumerate(lines) if "uv run" in ln and "STARTUP_SYNC_SCRIPT" in ln
    )
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "else")
    block = "\n".join(lines[start:end])
    assert "exit" not in block


def test_entrypoint_still_dies_on_clone_failure():
    """clone 실패는 종전대로 치명적이다 — 기억이 하나도 없는 빈 서버가 뜨면 그 위에
    쌓인 기록이 원격 이력과 갈라진다(2026-08-16 사용자 결정)."""
    text = _entrypoint_text()
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if "git clone" in ln)
    block = "\n".join(lines[start:start + 5])
    assert "exit 1" in block


def test_dockerfile_ships_the_startup_script():
    """스크립트를 이미지에 안 넣으면 컨테이너에서만 조용히 실패한다(로컬 테스트는
    전부 통과하는데 배포만 깨지는 자리라 따로 못 박는다)."""
    text = (
        Path(__file__).resolve().parent.parent / "deploy" / "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "deploy/namu_startup_sync.py" in text
