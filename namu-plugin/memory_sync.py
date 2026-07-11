"""~/.namu(namu-35: 데이터 루트 고정, "개발 모드/설치 모드" 구분 폐지) 교훈 저장소의
git 자동 동기화 — record 시 auto commit+push, 세션 시작 훅에서 auto pull.

명시적 활성화(namu_sync_setup으로 마커 파일 생성) 전제.

db.py(코어)와 성격이 다른 인터페이스/훅 레이어 소관이라 stdlib만 사용한다 — 훅들의
PEP 723 의존성 블록을 건드릴 필요가 없게 하기 위함.

subprocess 호출 공통 규약(session_context.check_git_behind와 동일 패턴):
capture_output=True, encoding="utf-8", errors="replace", shell=False, timeout 명시.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path


def sync_enabled() -> bool:
    """자동 동기화 활성 여부. 아래 3개를 전부 충족해야 True.

    1. NAMU_SYNC 환경변수가 "0"이 아님 — 기본 켜짐, 끄기 스위치
       (session_context.check_git_behind의 NAMU_GIT_CHECK=0 패턴과 동일).
    2. NAMU_DATA_ROOT/.namu_sync 마커 파일 존재 — namu_sync_setup으로만 생성되므로
       "명시적 활성화" 전제를 보장한다.
    3. NAMU_DATA_ROOT/.git 존재 — git 저장소로 초기화돼 있어야 pull/push가 의미 있다.

    namu-35: 데이터 루트가 Path.home()/".namu" 고정이 되며 "개발 repo(clone형)를
    가리킬 수 있는 포인터" 자체가 사라졌다 — 그래서 이전에 있던 "NAMU_DATA_ROOT !=
    REPO_ROOT" 하드가드는 지킬 대상이 없어져 삭제했다(더 이상 개발 repo로 오염될
    경로가 존재하지 않는다).

    cfg는 함수 내부에서 import해 테스트가 config 모듈 속성을 monkeypatch로
    격리할 수 있게 한다(session_context.py 관례와 동일).
    """
    import config as cfg

    if os.environ.get("NAMU_SYNC") == "0":
        return False
    if not (cfg.NAMU_DATA_ROOT / ".namu_sync").exists():
        return False
    if not (cfg.NAMU_DATA_ROOT / ".git").exists():
        return False
    return True


def _append_sync_log(line: str, home: "Path | str | None" = None) -> None:
    """동기화 실패/스킵 사유 1줄 기록(물증). record·세션 시작을 절대 막으면 안
    되므로 전예외 무음 처리한다(session_context._append_git_check_log와 동일 원칙 —
    무음 실패가 잠복하지 않도록 사유만은 남긴다).

    home 생략 시 cfg.NAMU_DATA_ROOT(기존 sync_push/sync_pull 호출부와 동일). namu_tasks_push
    CLI(namu-34 ③-b)처럼 대상이 항상 `~/.namu`로 고정된(namu-35 이후로는 cfg.NAMU_DATA_ROOT와
    동일 경로) 호출부도 명시적으로 home을 넘겨 호출 의도를 분명히 한다.
    """
    try:
        if home is None:
            import config as cfg

            home = cfg.NAMU_DATA_ROOT
        path = Path(home) / "db" / "sync.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {line}\n")
    except Exception:
        pass


def sync_pull() -> bool:
    """NAMU_DATA_ROOT에서 git pull(union merge)로 다른 PC의 최신 교훈을 당겨온다.

    세션 시작 훅에서 호출 — 여기서 yaml이 갱신되면 기존 cache_is_stale 로직이
    db를 자동 재생성하므로 이 함수는 pull만 책임진다. 훅을 절대 막지 않도록
    실패·타임아웃·예외 전부 예외를 삼키고 False를 반환한다.
    """
    import config as cfg

    if not sync_enabled():
        return False

    home = str(cfg.NAMU_DATA_ROOT)
    try:
        result = subprocess.run(
            ["git", "-C", home, "pull", "--no-rebase", "--no-edit", "--quiet"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            shell=False,
        )
        if result.returncode != 0:
            _append_sync_log(
                f"PULL FAIL rc={result.returncode} err={(result.stderr or '').strip()[:200]}"
            )
            return False
        return True
    except Exception as exc:
        _append_sync_log(f"PULL FAIL {type(exc).__name__}: {exc}")
        return False


def _run(args: list[str], timeout: int):
    return subprocess.run(
        args,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )


def _add_targets(home: str, required: list[str], optional: list[str]) -> list[str]:
    """git add 대상 목록 조립(namu-34 ③-a). required는 무조건 포함(없으면 git add
    자체가 실패해 물증이 남는 기존 sync_push 회귀를 그대로 유지 — memory/가 없는
    설치는 이미 뭔가 잘못된 상태라 실패로 드러나야 한다). optional은 실재할 때만
    포함한다 — tasks/는 아직 한 번도 안 생겼을 수 있는 신규 환경이라, 없다고 git
    add 자체를 실패시키면 안 되기 때문이다."""
    targets = list(required)
    for rel in optional:
        if (Path(home) / rel.rstrip("/")).exists():
            targets.append(rel)
    return targets


def _push(
    home: str, message: str, required_paths: list[str], optional_paths: list[str]
) -> bool:
    """add(required 전부 + optional 실재분)→(변경 있으면) commit→push 공통 로직.

    sync_push(설치형 자동, namu_record 직후)와 push_tasks_pool(namu_tasks_push CLI,
    namu-34 ③-b)이 이 함수를 공유한다 — 게이팅 조건(sync_enabled 마커+하드가드 vs
    대상 git/origin 실재)만 호출자가 각자 다르게 검사하고, git 호출 시퀀스·재시도·
    로그 규약은 하나로 유지한다(중복 구현 금지).

    변경이 없어도 commit 단계만 건너뛰고 push는 계속 진행한다 — 밀린 커밋을
    flush하는 목적(예: 오프라인 중 쌓인 로컬 커밋을 다음 호출 때 push).
    push 실패 시 pull(--no-rebase, union merge로 충돌 해소)→push 1회만 재시도한다
    (양쪽 PC가 오프라인 상태에서 각자 기록해 divergence가 생긴 경우 복구).
    commit author는 사용자 git 전역 설정을 그대로 쓴다(별도 설정 안 함).
    각 단계 실패는 물증 로그 + False, 예외는 절대 전파하지 않는다(호출자 결과에
    영향 주면 안 됨).
    """
    targets = _add_targets(home, required_paths, optional_paths)

    if targets:
        try:
            add_res = _run(["git", "-C", home, "add", *targets], 5)
            if add_res.returncode != 0:
                _append_sync_log(
                    f"PUSH FAIL add rc={add_res.returncode} err={(add_res.stderr or '').strip()[:200]}",
                    home=home,
                )
                return False
        except Exception as exc:
            _append_sync_log(f"PUSH FAIL add {type(exc).__name__}: {exc}", home=home)
            return False

    try:
        diff_res = _run(["git", "-C", home, "diff", "--cached", "--quiet"], 5)
        has_changes = diff_res.returncode != 0
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL diff-check {type(exc).__name__}: {exc}", home=home)
        return False

    if has_changes:
        try:
            commit_res = _run(["git", "-C", home, "commit", "-m", message], 5)
            if commit_res.returncode != 0:
                _append_sync_log(
                    f"PUSH FAIL commit rc={commit_res.returncode} "
                    f"err={(commit_res.stderr or '').strip()[:200]}",
                    home=home,
                )
                return False
        except Exception as exc:
            _append_sync_log(f"PUSH FAIL commit {type(exc).__name__}: {exc}", home=home)
            return False

    try:
        push_res = _run(["git", "-C", home, "push"], 10)
        if push_res.returncode == 0:
            return True
        _append_sync_log(
            f"PUSH retry-trigger rc={push_res.returncode} "
            f"err={(push_res.stderr or '').strip()[:200]}",
            home=home,
        )
    except Exception as exc:
        _append_sync_log(f"PUSH retry-trigger {type(exc).__name__}: {exc}", home=home)

    # 복구 재시도: divergence를 union merge로 정리한 뒤 1회만 다시 push
    try:
        pull_res = _run(["git", "-C", home, "pull", "--no-rebase", "--no-edit"], 10)
        if pull_res.returncode != 0:
            _append_sync_log(
                f"PUSH FAIL recovery-pull rc={pull_res.returncode} "
                f"err={(pull_res.stderr or '').strip()[:200]}",
                home=home,
            )
            return False
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL recovery-pull {type(exc).__name__}: {exc}", home=home)
        return False

    try:
        retry_res = _run(["git", "-C", home, "push"], 10)
        if retry_res.returncode == 0:
            return True
        _append_sync_log(
            f"PUSH FAIL retry-push rc={retry_res.returncode} "
            f"err={(retry_res.stderr or '').strip()[:200]}",
            home=home,
        )
        return False
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL retry-push {type(exc).__name__}: {exc}", home=home)
        return False


_GITATTRIBUTES_UNION_LINES = [
    "memory/learnings.yaml merge=union",
    # namu-34 ③-c: tasks가 개인 풀(~/.namu/tasks/<프로젝트키>/)로 통합되며 log.md
    # (append-only 사건 기록)와 .project(machine=경로 매핑, 역시 append-only)도
    # 양쪽 PC가 오프라인 중 각자 추가한 줄이 서로를 지우지 않게 union 병합이 필요하다.
    "tasks/**/log.md merge=union",
    "tasks/*/.project merge=union",
]


def ensure_gitattributes_union(home: Path) -> list[str]:
    """`.gitattributes`에 union 병합 라인들을 멱등 ensure한다(namu-34 ③-c).

    있으면 무변경, 없으면 append만 — 신규 개통(sync_setup)과 기존 개통분(hp·samsung,
    서버 부팅 시 mcp_server.py)이 이 함수 하나를 공유해 라인 목록이 어긋나지 않게 한다.
    반환값은 사람이 읽는 notes 리스트(sync_setup 보고용) — 부팅 경로 호출자는 무시해도
    무방하다. 파일 I/O 실패는 예외를 전파하지 않고 notes에 사유만 남긴다.
    """
    gitattributes = home / ".gitattributes"
    notes: list[str] = []
    try:
        existing = gitattributes.read_text(encoding="utf-8") if gitattributes.exists() else ""
        existing_lines = existing.splitlines()
        missing = [ln for ln in _GITATTRIBUTES_UNION_LINES if ln not in existing_lines]
        if missing:
            with gitattributes.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                for ln in missing:
                    f.write(ln + "\n")
            notes.append(f".gitattributes에 {len(missing)}개 union 라인 추가")
        else:
            notes.append(".gitattributes: union 라인 이미 존재 (스킵)")
    except OSError as exc:
        notes.append(f".gitattributes 기록 실패: {exc}")
    return notes


def sync_push(message: str) -> bool:
    """memory/(+실재하면 tasks/, namu-34 ③-a)를 add→(변경 있으면) commit→push.
    namu_record 성공 직후 호출. 실제 git 시퀀스는 `_push()` 참조."""
    import config as cfg

    if not sync_enabled():
        return False

    return _push(str(cfg.NAMU_DATA_ROOT), message, ["memory/"], ["tasks/"])


def tasks_pool_git_ready(home: "Path | str") -> bool:
    """namu_tasks_push CLI 전용 게이팅(namu-34 ③-b) — sync_enabled(마커 파일 게이트)와는
    무관하게, 대상(`~/.namu`) 자체가 git repo이고 origin 원격을 가졌는지만 본다.
    """
    home_path = Path(home)
    if not (home_path / ".git").exists():
        return False
    try:
        remote_res = _run(["git", "-C", str(home_path), "remote", "get-url", "origin"], 5)
    except Exception:
        return False
    return remote_res.returncode == 0


def push_tasks_pool(home: "Path | str", message: str) -> bool:
    """`~/.namu`(개인 풀) 대상 tasks/(+실재하면 memory/) push(namu-34 ③-b, CLI 전용).

    `tasks_pool_git_ready(home)`가 False면(신규 sync 미개통 등) 조용히 no-op으로
    False를 반환한다 — 호출자(namu_tasks_push.py)는 이를 정상 종료(exit 0)로 취급한다.
    """
    if not tasks_pool_git_ready(home):
        return False
    return _push(str(home), message, [], ["tasks/", "memory/"])


def sync_setup(remote_url: str) -> str:
    """~/.namu(NAMU_DATA_ROOT) 교훈 저장소를 git 원격 백업용으로 초기화한다.

    이 함수만 예외적으로 무음이 아니다 — 사람이 읽고 다음 행동(인증 설정 등)을
    판단해야 하는 결과이므로 문자열로 그대로 보고한다.

    원격 repo 자체는 사용자가 미리 준비해야 한다(이 함수는 로컬 wiring만 담당).
    """
    import config as cfg

    home = cfg.NAMU_DATA_ROOT
    home.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    git_dir = home / ".git"
    if git_dir.exists():
        notes.append("git 저장소: 이미 존재 (초기화 스킵)")
    else:
        try:
            init_res = _run(["git", "-C", str(home), "init", "-b", "main"], 10)
            if init_res.returncode == 0:
                notes.append("git init -b main 완료")
            else:
                return f"실패: git init 오류 - {(init_res.stderr or '').strip()[:300]}"
        except Exception as exc:
            return f"실패: git init 예외 - {type(exc).__name__}: {exc}"

    gitignore = home / ".gitignore"
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if "db/" not in existing.splitlines():
            with gitignore.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("db/\n")
            notes.append(".gitignore에 db/ 추가")
        else:
            notes.append(".gitignore: db/ 이미 존재 (스킵)")
    except OSError as exc:
        notes.append(f".gitignore 기록 실패: {exc}")

    notes.extend(ensure_gitattributes_union(home))

    try:
        remote_check = _run(["git", "-C", str(home), "remote", "get-url", "origin"], 5)
        if remote_check.returncode == 0:
            set_res = _run(["git", "-C", str(home), "remote", "set-url", "origin", remote_url], 5)
            notes.append(
                "원격 origin 갱신"
                if set_res.returncode == 0
                else f"원격 갱신 실패: {(set_res.stderr or '').strip()[:200]}"
            )
        else:
            add_res = _run(["git", "-C", str(home), "remote", "add", "origin", remote_url], 5)
            notes.append(
                "원격 origin 추가"
                if add_res.returncode == 0
                else f"원격 추가 실패: {(add_res.stderr or '').strip()[:200]}"
            )
    except Exception as exc:
        notes.append(f"원격 설정 예외: {type(exc).__name__}: {exc}")

    marker = home / ".namu_sync"
    try:
        marker.touch(exist_ok=True)
        notes.append("마커(.namu_sync) 생성 — 이후 자동 pull/push 활성화")
    except OSError as exc:
        notes.append(f"마커 생성 실패: {exc}")

    try:
        add_res = _run(["git", "-C", str(home), "add", "-A"], 10)
        if add_res.returncode != 0:
            notes.append(f"git add -A 실패: {(add_res.stderr or '').strip()[:200]}")
        else:
            diff_res = _run(["git", "-C", str(home), "diff", "--cached", "--quiet"], 5)
            if diff_res.returncode != 0:
                commit_res = _run(
                    ["git", "-C", str(home), "commit", "-m", "namu: sync 초기 설정"], 10
                )
                notes.append(
                    "초기 커밋 완료"
                    if commit_res.returncode == 0
                    else f"초기 커밋 실패: {(commit_res.stderr or '').strip()[:200]}"
                )
            else:
                notes.append("커밋할 변경 없음")
    except Exception as exc:
        notes.append(f"add/commit 예외: {type(exc).__name__}: {exc}")

    # 두 번째 이후 PC가 "클론"이 아니라 "빈 홈에서 독립 init"으로 온보딩하는 경우,
    # 이 시점의 로컬 역사는 원격(이미 A가 push해둔 main)과 공통 조상이 전혀 없다
    # (unrelated histories). 이 상태로 바로 push -u를 하면 non-fast-forward로
    # 거부되고, 그 실패 때문에 upstream이 끝내 등록되지 않아 이후 sync_pull/
    # sync_push가 "tracking information 없음"으로 영구 실패하는 사고가 난다
    # (실측: 2PC 온보딩 라이브 검증). 그래서 push 전에 원격을 fetch해 미리
    # 흡수한다 — --allow-unrelated-histories는 이 1회성 온보딩에만 쓴다
    # (sync_pull/sync_push의 평상 운영에서 unrelated가 뜨면 그건 진짜 사고이므로
    # 무음 병합하면 안 된다 — 그쪽은 절대 이 플래그를 쓰지 않는다).
    try:
        fetch_res = _run(["git", "-C", str(home), "fetch", "origin"], 10)
        if fetch_res.returncode != 0:
            notes.append(
                "원격 fetch 실패(오프라인/인증 미비 등 — push 단계에서 다시 확인): "
                f"{(fetch_res.stderr or '').strip()[:200]}"
            )
        else:
            remote_ref_res = _run(
                ["git", "-C", str(home), "rev-parse", "--verify", "-q", "origin/main"], 5
            )
            if remote_ref_res.returncode != 0:
                notes.append("원격에 main 없음 — 최초 설정으로 간주, 병합 스킵")
            else:
                head_res = _run(["git", "-C", str(home), "rev-parse", "--verify", "-q", "HEAD"], 5)
                if head_res.returncode == 0:
                    merge_res = _run(
                        [
                            "git", "-C", str(home), "merge",
                            "--allow-unrelated-histories", "--no-edit", "origin/main",
                        ],
                        10,
                    )
                    notes.append(
                        "원격 기존 기록과 병합 완료(unrelated-histories, 온보딩 전용)"
                        if merge_res.returncode == 0
                        else f"원격 기록 병합 실패: {(merge_res.stderr or '').strip()[:300]}"
                    )
                else:
                    # 로컬에 커밋이 전혀 없는 예외 경로(위 add/commit이 실패했거나
                    # 애초에 커밋할 변경이 없던 경우) — 병합할 로컬 역사 자체가
                    # 없으므로 원격 main을 그대로 로컬 main으로 채택한다.
                    checkout_res = _run(
                        ["git", "-C", str(home), "checkout", "-B", "main", "origin/main"], 10
                    )
                    notes.append(
                        "로컬 커밋 없음 — 원격 main을 그대로 채택"
                        if checkout_res.returncode == 0
                        else f"원격 main 채택 실패: {(checkout_res.stderr or '').strip()[:300]}"
                    )
    except Exception as exc:
        notes.append(f"fetch/병합 예외: {type(exc).__name__}: {exc}")

    try:
        push_res = _run(["git", "-C", str(home), "push", "-u", "origin", "main"], 10)
        if push_res.returncode == 0:
            notes.append("push 완료")
        else:
            notes.append(
                "push 실패(인증 미비 등 사용자가 해결할 문제 — 다음 record가 재시도): "
                f"{(push_res.stderr or '').strip()[:300]}"
            )
    except Exception as exc:
        notes.append(f"push 예외: {type(exc).__name__}: {exc}")

    return "namu_sync_setup 완료:\n- " + "\n- ".join(notes)
