"""memory_sync.py 단위/실전 테스트.

sync_enabled 관련 조건 분기는 config 모듈 속성을 직접 monkeypatch한다
(test_hook_stale_rebuild.py·test_session_context.py와 동일 관례 — memory_sync가
함수 내부에서 `import config as cfg`로 매번 같은 캐시된 모듈 객체를 조회하므로,
그 모듈 객체의 속성을 덮어쓰면 그대로 반영된다).

NAMU_SYNC 환경변수는 os.environ을 직접 읽으므로(NAMU_GIT_CHECK 패턴과 동일)
monkeypatch.setenv/delenv로 다룬다. 실전 git 시나리오는 실제 git 명령을 그대로
사용하되, 테스트 repo에는 로컬(--global 아님) git config로 user.name/email을
심어 CI 환경의 전역 git 설정 유무에 의존하지 않는다.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import memory_sync as ms


@pytest.fixture(autouse=True)
def _clean_namu_sync_env(monkeypatch):
    """다른 테스트나 실제 셸 환경에 NAMU_SYNC가 남아있어도 각 테스트는 깨끗한
    기본값(미설정=켜짐)에서 시작하게 한다."""
    monkeypatch.delenv("NAMU_SYNC", raising=False)


def _init_git_repo(path: Path) -> None:
    """path에 git 저장소를 만들고 로컬 user.name/email을 심는다(전역 설정 무의존)."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        check=True, capture_output=True,
    )


def _commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        check=True, capture_output=True,
    )


def _read_yaml(path: Path) -> str:
    return (path / "memory" / "learnings.yaml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# sync_enabled
# ---------------------------------------------------------------------------

def test_sync_enabled_false_without_marker(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _init_git_repo(home)
    monkeypatch.setattr(cfg, "NAMU_HOME", home)
    assert ms.sync_enabled() is False


def test_sync_enabled_false_when_namu_sync_zero(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)
    monkeypatch.setenv("NAMU_SYNC", "0")
    assert ms.sync_enabled() is False


def test_sync_enabled_false_when_home_equals_repo_root(monkeypatch, tmp_path):
    """개발 repo(클론형) 하드가드 — 마커가 있어도 NAMU_HOME==REPO_ROOT면 절대 False."""
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)
    monkeypatch.setattr(cfg, "REPO_ROOT", home)
    assert ms.sync_enabled() is False


def test_sync_enabled_true_when_all_conditions_met(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)
    assert ms.sync_enabled() is True


# ---------------------------------------------------------------------------
# sync_pull / sync_push — 실패 경로(비정상 git 상태) 물증 로그
# ---------------------------------------------------------------------------

def test_sync_pull_without_marker_returns_false_silently(monkeypatch, tmp_path):
    """마커가 없으면 sync_enabled()이 False라 로그 없이 조용히 실패한다."""
    home = tmp_path / "home"
    _init_git_repo(home)
    monkeypatch.setattr(cfg, "NAMU_HOME", home)

    assert ms.sync_pull() is False
    assert not (home / "db" / "sync.log").exists()


def test_sync_pull_git_repo_without_remote_logs_failure(monkeypatch, tmp_path):
    """sync_enabled 조건은 충족(마커+.git)하지만 remote/upstream이 없는 git 저장소 —
    실제 git pull이 실패하며 사유가 db/sync.log에 남고 예외는 전파되지 않는다."""
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / "README.md").write_text("x", encoding="utf-8")
    _commit_all(home, "init")
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)

    assert ms.sync_pull() is False
    log = (home / "db" / "sync.log").read_text(encoding="utf-8")
    assert "PULL FAIL" in log


def test_sync_push_git_repo_without_memory_dir_logs_failure(monkeypatch, tmp_path):
    """memory/ 폴더 자체가 없는 git 저장소 — git add memory/가 실패하며 사유가
    로그에 남고 예외는 전파되지 않는다."""
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / "README.md").write_text("x", encoding="utf-8")
    _commit_all(home, "init")
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)

    assert ms.sync_push("test message") is False
    log = (home / "db" / "sync.log").read_text(encoding="utf-8")
    assert "PUSH FAIL" in log


# ---------------------------------------------------------------------------
# sync_push add 범위 확장(namu-34 ③-a) — tasks/ 실재 시 커밋에 포함
# ---------------------------------------------------------------------------

def test_sync_push_includes_tasks_dir_when_present(monkeypatch, tmp_path):
    """tasks/가 실재하면 memory/와 함께 add 대상에 포함돼 커밋·push된다."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    home = tmp_path / "home"
    _init_git_repo(home)
    (home / "README.md").write_text("x", encoding="utf-8")
    _commit_all(home, "init")
    subprocess.run(
        ["git", "-C", str(home), "remote", "add", "origin", str(bare)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(home), "push", "-q", "-u", "origin", "main"],
        check=True, capture_output=True,
    )
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)

    (home / "memory").mkdir()
    (home / "memory" / "learnings.yaml").write_text("---\nid: FAKE0001\n", encoding="utf-8")
    (home / "tasks" / "proj-a").mkdir(parents=True)
    (home / "tasks" / "proj-a" / "log.md").write_text("# log\n[시작] ...\n", encoding="utf-8")

    assert ms.sync_push("learn: with tasks") is True

    show = subprocess.run(
        ["git", "-C", str(home), "show", "--stat", "--name-only", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    assert "tasks/proj-a/log.md" in show.stdout
    assert "memory/learnings.yaml" in show.stdout


def test_sync_push_add_scope_unaffected_when_tasks_dir_absent(monkeypatch, tmp_path):
    """tasks/가 없는(신규 환경) 상태에서도 add가 실패하지 않고 memory/만 정상 커밋된다
    (namu-34 ③-a — tasks/ 부재가 add 자체를 실패시키면 안 된다는 요구 확인)."""
    home = tmp_path / "home"
    _init_git_repo(home)
    (home / ".namu_sync").touch()
    monkeypatch.setattr(cfg, "NAMU_HOME", home)

    (home / "memory").mkdir()
    (home / "memory" / "learnings.yaml").write_text("---\nid: FAKE0001\n", encoding="utf-8")

    # push 자체는 원격이 없어 결국 False가 되지만(재시도까지 소진), commit은
    # add/diff/commit 단계에서 이미 끝나 있어야 한다(tasks/ 부재로 add가 실패하면
    # 애초에 commit 전 단계에서 False가 나 log에 "PUSH FAIL add"가 남는다).
    ms.sync_push("learn: no tasks dir")
    log_path = home / "db" / "sync.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert "PUSH FAIL add" not in log

    show = subprocess.run(
        ["git", "-C", str(home), "log", "--oneline"],
        check=True, capture_output=True, text=True,
    )
    assert "learn: no tasks dir" in show.stdout


# ---------------------------------------------------------------------------
# .gitattributes union ensure 멱등성(namu-34 ③-c)
# ---------------------------------------------------------------------------

def test_ensure_gitattributes_union_appends_all_lines(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    notes = ms.ensure_gitattributes_union(home)

    content = (home / ".gitattributes").read_text(encoding="utf-8")
    assert "memory/learnings.yaml merge=union" in content
    assert "tasks/**/log.md merge=union" in content
    assert "tasks/*/.project merge=union" in content
    assert any("추가" in n for n in notes)


def test_ensure_gitattributes_union_idempotent_on_second_call(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    ms.ensure_gitattributes_union(home)
    content_after_first = (home / ".gitattributes").read_text(encoding="utf-8")

    notes_second = ms.ensure_gitattributes_union(home)
    content_after_second = (home / ".gitattributes").read_text(encoding="utf-8")

    assert content_after_first == content_after_second
    assert any("이미 존재" in n for n in notes_second)


def test_ensure_gitattributes_union_preserves_unrelated_existing_lines(tmp_path):
    """이미 다른 관례로 .gitattributes를 쓰고 있어도 기존 줄은 건드리지 않고
    누락된 union 라인만 append한다."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitattributes").write_text("*.png binary\n", encoding="utf-8")

    ms.ensure_gitattributes_union(home)

    content = (home / ".gitattributes").read_text(encoding="utf-8")
    assert "*.png binary" in content
    assert "tasks/**/log.md merge=union" in content


# ---------------------------------------------------------------------------
# namu_tasks_push CLI 전용 게이팅·push(namu-34 ③-b) — 함수 단위
# ---------------------------------------------------------------------------

def test_tasks_pool_git_ready_false_when_not_git_repo(tmp_path):
    home = tmp_path / "not_a_repo"
    home.mkdir()
    assert ms.tasks_pool_git_ready(home) is False


def test_tasks_pool_git_ready_false_when_no_origin_remote(tmp_path):
    home = tmp_path / "repo"
    _init_git_repo(home)
    assert ms.tasks_pool_git_ready(home) is False


def test_tasks_pool_git_ready_true_when_origin_configured(tmp_path):
    home = tmp_path / "repo"
    _init_git_repo(home)
    subprocess.run(
        ["git", "-C", str(home), "remote", "add", "origin", "https://example.invalid/x.git"],
        check=True, capture_output=True,
    )
    assert ms.tasks_pool_git_ready(home) is True


def test_push_tasks_pool_noop_returns_false_when_not_ready(tmp_path):
    home = tmp_path / "not_a_repo"
    home.mkdir()
    assert ms.push_tasks_pool(home, "tasks: sync") is False


def test_push_tasks_pool_pushes_tasks_and_memory_to_bare_remote(tmp_path):
    """tasks/(+실재하는 memory/)가 실제 bare 원격까지 도착하는지 종단 검증."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    home = tmp_path / "home"
    _init_git_repo(home)
    (home / "README.md").write_text("x", encoding="utf-8")
    _commit_all(home, "init")
    subprocess.run(
        ["git", "-C", str(home), "remote", "add", "origin", str(bare)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(home), "push", "-q", "-u", "origin", "main"],
        check=True, capture_output=True,
    )

    (home / "tasks" / "proj-a").mkdir(parents=True)
    (home / "tasks" / "proj-a" / "log.md").write_text("# log\n[시작] ...\n", encoding="utf-8")
    (home / "memory").mkdir()
    (home / "memory" / "learnings.yaml").write_text("---\nid: FAKE0001\n", encoding="utf-8")

    assert ms.push_tasks_pool(home, "tasks: sync") is True

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    assert (clone / "tasks" / "proj-a" / "log.md").exists()
    assert (clone / "memory" / "learnings.yaml").exists()


# ---------------------------------------------------------------------------
# 실전 git 시나리오 — bare 원격 + 두 클론
# ---------------------------------------------------------------------------

def test_setup_push_reaches_other_clone_via_pull(monkeypatch, tmp_path):
    """① setup 후 memory/learnings.yaml append → sync_push → 다른 클론에서
    pull로 내용 도착 확인."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True,
    )

    home_a = tmp_path / "a"
    _init_git_repo(home_a)
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "machine-a")

    result = ms.sync_setup(str(bare))
    assert "push 완료" in result
    assert (home_a / ".namu_sync").exists()
    assert (home_a / ".gitignore").read_text(encoding="utf-8").splitlines() == ["db/"]
    assert "memory/learnings.yaml merge=union" in (
        home_a / ".gitattributes"
    ).read_text(encoding="utf-8")

    # 다른 PC의 클론 — 마커를 심어 sync_pull 대상으로 만든다.
    home_b = tmp_path / "b"
    subprocess.run(
        ["git", "clone", "-q", str(bare), str(home_b)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(home_b), "config", "user.email", "b@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(home_b), "config", "user.name", "B"],
        check=True, capture_output=True,
    )
    (home_b / ".namu_sync").touch()

    # a에서 새 교훈 append 후 push (memory/는 실제 db.record가 최초 기록 시
    # mkdir하는데, sync_setup은 그 디렉터리 생성까지는 책임지지 않으므로 테스트가 만든다).
    (home_a / "memory").mkdir(exist_ok=True)
    (home_a / "memory" / "learnings.yaml").write_text(
        "---\nid: FAKE0001\ntask: t\n", encoding="utf-8"
    )
    assert ms.sync_push("learn: 테스트 교훈 (machine-a)") is True

    # b에서 pull하면 도착해야 한다.
    monkeypatch.setattr(cfg, "NAMU_HOME", home_b)
    assert ms.sync_pull() is True
    assert "FAKE0001" in _read_yaml(home_b)


def test_sync_push_recovers_from_divergence_via_union_merge(monkeypatch, tmp_path):
    """② 양쪽 divergence(각자 learnings.yaml append+commit) → 한쪽 push 성공,
    다른 쪽은 sync_push 내부 pull(union merge)→재push로 성공. 최종 yaml에
    양쪽 항목이 모두 존재해야 한다."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True,
    )

    base = tmp_path / "base"
    _init_git_repo(base)
    (base / "memory").mkdir()
    (base / "memory" / "learnings.yaml").write_text("---\nid: BASE0000\n", encoding="utf-8")
    (base / ".gitattributes").write_text(
        "memory/learnings.yaml merge=union\n", encoding="utf-8"
    )
    _commit_all(base, "base")
    subprocess.run(
        ["git", "-C", str(base), "remote", "add", "origin", str(bare)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(base), "push", "-q", "-u", "origin", "main"],
        check=True, capture_output=True,
    )

    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    for home in (home_a, home_b):
        subprocess.run(
            ["git", "clone", "-q", str(bare), str(home)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(home), "config", "user.email", f"{home.name}@example.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(home), "config", "user.name", home.name],
            check=True, capture_output=True,
        )
        (home / ".namu_sync").touch()

    # 각자 오프라인 상태로 독립 append + commit (아직 push 안 함).
    (home_a / "memory" / "learnings.yaml").write_text(
        "---\nid: BASE0000\n---\nid: FROM_A\n", encoding="utf-8"
    )
    _commit_all(home_a, "from a")

    (home_b / "memory" / "learnings.yaml").write_text(
        "---\nid: BASE0000\n---\nid: FROM_B\n", encoding="utf-8"
    )
    _commit_all(home_b, "from b")

    # a가 먼저 push — fast-forward라 그냥 성공.
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    assert ms.sync_push("learn: from a") is True

    # b는 origin과 갈라진 상태 — 최초 push 실패 → 내부 pull(union)→재push로 성공해야 함.
    monkeypatch.setattr(cfg, "NAMU_HOME", home_b)
    assert ms.sync_push("learn: from b") is True

    merged = _read_yaml(home_b)
    assert "FROM_A" in merged
    assert "FROM_B" in merged

    # a도 pull하면 b가 추가한 내용까지 받아야 한다(양쪽 최종 상태 일치 확인).
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    assert ms.sync_pull() is True
    merged_a = _read_yaml(home_a)
    assert "FROM_A" in merged_a
    assert "FROM_B" in merged_a


def test_sync_setup_onboards_second_pc_from_truly_empty_home(monkeypatch, tmp_path):
    """namu-30 라이브 실측 FAIL 재현·수정 검증 — 두 번째 PC는 클론이 아니라
    완전히 빈 디렉터리에서 namu_sync_setup을 직접 호출한다. 이때 로컬 초기 커밋
    (.gitignore/.gitattributes)은 원격(A가 이미 push해둔 main)과 공통 조상이
    없는 unrelated-histories 상태다. fetch+merge(--allow-unrelated-histories,
    온보딩 전용) 없이 push -u를 바로 하면 non-fast-forward로 거부되고 upstream이
    끝내 등록되지 않아, 이후 sync_pull/sync_push가 "tracking information 없음"
    으로 영구 실패한다 — 이 테스트는 그 실패가 재현되지 않음을 검증한다.
    """
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    home_a = tmp_path / "a"
    _init_git_repo(home_a)
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "machine-a")
    assert "push 완료" in ms.sync_setup(str(bare))

    (home_a / "memory").mkdir(exist_ok=True)
    (home_a / "memory" / "learnings.yaml").write_text("---\nid: FROM_A\n", encoding="utf-8")
    assert ms.sync_push("learn: from a") is True

    # 홈B — git init조차 안 된 완전히 빈 디렉터리(클론 아님). sync_setup이 내부에서
    # 직접 git init+commit을 수행하므로, 사전에 로컬 config를 심어둘 지점이 없다 —
    # CI 전역 git config에 의존하지 않도록 이 프로세스 한정 GIT_AUTHOR/COMMITTER
    # 환경변수로 커밋 신원을 준다(로컬 config를 강제하는 게 아니라 무의존 확인 목적).
    home_b = tmp_path / "b"
    home_b.mkdir()
    monkeypatch.setenv("GIT_AUTHOR_NAME", "B")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "b@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "B")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "b@example.com")
    monkeypatch.setattr(cfg, "NAMU_HOME", home_b)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "machine-b")

    setup_b = ms.sync_setup(str(bare))
    assert "push 완료" in setup_b
    assert "병합" in setup_b or "채택" in setup_b  # fetch+merge/checkout 단계가 실행됐는지 확인

    assert "FROM_A" in _read_yaml(home_b)

    (home_b / "memory" / "learnings.yaml").write_text(
        "---\nid: FROM_A\n---\nid: FROM_B\n", encoding="utf-8"
    )
    assert ms.sync_push("learn: from b") is True

    # upstream이 실제로 등록됐는지 — 원격에 B의 커밋까지 도착했는지 A가 pull로 확인.
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    assert ms.sync_pull() is True
    assert "FROM_B" in _read_yaml(home_a)


def test_sync_setup_merges_pre_existing_local_learnings_via_unrelated_histories(
    monkeypatch, tmp_path
):
    """변형 — 홈에 이미 로컬 교훈(설치 직후부터 기록해온 커밋)이 있는 상태에서
    뒤늦게 setup을 부르는 실사용 패턴. git init은 스킵되지만(이미 .git 존재)
    fetch+merge(--allow-unrelated-histories)로 원격 기존 기록과 합쳐져야 한다."""
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    home_a = tmp_path / "a"
    _init_git_repo(home_a)
    monkeypatch.setattr(cfg, "NAMU_HOME", home_a)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "machine-a")
    assert "push 완료" in ms.sync_setup(str(bare))
    (home_a / "memory").mkdir(exist_ok=True)
    (home_a / "memory" / "learnings.yaml").write_text("---\nid: FROM_A\n", encoding="utf-8")
    assert ms.sync_push("learn: from a") is True

    # 홈B — 이미 로컬에 자기만의 교훈 + 커밋이 있는 상태(git init 이미 완료).
    home_b = tmp_path / "b"
    _init_git_repo(home_b)
    (home_b / "memory").mkdir()
    (home_b / "memory" / "learnings.yaml").write_text("---\nid: FROM_B_LOCAL\n", encoding="utf-8")
    _commit_all(home_b, "local learning before setup")

    monkeypatch.setattr(cfg, "NAMU_HOME", home_b)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "machine-b")
    setup_b = ms.sync_setup(str(bare))
    assert "push 완료" in setup_b
    assert "병합" in setup_b
    assert "git 저장소: 이미 존재" in setup_b  # init은 스킵됐음을 재확인

    merged = _read_yaml(home_b)
    assert "FROM_A" in merged
    assert "FROM_B_LOCAL" in merged


def test_sync_setup_rejects_when_namu_home_equals_repo_root(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "NAMU_HOME", cfg.REPO_ROOT)
    result = ms.sync_setup("git@example.com:user/repo.git")
    assert result.startswith("거부")


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
