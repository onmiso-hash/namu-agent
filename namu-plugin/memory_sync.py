"""~/.namu(namu-35: 데이터 루트 고정, "개발 모드/설치 모드" 구분 폐지) 교훈 저장소의
git 자동 동기화 — record 시 auto commit+push, 세션 시작 훅에서 auto pull.

명시적 활성화(namu_sync_setup으로 마커 파일 생성) 전제.

db.py(코어)와 성격이 다른 인터페이스/훅 레이어 소관이라 stdlib만 사용한다 — 훅들의
PEP 723 의존성 블록을 건드릴 필요가 없게 하기 위함. 예외는 memo 충돌 자동 병합
(`_resolve_memo_conflict`) 하나로, 거기서만 yaml을 늦게 import하고 없으면 종전처럼
병합을 되돌린다.

subprocess 호출 공통 규약(session_context.check_git_behind와 동일 패턴):
capture_output=True, encoding="utf-8", errors="replace", shell=False, timeout 명시,
stdin=subprocess.DEVNULL — MCP 서버(stdio)의 stdin은 JSON-RPC 파이프라, 자식 git이
이를 상속하면 Windows에서 git이 작업을 끝내고도 종료/EOF를 못 해 communicate가
타임아웃되고, 이어지는 무타임아웃 reaping 대기로 서버가 수 분씩 멈춘다(namu-38 실측).
"""
import os
import subprocess
import time
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

    시각은 `cfg.now()`(기준 시간대)로 찍는다 — 이 파일이 기기 사이에 섞이지 않는데도
    그렇게 하는 이유는, **같은 기계 안에서 두 시간대가 섞이면 고장을 들여다볼 수 없기
    때문**이다. 웹 컨테이너의 시계는 UTC라 `datetime.now()`는 한국시간보다 9시간
    이르게 찍혔고, 바로 옆 작업일지·기억 기록은 `cfg.now()`라 한국시간이었다.
    2026-08-16 무한 재시작 사고를 뒤쫓을 때 실제로 이 어긋남에 걸렸다.
    """
    try:
        import config as cfg

        if home is None:
            home = cfg.NAMU_DATA_ROOT
        path = Path(home) / "db" / "sync.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = cfg.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {line}\n")
    except Exception:
        pass


def sync_pull() -> bool:
    """NAMU_DATA_ROOT에서 git pull(union merge)로 다른 PC의 최신 교훈을 당겨온다.

    세션 시작 훅에서 호출 — 여기서 원본 파일이 갱신되면 훅이 곧이어 부르는
    `db.ensure_indexes()`가 바뀐 그릇의 검색 색인을 다시 만든다(다섯 그릇 전부.
    fts5-memo-tasks-index 4단계 — 그전에는 교훈 하나뿐이었다). 그래서 이 함수는
    pull만 책임진다. 훅을 절대 막지 않도록 실패·타임아웃·예외 전부 삼키고
    False를 반환한다.
    """
    import config as cfg

    if not sync_enabled():
        return False

    home = str(cfg.NAMU_DATA_ROOT)
    try:
        # 개인 PC에도 죽은 git의 잠금이 남는다(아래 타임아웃이 git을 죽인다) — 컨테이너만
        # 청소하던 것을 여기서도 한다. 나이 기준만 본다(PERSONAL_STALE_LOCK_AGE_SECONDS 참조).
        removed = clear_stale_git_locks(home, PERSONAL_STALE_LOCK_AGE_SECONDS)
        if removed:
            _append_sync_log(f"PULL stale-lock 정리 {len(removed)}개: {', '.join(removed)}")
        # 앞선 실패가 병합을 멈춘 채 두었으면 먼저 정리한다 — 그 상태에서는 pull이 계속
        # "unmerged files"로 실패해 영영 회복하지 못한다.
        if merge_in_progress(home):
            _, note = settle_failed_merge(home)
            _append_sync_log(f"PULL 선행 병합 정리: {note}")
        result = subprocess.run(
            ["git", "-C", home, "pull", "--no-rebase", "--no-edit", "--quiet"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            shell=False,
            stdin=subprocess.DEVNULL,  # 서버 stdin(파이프) 상속 차단 (namu-38)
        )
        if result.returncode != 0:
            # 충돌로 멈췄으면 memo만의 충돌은 풀고, 아니면 되돌린다 — 되돌리지 않으면
            # 다음 sync_push가 충돌 표시를 커밋해 원격에 올린다(위 "멈춘 병합" 절).
            resolved, note = settle_failed_merge(home)
            _append_sync_log(
                f"PULL FAIL rc={result.returncode} err={(result.stderr or '').strip()[:200]}"
                + (f" | {note}" if note else "")
            )
            if not resolved:
                return False
        # 시작 시 받아오기가 실패해 남은 경고를 여기서 지운다
        # (namu-entrypoint-pull-resilience). 이 줄이 없으면 컨테이너가 뜬 뒤 런타임
        # pull로 이미 회복됐는데도 경고가 영영 남아, 다음번 진짜 실패를 사람이
        # 무시하게 된다. import를 함수 안에서 하는 이유는 startup_sync가 이 모듈을
        # import하기 때문(모듈 로드 시점 순환 회피 — cfg 지연 import와 같은 관례).
        import startup_sync

        startup_sync.clear_status(home)
        return True
    except Exception as exc:
        _append_sync_log(f"PULL FAIL {type(exc).__name__}: {exc}")
        return False


def _run(args: list[str], timeout: int):
    # stdin=DEVNULL 필수 — 모듈 docstring의 subprocess 공통 규약 참조(namu-38).
    return subprocess.run(
        args,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        stdin=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# 멈춘 병합 뒷정리 — 모든 pull/merge 실패 경로가 이 한 벌을 쓴다
# ---------------------------------------------------------------------------
# 계기(2026-09 검수 재현): 충돌로 멈춘 병합을 되돌리는 코드는 startup_sync.startup_pull
# 한 곳에만 있었다. 런타임 sync_pull·_push_steps 복구 pull·sync_setup 병합은 실패를
# 로그만 남기고 MERGE_HEAD와 충돌 표시(<<<<<<<)를 워킹트리에 둔 채 돌아갔고, 다음
# namu_record의 sync_push가 `git add memory/` + commit으로 **충돌 표시를 그대로 커밋해
# 원격에 올렸다**. memo.yaml은 union이 아니라 파일 단위 병합(mutable 그릇)이라 두 PC가
# 각자 메모를 붙이기만 해도 이 길로 들어간다. 그래서 되돌리기를 여기 한 벌로 두고,
# 모든 실패 경로와 커밋 직전 가드가 같은 함수를 부른다(두 벌이면 한쪽만 낡는다).

# 충돌 시 자동으로 풀어 주는 유일한 파일. config.BOWLS의 memo 패턴을 쓰지 않고 적어 두는
# 이유: 이 규칙은 "memo 파일 형식(YAML 리스트 한 문서, id 필수)을 안다"는 전제 위에
# 서 있어서, 그릇 등록만 바꾼다고 다른 파일에 자동으로 번지면 안 된다.
MEMO_REL_PATH = "memory/memo.yaml"


def _merge_head_exists(home: "Path | str") -> bool:
    return (Path(home) / ".git" / "MERGE_HEAD").exists()


def unmerged_paths(home: "Path | str") -> list[str]:
    """충돌이 풀리지 않은 경로들. 조회 자체가 실패하면 빈 목록(가드는 MERGE_HEAD도 본다)."""
    try:
        res = _run(
            ["git", "-C", str(home), "diff", "--name-only", "--diff-filter=U", "-z"], 30
        )
    except Exception:
        return []
    if res.returncode != 0:
        return []
    return sorted({p for p in (res.stdout or "").split("\0") if p.strip()})


def merge_in_progress(home: "Path | str") -> bool:
    """병합이 멈춰 있는가 — MERGE_HEAD가 있거나 충돌 미해결 경로가 하나라도 있으면 참.

    둘 다 보는 이유: `git merge --abort`가 반쯤 실패하면 MERGE_HEAD는 없는데 인덱스에
    충돌 단계(:1:/:2:/:3:)가 남는 경우가 있고, 그 상태로 `git add`하면 충돌 표시가
    그대로 스테이징된다."""
    return _merge_head_exists(home) or bool(unmerged_paths(home))


def abort_merge(home: "Path | str") -> "str | None":
    """멈춘 병합을 되돌린다. 멈춘 게 없으면 None, 있으면 사람이 읽을 한 줄.

    되돌리지 않으면 워킹트리가 충돌 표시가 박힌 채 남아, 서버가 그 상태의 기억
    파일을 읽고(memo 로더는 깨진 yaml을 빈 목록으로 읽는다 — 메모가 전부 사라져 보인다)
    다음 커밋이 그것을 원격에 올린다. (원래 startup_sync._abort_merge — 여기로 옮겼다.)"""
    home_s = str(home)
    if not merge_in_progress(home_s):
        return None
    try:
        res = _run(["git", "-C", home_s, "merge", "--abort"], 30)
    except Exception as exc:
        return f"충돌 되돌리기 예외: {type(exc).__name__}: {exc}"
    if res.returncode != 0:
        return f"충돌 되돌리기 실패: {(res.stderr or '').strip()[:200]}"
    return "충돌이 나 받아오기를 되돌림 — 이 기기의 기억은 그대로 남아 있음"


def merge_memo_entries(base: list, ours: list, theirs: list) -> list:
    """memo 3-way 병합(순수 함수). 형식이 어긋나면 ValueError.

    규칙(2026-09 오케스트레이터 결정): 결과 = ours ∪ theirs 에서 **base에 있었는데
    어느 한쪽이라도 뗀 id**를 뺀 것. memo는 붙이기·떼기만 있고 고치기가 없으므로 id
    집합 연산으로 양쪽 의도가 빠짐없이 표현된다 — 한쪽이 붙인 것은 살고, 한쪽이 뗀
    것은 사라진다(union 병합이 못 하던 "떼기"가 여기서는 지켜진다).

    같은 id가 양쪽에 다르게 있으면(고치기 기능이 없으니 사실상 일어나지 않는다) base와
    달라진 쪽을, 둘 다 달라졌으면 ours를 쓴다.

    순서: memo.add는 붙인 순서대로 뒤에 덧붙이므로 파일은 "오래된 것 먼저"다. id가
    ULID(앞부분이 만든 시각)라 id 정렬이 곧 붙인 시각 순서다. timestamp 문자열로
    정렬하지 않는 이유는 기기마다 시간대 표기가 다르면 문자열 비교가 틀리기 때문이다.
    """
    def _index(entries, label):
        if entries is None:
            return {}
        if not isinstance(entries, list):
            raise ValueError(f"{label}: 리스트가 아님")
        out: dict[str, dict] = {}
        for e in entries:
            if not isinstance(e, dict) or not e.get("id"):
                raise ValueError(f"{label}: id 없는 항목")
            key = str(e["id"])
            if key in out:
                raise ValueError(f"{label}: id 중복 {key}")
            out[key] = e
        return out

    b = _index(base, "base")
    o = _index(ours, "ours")
    t = _index(theirs, "theirs")
    removed = {i for i in b if i not in o or i not in t}
    merged: dict[str, dict] = {}
    for i in list(o) + [i for i in t if i not in o]:
        if i in removed:
            continue
        if i in o and i in t and o[i] != t[i]:
            merged[i] = t[i] if (i in b and o[i] == b[i]) else o[i]
        else:
            merged[i] = o.get(i, t.get(i))
    return [merged[i] for i in sorted(merged)]


def _resolve_memo_conflict(home: "Path | str") -> str:
    """충돌이 memo.yaml 하나뿐이면 3-way id 병합으로 풀고 병합 커밋까지 끝낸다.
    풀었으면 한 줄, 못 풀면 ValueError(호출자가 되돌린다).

    yaml은 여기서만 늦게 import한다 — 이 모듈은 stdlib만 쓰는 게 원칙인데(모듈
    docstring), 자동 병합은 memo 형식을 읽어야 하므로 예외로 둔다. yaml이 없는
    실행 환경이면 ImportError → 호출자가 종전대로 되돌린다(자동 병합만 빠진다).
    memo.py를 import하지 않는 이유도 같다(ulid까지 끌려온다) — 대신 쓰는 형식을
    memo._write_all과 똑같이 맞춘다(한 문서 리스트, allow_unicode, sort_keys=False).
    """
    import yaml

    home_s = str(home)
    conflicted = unmerged_paths(home_s)
    if conflicted != [MEMO_REL_PATH]:
        raise ValueError(f"자동 병합 대상 아님: {conflicted}")

    def _stage(n: int):
        res = _run(["git", "-C", home_s, "show", f":{n}:{MEMO_REL_PATH}"], 30)
        if res.returncode != 0:
            # 1번(base)이 없으면 양쪽이 각자 새로 만든 파일이다 — 빈 base로 본다.
            if n == 1:
                return []
            raise ValueError(f"stage {n} 읽기 실패: {(res.stderr or '').strip()[:200]}")
        return yaml.safe_load(res.stdout or "") or []

    merged = merge_memo_entries(_stage(1), _stage(2), _stage(3))
    body = yaml.safe_dump(merged, allow_unicode=True, default_flow_style=False, sort_keys=False)
    (Path(home_s) / MEMO_REL_PATH).write_text(body, encoding="utf-8")
    add = _run(["git", "-C", home_s, "add", "--", MEMO_REL_PATH], 30)
    if add.returncode != 0:
        raise ValueError(f"병합 결과 add 실패: {(add.stderr or '').strip()[:200]}")
    if unmerged_paths(home_s):
        raise ValueError("add 뒤에도 충돌 경로가 남음")
    commit = _run(["git", "-C", home_s, "commit", "-q", "--no-edit"], 30)
    if commit.returncode != 0:
        raise ValueError(f"병합 커밋 실패: {(commit.stderr or commit.stdout or '').strip()[:200]}")
    return f"메모 충돌을 자동 병합함(양쪽이 붙인 것은 살리고 뗀 것은 뺌 — {len(merged)}장)"


def settle_failed_merge(home: "Path | str") -> "tuple[bool, str | None]":
    """pull/merge가 실패한 **직후** 부른다. (풀었나, 사람이 읽을 한 줄).

    - 멈춘 병합이 없으면 (False, None) — 네트워크 실패 등, 되돌릴 게 없다.
    - 충돌이 memo.yaml 하나뿐이면 자동 병합해 커밋까지 끝내고 (True, 설명).
    - 그 밖(다른 파일 충돌·형식 깨짐·yaml 없음)은 병합을 되돌리고 (False, 설명).
    어느 경우든 이 함수가 돌아온 뒤에는 워킹트리에 충돌 표시가 남지 않는다."""
    home_s = str(home)
    if not merge_in_progress(home_s):
        return False, None
    try:
        return True, _resolve_memo_conflict(home_s)
    except Exception as exc:
        aborted = abort_merge(home_s)
        why = f"자동 병합 불가({type(exc).__name__}: {str(exc)[:150]})"
        return False, f"{why} — {aborted}" if aborted else why


# ---------------------------------------------------------------------------
# 오래된 잠금 파일 청소 — 컨테이너(startup_sync)와 개인 PC(sync_pull)가 같이 쓴다
# ---------------------------------------------------------------------------
# 개인 PC 기준(초). sync_pull·check_git_behind는 타임아웃이 나면 git을 죽이므로 개인
# PC에도 `.git/**/*.lock`이 남을 수 있는데, 지금까지 청소는 컨테이너 시작 때만 했다.
# 이 모듈의 git 호출 타임아웃은 가장 긴 것이 120초(첨부)라 10분 넘은 잠금은 살아 있는
# git의 것일 수 없다고 본다. "git 프로세스가 도는지"는 운영체제마다 보는 법이 달라
# 묻지 않고 나이만 본다 — 그래서 문턱을 타임아웃의 다섯 배로 넉넉히 잡았다.
PERSONAL_STALE_LOCK_AGE_SECONDS = 600


def git_lock_files(home: "Path | str") -> list[Path]:
    """`.git` 아래 모든 `*.lock`. 바로 아래만 보면 안 되는 게 이 함수의 존재 이유다 —
    2026-08-16 사고 때 사람을 두 번 막은 `refs/heads/main.lock`이 하위 폴더에 있었다."""
    git_dir = Path(home) / ".git"
    if not git_dir.is_dir():
        return []
    try:
        return sorted(p for p in git_dir.rglob("*.lock") if p.is_file())
    except Exception:
        return []


def clear_stale_git_locks(home: "Path | str", max_age_seconds: float) -> list[str]:
    """나이가 max_age_seconds를 넘긴 git 잠금 파일만 지우고, 지운 경로 목록을 돌려준다.
    갓 생긴 잠금은 손대지 않는다 — 그건 지금 돌고 있는 git의 것일 수 있다."""
    removed: list[str] = []
    now = time.time()
    for lock in git_lock_files(home):
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


# sync_setup이 `.gitignore`에 넣는 줄. **여기에 줄을 더하지 말 것** — 새 기기가 클론이
# 아니라 빈 홈에서 독립 init으로 온보딩하면(sync_setup의 unrelated-histories 병합) 양쪽
# `.gitignore`가 서로 다른 "새 파일"이라 add/add 충돌이 나고, 옛 판이 만든 원격에 새 판
# 기기가 붙는 순간 온보딩 병합이 되돌려진다. 새로 가릴 파일은 아래 LOCAL_EXCLUDE_LINES로.
GITIGNORE_LINES = ["db/"]

# git이 따라가면 안 되는 기기별 파일 — `.git/info/exclude`에 넣는다(ensure_local_excludes).
#   - db/ : 검색 캐시·로그(기기별, 다시 만들어진다)
#   - memory/.memo.lock : memo.py가 쪽지 파일을 고치는 동안 잡는 잠금(2026-09 추가).
#     `git add memory/`가 이것을 주워 커밋하면 다른 기기로 잠금 파일이 퍼진다.
LOCAL_EXCLUDE_LINES = ["db/", "memory/.memo.lock"]


def ensure_local_excludes(home: "Path | str") -> None:
    """LOCAL_EXCLUDE_LINES를 `.git/info/exclude`에 멱등으로 넣는다(전예외 무음).

    `.gitignore`에 넣지 않는 이유가 둘이다. ① 그 파일은 sync_setup을 돌릴 때만
    고쳐지는데 이미 개통된 기기(hp·samsung 등)는 sync_setup을 다시 돌리지 않는다 —
    그러면 새로 생긴 잠금 파일(memory/.memo.lock)을 다음 sync_push의 `git add memory/`가
    그대로 커밋한다. ② 줄을 더하면 독립 init 온보딩에서 add/add 충돌이 난다
    (GITIGNORE_LINES 설명). info/exclude는 git 추적 대상이 아니라 기기마다 조용히 넣어도 워킹트리를
    더럽히지 않으므로, add 직전마다 불러도 부작용이 없다."""
    try:
        git_dir = Path(home) / ".git"
        if not git_dir.is_dir():
            return
        exclude = git_dir / "info" / "exclude"
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        missing = [ln for ln in LOCAL_EXCLUDE_LINES if ln not in existing.splitlines()]
        if not missing:
            return
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for ln in missing:
                f.write(ln + "\n")
    except Exception:
        pass


def _add_targets(home: str, required: list[str], optional: list[str]) -> list[str]:
    """git add 대상 목록 조립(namu-34 ③-a). required는 무조건 포함(없으면 git add
    자체가 실패해 물증이 남는 기존 sync_push 회귀를 그대로 유지 — memory/가 없는
    설치는 이미 뭔가 잘못된 상태라 실패로 드러나야 한다). optional은 실재할 때만
    포함한다 — tasks/는 아직 한 번도 안 생겼을 수 있는 신규 환경이라, 없다고 git
    add 자체를 실패시키면 안 되기 때문이다."""
    # add 대상을 고르는 모든 경로(sync_push·push_tasks_pool·sync_setup·commit_pending)가
    # 여기를 지나므로, 기기별 파일 제외도 여기서 한 번 보장한다.
    ensure_local_excludes(home)
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

    namu-38: 단계별(add/diff/commit/push/재시도) 소요를 perf_counter로 재서 성공·
    실패 무관하게 함수 종료 시 "PUSH timing ..." 1줄을 추가로 남긴다 — samsung에서
    관측된 "git subprocess만 수십 배 느림" 재현·원인 특정용 물증이다. 기존 FAIL/
    retry-trigger 로그 라인은 그대로 두고(회귀 금지) timing 라인만 덧붙인다.
    """
    timings: dict[str, float] = {}
    start_total = time.perf_counter()

    def _timed(key: str, args: list[str], timeout: int):
        t0 = time.perf_counter()
        res = _run(args, timeout)
        timings[key] = time.perf_counter() - t0
        return res

    ok = _push_steps(home, message, required_paths, optional_paths, _timed)

    total = time.perf_counter() - start_total
    parts = " ".join(f"{k}={v:.2f}s" for k, v in timings.items())
    _append_sync_log(f"PUSH timing {parts} total={total:.2f}s ok={ok}", home=home)
    return ok


def _push_steps(home, message, required_paths, optional_paths, _timed) -> bool:
    """_push의 실제 git 호출 시퀀스(namu-38: timing 계측을 위해 _push에서 분리).
    반환값과 각 단계 실패 시 물증 로그는 분리 전과 동일하다.

    가드(2026-09): 병합이 멈춰 있으면 **커밋하지 않는다** — 먼저 풀거나(memo만의 충돌)
    되돌리고, 그래도 멈춰 있으면 실패로 끝낸다. 이 가드가 없던 때 `git add memory/`가
    충돌 표시를 스테이징하고 commit이 MERGE_HEAD를 부모로 삼아 병합을 "완료"시켜,
    충돌 표시가 원격에 올라갔다(검수 재현 test_fixC_conflict_markers)."""
    if merge_in_progress(home):
        _, note = settle_failed_merge(home)
        _append_sync_log(f"PUSH 선행 병합 정리: {note}", home=home)
        if merge_in_progress(home):
            _append_sync_log("PUSH FAIL 병합이 멈춘 채라 커밋하지 않음", home=home)
            return False

    targets = _add_targets(home, required_paths, optional_paths)

    if targets:
        try:
            add_res = _timed("add", ["git", "-C", home, "add", *targets], 5)
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
        diff_res = _timed("diff", ["git", "-C", home, "diff", "--cached", "--quiet"], 5)
        has_changes = diff_res.returncode != 0
    except Exception as exc:
        _append_sync_log(f"PUSH FAIL diff-check {type(exc).__name__}: {exc}", home=home)
        return False

    if has_changes:
        try:
            commit_res = _timed("commit", ["git", "-C", home, "commit", "-m", message], 5)
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
        push_res = _timed("push", ["git", "-C", home, "push"], 10)
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
        pull_res = _timed(
            "retry_pull", ["git", "-C", home, "pull", "--no-rebase", "--no-edit"], 10
        )
        if pull_res.returncode != 0:
            # memo만의 충돌이면 풀고 계속 올린다. 아니면 되돌리고 실패 — 이번 기록은
            # 로컬 커밋으로 남아 다음 호출 때 다시 시도된다.
            resolved, note = settle_failed_merge(home)
            if not resolved:
                _append_sync_log(
                    f"PUSH FAIL recovery-pull rc={pull_res.returncode} "
                    f"err={(pull_res.stderr or '').strip()[:200]}"
                    + (f" | {note}" if note else ""),
                    home=home,
                )
                return False
            _append_sync_log(f"PUSH recovery-pull {note}", home=home)
    except Exception as exc:
        settle_failed_merge(home)
        _append_sync_log(f"PUSH FAIL recovery-pull {type(exc).__name__}: {exc}", home=home)
        return False

    try:
        retry_res = _timed("retry_push", ["git", "-C", home, "push"], 10)
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


def _gitattributes_union_lines() -> list[str]:
    """config.BOWLS 레지스트리에서 `.gitattributes` union 병합 라인을 파생한다
    (namu-57 3단계 — 예전엔 여기 하드코딩 3줄 리스트였다. profile 그릇이 빠져 있어서
    hp/samsung이 오프라인 중 각자 memory/profile.yaml에 사실을 추가하면 진짜 git
    충돌이 나는 실제 버그였다. 그릇을 추가할 때마다 이 파일도 손으로 고쳐야 했던
    구조 자체가 원인이라, BOWLS 하나에서 파생시켜 빠질 수 없게 만든다).

    규칙: `merge == "union"`이고 `mutable == False`인 그릇의 `git_patterns` 각각을
    `"{pattern} merge=union"` 한 줄로 만든다. mutable 그릇(namu-56 4단계에서 들어올
    memo 등)은 파일 전체가 수시로 바뀌는 성격이라 줄 단위 union 병합이 오히려 내용을
    깨뜨리므로 제외한다 — Bowl.mutable 필드가 여기서 실제로 게이트 역할을 한다.

    BOWLS 순회 순서(learnings→tasks→profile)를 그대로 따른다 — 기존 설치본의
    .gitattributes에 이미 있는 학습/tasks 3줄이 앞서 나오고, 새로 추가되는 profile
    1줄만 뒤에 붙어 불필요한 파일 변경을 최소화한다(config.BOWLS 순서 주석 참고).

    cfg는 함수 안에서 import한다 — 이 파일의 다른 함수들과 동일한 관례(모듈 상단에서
    import하면 config 속성을 monkeypatch로 격리하는 테스트와 어긋날 여지가 생기고,
    config.py가 memory_sync.py를 import하지 않아 순환 위험은 없지만 관례를 굳이
    깨지 않는다).
    """
    import config as cfg

    lines: list[str] = []
    for bowl in cfg.BOWLS:
        if bowl.merge == "union" and not bowl.mutable:
            for pattern in bowl.git_patterns:
                lines.append(f"{pattern} merge=union")
    return lines


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
        missing = [ln for ln in _gitattributes_union_lines() if ln not in existing_lines]
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


def attach_isolation_active(home: Path) -> bool:
    """이 저장소에 첨부 격리가 이미 걸려 있는가(멱등 판정용).

    판정 근거는 `remote.origin.partialclonefilter` 설정 하나다 — 세 설정
    (promisor·filter·sparse) 중 이것만 "격리를 위해 우리가 넣은 값"이고 나머지
    둘은 다른 이유로도 켜질 수 있기 때문이다(sparse-checkout은 사용자가 직접 쓸
    수 있다). 셋을 모두 확인하면 사용자가 자기 목적으로 sparse를 켠 저장소를
    "격리됨"으로 오판할 수 있다.
    """
    res = _run(["git", "-C", str(home), "config", "--get", "remote.origin.partialclonefilter"], 5)
    return res.returncode == 0 and (res.stdout or "").strip() == "blob:none"


def ensure_attach_isolation(home: Path) -> list[str]:
    """첨부 폴더가 이 PC로 내려오지 않게 만든다(멱등).

    ⚠ 이 함수는 파일 첨부 기능보다 **먼저** 깔려야 한다. 이미 받아둔 파일은 설정을
    걸어도 사라지지 않는다 — 새로 오는 것만 막힌다. 순서가 뒤집히면 그 사이에 올라간
    파일이 모든 PC에 영구히 남는다(되돌릴 수 없다).

    거는 설정 세 가지:
      1. `remote.origin.promisor=true` — 몸통이 없는 객체를 "아직 안 받은 것"으로
         취급하고, 필요해지면 그때 원격에서 받아온다는 표시.
      2. `remote.origin.partialclonefilter=blob:none` — 이후 fetch/pull이 파일 몸통을
         받지 않는다.
      3. sparse-checkout에서 첨부 폴더 제외 — 작업트리에 파일이 나타나지 않는다.

    2번과 3번은 역할이 다르다. 2번이 없으면 몸통이 `.git`에 쌓이고(용량), 3번이
    없으면 작업트리에 파일이 나타난다. 둘 다 필요하다.

    첨부가 저장소에 있어도 이 PC에서 지워지는 일은 없다 — `sync_push`가 쓰는 add
    대상은 `memory/`·`tasks/`뿐이라 제외 경로가 삭제로 잡히지 않는다(실측 확인).

    반환값은 사람이 읽는 notes 리스트(sync_setup 보고용). 실패는 예외를 전파하지
    않고 notes에만 남긴다 — 세션 시작 훅을 막으면 안 되기 때문이다.
    """
    import config as cfg

    notes: list[str] = []
    if not (Path(home) / ".git").is_dir():
        notes.append("첨부 격리: git 저장소가 아니라 건너뜀")
        return notes

    if attach_isolation_active(Path(home)):
        notes.append("첨부 격리: 이미 걸려 있음 (스킵)")
        return notes

    try:
        for key, value in (
            ("remote.origin.promisor", "true"),
            ("remote.origin.partialclonefilter", "blob:none"),
        ):
            res = _run(["git", "-C", str(home), "config", key, value], 5)
            if res.returncode != 0:
                notes.append(f"첨부 격리 실패({key}): {(res.stderr or '').strip()[:200]}")
                return notes

        sparse = _run(
            [
                "git", "-C", str(home), "sparse-checkout", "set", "--no-cone",
                *cfg.ATTACH_SPARSE_PATTERNS,
            ],
            30,
        )
        if sparse.returncode != 0:
            notes.append(f"첨부 격리 실패(sparse-checkout): {(sparse.stderr or '').strip()[:200]}")
            return notes

        notes.append(f"첨부 격리 적용 — {cfg.ATTACH_DIR_NAME}/ 는 이 PC로 내려오지 않는다")
    except Exception as exc:
        notes.append(f"첨부 격리 예외: {type(exc).__name__}: {exc}")
    return notes


def sync_push(message: str) -> bool:
    """memory/(+실재하면 tasks/, namu-34 ③-a / .gitattributes, namu-57 3단계 ④)를
    add→(변경 있으면) commit→push. namu_record 성공 직후 호출. 실제 git 시퀀스는
    `_push()` 참조.

    .gitattributes를 optional로 추가한 이유(namu-57 3단계 ④): 서버 부팅 시
    ensure_gitattributes_union()이 이 파일에 새 union 라인을 append해도, 지금까지는
    sync_push의 add 대상에 `.gitattributes`가 아예 없어서 그 변경이 영영 커밋되지
    않았다(워킹트리가 계속 더러운 채로 남고, 새로 clone하는 쪽은 옛 내용만 받는 구멍).
    required가 아니라 optional인 이유: 아직 `.gitattributes`가 없는 신규 환경(첫 부팅
    전)에서 `git add`가 대상 부재로 실패하면 안 되기 때문 — `_add_targets()`가
    `Path(home)/rel` 존재 여부로 걸러주므로 파일에도 디렉터리와 동일하게 그대로
    동작한다.

    config/를 optional로 추가한 이유: 세션 시작 검사 훅이 감시 대상을
    `~/.namu/config/version_targets.json`에서 읽는데, 이 폴더가 add 대상에 없으면
    설정이 만든 기계에만 남고 다른 기계에서는 검사가 대상 없이 조용히 끝난다.
    기계마다 다른 값을 코드가 아니라 설정에 두기로 한 이상, 그 설정도 기억과
    같은 경로로 따라가야 한다."""
    import config as cfg

    if not sync_enabled():
        return False

    return _push(
        str(cfg.NAMU_DATA_ROOT), message, ["memory/"],
        ["tasks/", ".gitattributes", "config/"],
    )


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
    """`~/.namu`(개인 풀) 대상 tasks/(+실재하면 memory/, .gitattributes) push
    (namu-34 ③-b, CLI 전용).

    `tasks_pool_git_ready(home)`가 False면(신규 sync 미개통 등) 조용히 no-op으로
    False를 반환한다 — 호출자(namu_tasks_push.py)는 이를 정상 종료(exit 0)로 취급한다.

    .gitattributes를 optional로 추가한 이유는 sync_push()와 동일(namu-57 3단계 ④ —
    서버 부팅 시 append된 union 라인이 이 경로로도 커밋 누락되지 않게 함)."""
    if not tasks_pool_git_ready(home):
        return False
    return _push(
        str(home), message, [],
        ["tasks/", "memory/", ".gitattributes", "config/"],
    )


# sync_setup이 커밋하는 대상 — `git add -A`를 쓰지 않는다(startup_sync._COMMIT_TARGETS와
# 같은 이유: ~/.namu는 첨부 폴더를 sparse-checkout으로 격리해 두고 있어 전체 add는 격리
# 규칙과 부딪힐 여지가 있고, 사용자가 ~/.namu에 둔 엉뚱한 파일까지 원격으로 새어 나간다).
# 평소 동기화 대상(memory/·tasks/·.gitattributes·config/)에 더해, 설정이 막 만든
# `.gitignore`와 마커 `.namu_sync`를 담는다 — 예전 `add -A`가 담던 것 중 의도된 것은 이
# 둘뿐이었다. 전부 optional(실재할 때만) — 신규 환경에서 대상 부재로 add가 실패하면 안 된다.
SETUP_COMMIT_TARGETS = [
    ".gitignore", ".gitattributes", ".namu_sync", "memory/", "tasks/", "config/",
]


def sync_setup(remote_url: str) -> str:
    """~/.namu(NAMU_DATA_ROOT) 교훈 저장소를 git 원격 백업용으로 초기화한다.

    이 함수만 예외적으로 무음이 아니다 — 사람이 읽고 다음 행동(인증 설정 등)을
    판단해야 하는 결과이므로 문자열로 그대로 보고한다. 구조화된 결과가 필요하면
    `sync_setup_report()`를 쓴다(클라우드 entrypoint가 그렇다).

    원격 repo 자체는 사용자가 미리 준비해야 한다(이 함수는 로컬 wiring만 담당).
    """
    return sync_setup_report(remote_url)["text"]


def sync_setup_report(remote_url: str) -> dict:
    """sync_setup의 본체. `{"text", "notes", "fatal", "network"}`를 돌려준다.

    실패를 두 갈래로 가른다(2026-09):
    - `fatal` — 로컬 wiring이 안 된 것(init·원격 등록·마커·커밋 등). 이대로 서버를 띄우면
      기록이 원격으로 가지 못한다.
    - `network` — 원격에 닿지 못한 것(fetch·병합·push). 로컬 wiring은 끝났고, 다음
      record·pull이 다시 시도한다. 클라우드 entrypoint는 이것을 치명으로 보면 안 된다 —
      GitHub가 잠깐 안 닿는다고 exit 1이면 재시작 정책(always)과 맞물려 2026-08-16과
      같은 무한 재시작 루프가 된다(검수 재현 repro_boot_offline.sh).
    예전에는 호출부가 결과 문자열에서 "실패"를 찾아 판정했다 — 사람이 읽는 문장에
    판정을 매달면 문구 하나가 바뀔 때 동작이 조용히 바뀐다. 그래서 칸을 나눴다.
    """
    import config as cfg

    home = cfg.NAMU_DATA_ROOT
    home.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    fatal: list[str] = []
    network: list[str] = []

    def _report() -> dict:
        return {
            "text": "namu_sync_setup 완료:\n- " + "\n- ".join(notes),
            "notes": notes, "fatal": fatal, "network": network,
        }

    def _fatal(note: str) -> None:
        notes.append(note)
        fatal.append(note)

    def _network(note: str) -> None:
        notes.append(note)
        network.append(note)

    git_dir = home / ".git"
    if git_dir.exists():
        notes.append("git 저장소: 이미 존재 (초기화 스킵)")
    else:
        try:
            init_res = _run(["git", "-C", str(home), "init", "-b", "main"], 10)
            if init_res.returncode == 0:
                notes.append("git init -b main 완료")
            else:
                msg = f"실패: git init 오류 - {(init_res.stderr or '').strip()[:300]}"
                return {"text": msg, "notes": [msg], "fatal": [msg], "network": []}
        except Exception as exc:
            msg = f"실패: git init 예외 - {type(exc).__name__}: {exc}"
            return {"text": msg, "notes": [msg], "fatal": [msg], "network": []}

    gitignore = home / ".gitignore"
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        missing = [ln for ln in GITIGNORE_LINES if ln not in existing.splitlines()]
        if missing:
            with gitignore.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                for ln in missing:
                    f.write(ln + "\n")
            notes.append(f".gitignore에 {', '.join(missing)} 추가")
        else:
            notes.append(".gitignore: db/ 이미 존재 (스킵)")
    except OSError as exc:
        _fatal(f".gitignore 기록 실패: {exc}")

    # 아래 두 도우미는 notes 목록만 돌려준다 — 그 안의 실패 문장은 로컬 설정 실패라
    # 치명으로 분류한다(종전 "실패" 문자열 판정과 같은 결과를 유지).
    for note in ensure_gitattributes_union(home):
        (_fatal if ("실패" in note or "예외" in note) else notes.append)(note)

    try:
        remote_check = _run(["git", "-C", str(home), "remote", "get-url", "origin"], 5)
        if remote_check.returncode == 0:
            set_res = _run(["git", "-C", str(home), "remote", "set-url", "origin", remote_url], 5)
            if set_res.returncode == 0:
                notes.append("원격 origin 갱신")
            else:
                _fatal(f"원격 갱신 실패: {(set_res.stderr or '').strip()[:200]}")
        else:
            add_res = _run(["git", "-C", str(home), "remote", "add", "origin", remote_url], 5)
            if add_res.returncode == 0:
                notes.append("원격 origin 추가")
            else:
                _fatal(f"원격 추가 실패: {(add_res.stderr or '').strip()[:200]}")
    except Exception as exc:
        _fatal(f"원격 설정 예외: {type(exc).__name__}: {exc}")

    # 첨부 격리는 **원격을 등록한 뒤, 첫 fetch 전에** 건다. 순서가 이 사이여야 하는
    # 이유가 양쪽에 있다.
    #   - 원격 등록보다 먼저 걸면 안 된다: `git config remote.origin.*`이
    #     `[remote "origin"]` 절을 먼저 만들어 버려서, 바로 위 블록의
    #     `git remote get-url origin`이 성공해 `git remote add` 대신 `set-url`
    #     경로를 타고, 그러면 `git remote add`가 넣어주는 fetch refspec이 영영
    #     등록되지 않는다 → fetch를 해도 `origin/main`이 안 생겨 아래 병합이
    #     "원격에 main 없음"으로 건너뛰어지고 push가 non-fast-forward로 거부된다
    #     (테스트 2건이 실제로 이 순서에서 깨졌다).
    #   - 첫 fetch보다는 먼저 걸어야 한다: 그래야 처음 받아오는 순간부터 첨부
    #     몸통을 안 받는다.
    for note in ensure_attach_isolation(home):
        (_fatal if ("실패" in note or "예외" in note) else notes.append)(note)

    marker = home / ".namu_sync"
    try:
        marker.touch(exist_ok=True)
        notes.append("마커(.namu_sync) 생성 — 이후 자동 pull/push 활성화")
    except OSError as exc:
        _fatal(f"마커 생성 실패: {exc}")

    # 앞선 실패(컨테이너 재시작 전 등)가 병합을 멈춘 채 두었으면 커밋 전에 정리한다 —
    # 그 상태로 add/commit하면 충돌 표시가 커밋된다(_push_steps 가드와 같은 이유).
    if merge_in_progress(home):
        resolved, note = settle_failed_merge(home)
        (notes.append if resolved else _network)(f"멈춘 병합 정리: {note}")

    try:
        targets = _add_targets(str(home), [], SETUP_COMMIT_TARGETS)
        add_res = _run(["git", "-C", str(home), "add", "--", *targets], 10) if targets else None
        if add_res is not None and add_res.returncode != 0:
            _fatal(f"git add 실패: {(add_res.stderr or '').strip()[:200]}")
        else:
            diff_res = _run(["git", "-C", str(home), "diff", "--cached", "--quiet"], 5)
            if diff_res.returncode != 0:
                commit_res = _run(
                    ["git", "-C", str(home), "commit", "-m", "namu: sync 초기 설정"], 10
                )
                if commit_res.returncode == 0:
                    notes.append("초기 커밋 완료")
                else:
                    _fatal(f"초기 커밋 실패: {(commit_res.stderr or '').strip()[:200]}")
            else:
                notes.append("커밋할 변경 없음")
    except Exception as exc:
        _fatal(f"add/commit 예외: {type(exc).__name__}: {exc}")

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
            _network(
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
                    if merge_res.returncode == 0:
                        notes.append("원격 기존 기록과 병합 완료(unrelated-histories, 온보딩 전용)")
                    else:
                        # 충돌 내용(CONFLICT ...)은 stderr가 아니라 stdout으로 나온다 —
                        # stderr만 적으면 사유 칸이 비어 무엇이 부딪혔는지 알 수 없다.
                        # 멈춘 병합은 여기서 반드시 풀거나 되돌린다(안 그러면 다음
                        # commit_pending/sync_push가 충돌 표시를 커밋한다).
                        resolved, settle = settle_failed_merge(home)
                        if resolved:
                            notes.append(f"원격 기존 기록과 병합 완료 — {settle}")
                        else:
                            out = (merge_res.stdout or "").strip()
                            err = (merge_res.stderr or "").strip()
                            _network(
                                "원격 기록 병합 실패: "
                                f"{(out + (' | ' if out and err else '') + err)[:300]}"
                                + (f" — {settle}" if settle else "")
                            )
                else:
                    # 로컬에 커밋이 전혀 없는 예외 경로(위 add/commit이 실패했거나
                    # 애초에 커밋할 변경이 없던 경우) — 병합할 로컬 역사 자체가
                    # 없으므로 원격 main을 그대로 로컬 main으로 채택한다.
                    checkout_res = _run(
                        ["git", "-C", str(home), "checkout", "-B", "main", "origin/main"], 10
                    )
                    if checkout_res.returncode == 0:
                        notes.append("로컬 커밋 없음 — 원격 main을 그대로 채택")
                    else:
                        _fatal(f"원격 main 채택 실패: {(checkout_res.stderr or '').strip()[:300]}")
    except Exception as exc:
        settle_failed_merge(home)
        _network(f"fetch/병합 예외: {type(exc).__name__}: {exc}")

    try:
        push_res = _run(["git", "-C", str(home), "push", "-u", "origin", "main"], 10)
        if push_res.returncode == 0:
            notes.append("push 완료")
        else:
            _network(
                "push 실패(인증 미비 등 사용자가 해결할 문제 — 다음 record가 재시도): "
                f"{(push_res.stderr or '').strip()[:300]}"
            )
    except Exception as exc:
        _network(f"push 예외: {type(exc).__name__}: {exc}")

    return _report()
