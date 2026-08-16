"""컨테이너 시작 시 ~/.namu를 원격과 맞추는 절차 — 실패해도 서버를 죽이지 않는다
(namu-entrypoint-pull-resilience).

계기(2026-08-16 실사고): `deploy/entrypoint.sh`가 시작 시 `git pull`에 실패하면
`exit 1`로 끝냈고, 도커 재시작 정책이 `always`라 그대로 무한 재시작 루프가 됐다.
`namu-remote-mcp` 컨테이너가 14회 재시작하며 반나절 넘게 502였는데, 실제 원인은
저장 도중 끊겨 커밋 안 된 채 남은 파일 2개뿐이었다 — 기억을 읽고 쓰는 기능 자체는
멀쩡했다. 받아오기는 "있으면 좋은 것"인데 "없으면 죽는 것"으로 짜여 있던 게 결함이다.

그래서 이 모듈의 계약은 셋이다.

1. **막지 않는다** — 어떤 단계가 실패해도 예외를 밖으로 내보내지 않고 결과 dict만
   돌려준다. 호출자(entrypoint)는 그걸 보고 경고만 찍고 서버를 띄운다.
2. **버리지 않는다** — 커밋 안 된 변경은 사용자의 기억이다. 사람이 사고 때 손으로
   한 `git reset --hard`(=기억 버리기)를 스크립트가 자동으로 하면 안 된다. 대신
   커밋해서 보존한 뒤 받아온다(2026-08-16 사용자 결정).
3. **조용히 넘어가지 않는다** — 실패하면 `db/startup_sync.json`에 상태를 남긴다.
   이 파일은 받아오기가 실제로 성공할 때까지 지워지지 않고, 세션 브리핑과
   `namu_recall` 반환에 경고로 계속 뜬다. 로그 한 줄은 흘러가 버리기 때문이다.

`memory_sync.sync_pull()`(런타임 디바운스 pull)과 역할이 다르다 — 저쪽은 이미
전예외를 삼키고 있어 사고와 무관했고, 이쪽은 잠금 청소·미커밋 보존·충돌 되돌리기까지
하는 "시작 한 번" 절차다. subprocess 호출은 `memory_sync._run`을 그대로 빌려 쓴다
(stdin=DEVNULL 등 공통 규약을 두 벌로 만들면 한쪽만 낡는다 — namu-38 규약 참조).
"""
import json
import sys
import time
from pathlib import Path

import memory_sync

# 오래된 잠금 파일 판정 기준(초). 컨테이너가 재시작 루프에 빠지면 30초마다 git을
# 잡았다 죽어서 `.git/**/*.lock`이 남는다 — 사고 때 실제로 `.git/refs/heads/main.lock`과
# 하루 지난 `.git/gc.pid.lock`이 남아 사람이 손으로 지워야 했다. 나이 기준을 두는
# 이유는 "지금 돌고 있는 git"의 잠금을 뺏지 않기 위해서다. 컨테이너 안은 단일
# 프로세스라 시작 시점에 남의 git이 돌 일은 사실상 없지만, 이 함수는 개인 PC의
# ~/.namu에도 그대로 쓰일 수 있어 안전 쪽으로 둔다.
STALE_LOCK_AGE_SECONDS = 3600

# 받아오기 전 커밋해 둘 대상 — memory_sync._push와 같은 목록을 쓴다. `git add -A`를
# 쓰지 않는 이유: ~/.namu는 첨부 폴더(attach_file/)를 sparse-checkout으로 격리해 두고
# 있어서, 전체 add는 격리 규칙과 부딪힐 여지가 있다. 셋 다 optional인 이유는 아직
# 아무것도 안 생긴 신규 환경에서 `git add`가 대상 부재로 실패하면 안 되기 때문이다.
_COMMIT_TARGETS = ["memory/", "tasks/", ".gitattributes"]

_STATUS_FILENAME = "startup_sync.json"


def status_path(home: "Path | str") -> Path:
    """받아오기 실패 상태 파일 경로. `db/` 아래에 두는 이유는 sync.log·git_check.log와
    같은 성격(기기별 물증, git 추적 대상 아님)이기 때문이다 — 이 파일이 원격으로
    따라가면 A PC의 실패가 B PC 화면에 뜬다."""
    return Path(home) / "db" / _STATUS_FILENAME


def read_status(home: "Path | str") -> "dict | None":
    """실패 상태를 읽는다. 정상이면 None(파일 자체가 없음).

    읽기 실패·깨진 JSON도 None으로 삼킨다 — 이 함수는 세션 브리핑과 recall 안에서
    불리므로, 여기서 예외가 나면 기억 조회 전체가 막힌다."""
    try:
        raw = status_path(home).read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def clear_status(home: "Path | str") -> None:
    """받아오기가 실제로 성공했을 때만 부른다 — 경고를 지우는 유일한 길이다."""
    try:
        status_path(home).unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def write_status(home: "Path | str", step: str, reason: str, steps: list[str]) -> None:
    """실패 상태를 기록한다. 상태 파일 쓰기가 실패해도 시작을 막지 않는다(전예외 무음)
    — 다만 sync.log에는 어차피 같은 사유가 남는다."""
    import config as cfg

    payload = {
        "ok": False,
        "at": cfg.now().strftime("%Y-%m-%d %H:%M:%S"),
        "machine": cfg.NAMU_MACHINE,
        "step": step,
        "reason": reason[:500],
        "steps": steps,
    }
    try:
        path = status_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def warning_markdown(home: "Path | str") -> "str | None":
    """세션 브리핑에 실을 경고 문단. 정상이면 None.

    브리핑의 다른 경고들(`### ⚠ 원격 미동기화 …`)과 같은 모양을 쓴다 — 사람이 이미
    그 자리를 경고 칸으로 알고 있기 때문이다."""
    status = read_status(home)
    if not status:
        return None
    at = status.get("at", "?")
    step = status.get("step", "?")
    reason = (status.get("reason") or "").strip()
    return (
        f"### ⚠ 기억 저장소 받아오기 실패 — {at} ({step})\n\n"
        f"이 기기의 `~/.namu`가 원격과 맞지 않은 채 굴러가고 있습니다. "
        f"기억을 읽고 쓰는 것은 됩니다 — 다른 기기와의 동기화만 멈춰 있습니다.\n"
        f"오래 두면 나중 충돌이 커집니다.\n\n"
        f"사유: `{reason or '기록 없음'}`\n"
    )


def warning_text(home: "Path | str") -> "str | None":
    """`namu_recall` 반환에 실을 한 문단(웹용). 웹에는 세션 시작 훅이 없어서 recall
    반환이 사람에게 닿는 유일한 통로다 — 사고를 겪은 자리가 정확히 웹 컨테이너였다."""
    status = read_status(home)
    if not status:
        return None
    at = status.get("at", "?")
    reason = (status.get("reason") or "").strip()
    return (
        f"기억 저장소 받아오기 실패({at}) — 이 서버의 기억이 원격과 맞지 않은 채 "
        f"굴러가고 있습니다. 읽기·쓰기는 되지만 다른 기기와의 동기화가 멈춰 있으니 "
        f"사용자에게 알리세요. 사유: {reason or '기록 없음'}"
    )


def _git_lock_files(home: "Path | str") -> list[Path]:
    """`.git` 아래 모든 `*.lock`. 바로 아래만 보면 안 되는 게 이 함수의 존재 이유다 —
    사고 때 사람을 두 번 막은 `refs/heads/main.lock`이 하위 폴더에 있었다."""
    git_dir = Path(home) / ".git"
    if not git_dir.is_dir():
        return []
    try:
        return sorted(p for p in git_dir.rglob("*.lock") if p.is_file())
    except Exception:
        return []


def clear_stale_git_locks(
    home: "Path | str", max_age_seconds: float = STALE_LOCK_AGE_SECONDS
) -> list[str]:
    """나이가 max_age_seconds를 넘긴 git 잠금 파일만 지우고, 지운 경로 목록을 돌려준다.

    갓 생긴 잠금은 손대지 않는다 — 그건 지금 돌고 있는 git의 것일 수 있다."""
    removed: list[str] = []
    now = time.time()
    for lock in _git_lock_files(home):
        try:
            age = now - lock.stat().st_mtime
        except Exception:
            continue
        if age < max_age_seconds:
            continue
        try:
            lock.unlink()
        except Exception:
            continue
        removed.append(str(lock.relative_to(Path(home))))
    return removed


def commit_pending(home: "Path | str", message: str) -> "str | None":
    """커밋 안 된 변경을 커밋해 보존한다. 커밋했으면 사람이 읽을 한 줄, 없으면 None.

    사고 때 남아 있던 건 `A`(add만 되고 commit이 안 된) 상태의 파일 2개였다.
    `git add`를 다시 부르는 이유는 unstaged 변경까지 같이 담기 위해서다."""
    home_s = str(home)
    targets = memory_sync._add_targets(home_s, [], _COMMIT_TARGETS)
    if not targets:
        return None
    try:
        add = memory_sync._run(["git", "-C", home_s, "add", "--", *targets], 30)
        if add.returncode != 0:
            return f"미커밋 변경 add 실패: {(add.stderr or '').strip()[:200]}"
        diff = memory_sync._run(["git", "-C", home_s, "diff", "--cached", "--quiet"], 30)
        if diff.returncode == 0:
            return None  # 커밋할 게 없다(정상 경로)
        commit = memory_sync._run(["git", "-C", home_s, "commit", "-q", "-m", message], 30)
        if commit.returncode != 0:
            return f"미커밋 변경 commit 실패: {(commit.stderr or '').strip()[:200]}"
        return "커밋 안 된 변경을 커밋해 보존함(버리지 않음)"
    except Exception as exc:
        return f"미커밋 변경 보존 예외: {type(exc).__name__}: {exc}"


def _abort_merge(home: "Path | str") -> "str | None":
    """받아오기가 충돌로 멈춰 있으면 되돌린다. 되돌리지 않으면 워킹트리가 충돌
    표시(<<<<<<<)가 박힌 채 남아, 서버가 그 상태의 기억 파일을 읽게 된다."""
    home_s = str(home)
    if not (Path(home_s) / ".git" / "MERGE_HEAD").exists():
        return None
    try:
        res = memory_sync._run(["git", "-C", home_s, "merge", "--abort"], 30)
    except Exception as exc:
        return f"충돌 되돌리기 예외: {type(exc).__name__}: {exc}"
    if res.returncode != 0:
        return f"충돌 되돌리기 실패: {(res.stderr or '').strip()[:200]}"
    return "충돌이 나 받아오기를 되돌림 — 이 기기의 기억은 그대로 남아 있음"


def startup_pull(home: "Path | str", pull_timeout: int = 60) -> dict:
    """시작 동기화 한 판. 절대 예외를 밖으로 내보내지 않는다.

    Returns: {"ok": bool, "steps": [사람이 읽는 한 줄들], "reason": str}
      ok=False여도 호출자는 서버를 띄워야 한다 — 그것이 이 작업의 전부다.
    """
    home_s = str(home)
    steps: list[str] = []

    removed = clear_stale_git_locks(home_s)
    if removed:
        steps.append(f"오래된 잠금 파일 {len(removed)}개 정리: {', '.join(removed)}")

    committed = commit_pending(home_s, "namu: 시작 시 남아 있던 변경 자동 보존")
    if committed:
        steps.append(committed)

    try:
        pull = memory_sync._run(
            ["git", "-C", home_s, "pull", "--no-rebase", "--no-edit"], pull_timeout
        )
        ok = pull.returncode == 0
        reason = "" if ok else (pull.stderr or pull.stdout or "").strip()[:500]
    except Exception as exc:
        ok = False
        reason = f"{type(exc).__name__}: {exc}"

    if ok:
        steps.append("받아오기 성공")
        clear_status(home_s)
        memory_sync._append_sync_log("STARTUP PULL ok " + " | ".join(steps), home=home_s)
        return {"ok": True, "steps": steps, "reason": ""}

    aborted = _abort_merge(home_s)
    if aborted:
        steps.append(aborted)
    steps.append(f"받아오기 실패: {reason}")
    write_status(home_s, "pull", reason, steps)
    memory_sync._append_sync_log("STARTUP PULL FAIL " + " | ".join(steps), home=home_s)
    return {"ok": False, "steps": steps, "reason": reason}


def main(argv: "list[str] | None" = None) -> int:
    """entrypoint용 진입점. 정상 0, 받아오기 실패 3 — 실패해도 호출자는 서버를 띄운다.

    exit code를 0이 아닌 값으로 주는 이유는 셸이 경고 한 줄을 찍을 수 있게 하려는
    것뿐이다. 0/1이 아닌 3을 쓰는 것은 "치명적 실패(1)"와 눈으로 구분하기 위해서다.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 1:
        print("usage: startup_sync.py <namu_home>", file=sys.stderr)
        return 2
    result = startup_pull(args[0])
    for line in result["steps"]:
        print(f"[namu-startup-sync] {line}")
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
