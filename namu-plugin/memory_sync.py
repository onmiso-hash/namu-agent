"""설치형(~/.namu) 교훈 저장소의 git 자동 동기화 — record 시 auto commit+push,
세션 시작 훅에서 auto pull.

명시적 활성화(namu_sync_setup으로 마커 파일 생성) 전제. 개발 repo(clone형, config.py의
NAMU_HOME이 REPO_ROOT로 폴백되는 경우)에서는 마커가 있어도 절대 발동하지 않는다 —
그 경로는 이미 사람이 직접 git pull/push로 관리하는 대상이라, 자동 push가 끼어들면
사용자 모르게 커밋/강제 상태가 만들어지는 사고가 된다(하드가드, sync_enabled 참조).

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
    """설치형 자동 동기화 활성 여부. 아래 4개를 전부 충족해야 True.

    1. NAMU_SYNC 환경변수가 "0"이 아님 — 기본 켜짐, 끄기 스위치
       (session_context.check_git_behind의 NAMU_GIT_CHECK=0 패턴과 동일).
    2. NAMU_HOME/.namu_sync 마커 파일 존재 — namu_sync_setup으로만 생성되므로
       "명시적 활성화" 전제를 보장한다.
    3. NAMU_HOME != REPO_ROOT — 하드가드. config.py는 REPO_ROOT/memory가 실재하면
       NAMU_HOME을 REPO_ROOT로 폴백시키는데(클론해 직접 실행하는 개발 환경), 이
       경로는 이미 기존 repo git으로 관리되는 대상이다. 마커가 실수로 남아있어도
       auto-push가 그 repo에 조용히 끼어드는 사고를 여기서 원천 차단한다.
    4. NAMU_HOME/.git 존재 — git 저장소로 초기화돼 있어야 pull/push가 의미 있다.

    cfg는 함수 내부에서 import해 테스트가 config 모듈 속성을 monkeypatch로
    격리할 수 있게 한다(session_context.py 관례와 동일).
    """
    import config as cfg

    if os.environ.get("NAMU_SYNC") == "0":
        return False
    if not (cfg.NAMU_HOME / ".namu_sync").exists():
        return False
    if cfg.NAMU_HOME == cfg.REPO_ROOT:
        return False
    if not (cfg.NAMU_HOME / ".git").exists():
        return False
    return True


def _append_sync_log(line: str) -> None:
    """동기화 실패/스킵 사유 1줄 기록(물증). record·세션 시작을 절대 막으면 안
    되므로 전예외 무음 처리한다(session_context._append_git_check_log와 동일 원칙 —
    무음 실패가 잠복하지 않도록 사유만은 남긴다)."""
    try:
        import config as cfg

        path = cfg.NAMU_HOME / "db" / "sync.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {line}\n")
    except Exception:
        pass


def sync_pull() -> bool:
    """NAMU_HOME에서 git pull(union merge)로 다른 PC의 최신 교훈을 당겨온다.

    세션 시작 훅에서 호출 — 여기서 yaml이 갱신되면 기존 cache_is_stale 로직이
    db를 자동 재생성하므로 이 함수는 pull만 책임진다. 훅을 절대 막지 않도록
    실패·타임아웃·예외 전부 예외를 삼키고 False를 반환한다.
    """
    import config as cfg

    if not sync_enabled():
        return False

    home = str(cfg.NAMU_HOME)
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


def sync_push(message: str) -> bool:
    """memory/를 add→(변경 있으면) commit→push. namu_record 성공 직후 호출.

    변경이 없어도 commit 단계만 건너뛰고 push는 계속 진행한다 — 밀린 커밋을
    flush하는 목적(예: 오프라인 중 쌓인 로컬 커밋을 다음 record 때 push).
    push 실패 시 pull(--no-rebase, union merge로 충돌 해소)→push 1회만 재시도한다
    (양쪽 PC가 오프라인 상태에서 각자 기록해 divergence가 생긴 경우 복구).
    commit author는 사용자 git 전역 설정을 그대로 쓴다(별도 설정 안 함).
    각 단계 실패는 물증 로그 + False, 예외는 절대 전파하지 않는다(record 결과에
    영향 주면 안 됨).
    """
    import config as cfg

    if not sync_enabled():
        return False

    home = str(cfg.NAMU_HOME)

    try:
        add_res = _run(["git", "-C", home, "add", "memory/"], 5)
        if add_res.returncode != 0:
            _append_sync_log(
                f"PUSH FAIL add rc={add_res.returncode} err={(add_res.stderr or '').strip()[:200]}"
            )
            return False
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL add {type(exc).__name__}: {exc}")
        return False

    try:
        diff_res = _run(["git", "-C", home, "diff", "--cached", "--quiet"], 5)
        has_changes = diff_res.returncode != 0
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL diff-check {type(exc).__name__}: {exc}")
        return False

    if has_changes:
        try:
            commit_res = _run(["git", "-C", home, "commit", "-m", message], 5)
            if commit_res.returncode != 0:
                _append_sync_log(
                    f"PUSH FAIL commit rc={commit_res.returncode} "
                    f"err={(commit_res.stderr or '').strip()[:200]}"
                )
                return False
        except Exception as exc:
            _append_sync_log(f"PUSH FAIL commit {type(exc).__name__}: {exc}")
            return False

    try:
        push_res = _run(["git", "-C", home, "push"], 10)
        if push_res.returncode == 0:
            return True
        _append_sync_log(
            f"PUSH retry-trigger rc={push_res.returncode} "
            f"err={(push_res.stderr or '').strip()[:200]}"
        )
    except Exception as exc:
        _append_sync_log(f"PUSH retry-trigger {type(exc).__name__}: {exc}")

    # 복구 재시도: divergence를 union merge로 정리한 뒤 1회만 다시 push
    try:
        pull_res = _run(["git", "-C", home, "pull", "--no-rebase", "--no-edit"], 10)
        if pull_res.returncode != 0:
            _append_sync_log(
                f"PUSH FAIL recovery-pull rc={pull_res.returncode} "
                f"err={(pull_res.stderr or '').strip()[:200]}"
            )
            return False
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL recovery-pull {type(exc).__name__}: {exc}")
        return False

    try:
        retry_res = _run(["git", "-C", home, "push"], 10)
        if retry_res.returncode == 0:
            return True
        _append_sync_log(
            f"PUSH FAIL retry-push rc={retry_res.returncode} "
            f"err={(retry_res.stderr or '').strip()[:200]}"
        )
        return False
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL retry-push {type(exc).__name__}: {exc}")
        return False


def sync_setup(remote_url: str) -> str:
    """설치형(~/.namu) 교훈 저장소를 git 원격 백업용으로 초기화한다.

    이 함수만 예외적으로 무음이 아니다 — 사람이 읽고 다음 행동(인증 설정 등)을
    판단해야 하는 결과이므로 문자열로 그대로 보고한다.

    개발 repo(NAMU_HOME == REPO_ROOT)는 거부한다 — 그 경로는 이미 기존 repo의
    git pull/push로 동기화되는 대상이라 별도 초기화가 오히려 사고를 만든다.
    원격 repo 자체는 사용자가 미리 준비해야 한다(이 함수는 로컬 wiring만 담당).
    """
    import config as cfg

    if cfg.NAMU_HOME == cfg.REPO_ROOT:
        return (
            "거부: NAMU_HOME이 개발 repo(REPO_ROOT)와 같습니다. 이 환경은 이미 "
            "기존 repo의 git pull/push로 동기화하세요. namu_sync_setup은 "
            "설치형(~/.namu 등 분리된 데이터 루트) 전용입니다."
        )

    home = cfg.NAMU_HOME
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

    gitattributes = home / ".gitattributes"
    union_line = "memory/learnings.yaml merge=union"
    try:
        existing = gitattributes.read_text(encoding="utf-8") if gitattributes.exists() else ""
        if union_line not in existing.splitlines():
            with gitattributes.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(union_line + "\n")
            notes.append(".gitattributes에 merge=union 추가")
        else:
            notes.append(".gitattributes: merge=union 이미 존재 (스킵)")
    except OSError as exc:
        notes.append(f".gitattributes 기록 실패: {exc}")

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
