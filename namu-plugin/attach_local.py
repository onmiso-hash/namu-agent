"""터미널에서 첨부 파일 주고받기 — `~/.namu`의 git 저장소를 직접 쓴다.

클라우드는 GitHub API로 파일을 주고받지만(서버는 남의 저장소에 열쇠로 접근한다),
터미널은 회원 본인의 `~/.namu` 사본이 이미 그 저장소에 연결돼 있으므로 git으로
바로 다룬다. 두 경로가 같은 폴더(`attach_file/`)를 같은 규칙으로 쓴다.

**첨부 폴더는 이 PC에서 격리돼 있다**(config.ATTACH_SPARSE_PATTERNS). 그래서 평범한
`git add`는 통하지 않는다 — 아래 절차는 전부 2026-08-07에 실제 git으로 재서 정한
것이다(git 2.43.0).

| 하는 일 | 명령 | 확인한 것 |
|---|---|---|
| 올리기 | 파일을 쓰고 `git add --sparse` → commit → push → `sparse-checkout reapply` | 그냥 `add`는 "sparse 정의 밖"이라며 무시된다. `--sparse`는 스테이징된다. reapply 뒤 작업트리에서 파일이 사라지고 상태가 깨끗해진다 |
| 목록 | `git ls-tree -r --name-only HEAD -- attach_file` | **`-l`(크기 포함)을 쓰면 안 된다** — 크기를 알아내려고 빠진 몸통을 전부 내려받는다(파일 2,548개에 7분 넘게 안 끝남). 크기는 첨부 기록의 bytes 칸에서 읽는다 |
| 받기 | `git cat-file blob HEAD:<경로>` | 몸통이 없는 사본에서도 그 하나만 끌어온다(사용자 실제 저장소에서 40MB→3.4MB 사본, 파일 하나당 증가 0~12KB) |
| 지우기 | `git rm --sparse` → commit → push | 원격에서 빠지고 작업트리 상태는 깨끗하다 |

올린 뒤 로컬 사본을 남기지 않는 이유: 첨부가 각 PC에 쌓이지 않게 하는 것이 격리의
목적이다. 손으로 지우면 `git status`에 삭제로 남는데(원격에는 안 실린다 —
`sync_push`가 `memory/`·`tasks/`만 add하기 때문), 그 상태를 계속 두는 것보다
`sparse-checkout reapply`로 되돌리는 편이 깨끗하다.
"""
from pathlib import Path

import config as cfg
from memory_sync import _run


class AttachError(ValueError):
    """첨부 다루기 실패 — 사용자에게 그대로 보여줄 수 있는 메시지."""


_BAD_NAME_PARTS = ("..", "\\", "/")

_GIT_TIMEOUT_SEC = 120


def normalize_name(name: str) -> str:
    """올리려는 이름을 `attach_file/<이름>` 한 칸으로 정규화한다.

    `보고서.pdf`와 `attach_file/보고서.pdf` 둘 다 받는다. 하위 폴더나 거슬러
    올라가는 이름은 거절한다 — 첨부는 그 폴더 한 칸에만 놓인다(클라우드의
    attach_files.normalize_name과 같은 규칙이며, 어긋나면 두 경로가 다른 자리에
    파일을 놓게 된다).
    """
    raw = (name or "").strip().strip("/")
    prefix = f"{cfg.ATTACH_DIR_NAME}/"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    if not raw:
        raise AttachError("파일 이름이 비어 있습니다 — 올릴 이름을 적어 주세요.")
    if any(bad in raw for bad in _BAD_NAME_PARTS):
        raise AttachError(
            f"파일 이름에 쓸 수 없는 글자가 있습니다: {raw!r} — "
            f"첨부는 {prefix} 안에 하위 폴더 없이 놓입니다."
        )
    return prefix + raw


def _home() -> Path:
    home = cfg.NAMU_DATA_ROOT
    if not (home / ".git").is_dir():
        raise AttachError(
            f"{home} 가 git 저장소가 아닙니다 — `namu_sync_setup`으로 개인 원격 "
            "저장소를 먼저 연결하세요(첨부는 그 저장소에 올라갑니다)."
        )
    return home


def _git(home: Path, args: list[str], what: str):
    res = _run(["git", "-C", str(home), *args], _GIT_TIMEOUT_SEC)
    if res.returncode != 0:
        raise AttachError(
            f"{what} 실패 — {(res.stderr or res.stdout or '').strip()[:300]}"
        )
    return res


def _reapply_sparse(home: Path) -> None:
    """첨부 폴더를 작업트리에서 다시 걷어낸다(올리기·실패 뒷정리 공통).

    실패해도 예외를 올리지 않는다 — 파일은 이미 올라갔고, 여기서 도구를 실패로
    돌리면 회원이 같은 파일을 또 올린다. 남는 것은 작업트리에 첨부 한 개가
    보이는 상태뿐이고 다음 격리 보정이 다시 걷어낸다.
    """
    _run(["git", "-C", str(home), "sparse-checkout", "reapply"], _GIT_TIMEOUT_SEC)


def upload(name: str, content: bytes, message: str) -> dict:
    """파일 하나를 저장소의 `attach_file/`에 올린다(있으면 덮어쓴다).

    돌려주는 것: `{"path", "bytes", "replaced"}`. `replaced`는 저장소에 같은 이름이
    이미 있었는지이며, 호출부가 첨부 기록을 '올림'으로 남길지 '새 판'으로 남길지의
    근거다.
    """
    path = normalize_name(name)
    home = _home()
    replaced = path in set(list_paths())

    target = home / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    try:
        _git(home, ["add", "--sparse", path], "첨부 스테이징")
        _git(home, ["commit", "-m", message], "첨부 커밋")
        _git(home, ["push"], "첨부 올리기")
    finally:
        # 성공이든 실패든 첨부가 이 PC에 남지 않게 되돌린다.
        _reapply_sparse(home)
    return {"path": path, "bytes": len(content), "replaced": replaced}


def list_paths() -> list[str]:
    """저장소에 지금 있는 첨부 경로들 — **이름만** 읽는다.

    `-l`(크기 포함)을 쓰지 않는 것이 이 함수의 핵심이다. 크기를 물으면 git이
    그것을 알아내려고 빠진 파일 몸통을 전부 내려받아 첨부 격리가 뚫린다.
    크기는 첨부 기록(attachments.yaml)의 bytes 칸에서 읽는다.
    """
    home = _home()
    # `-z`가 필요하다 — 없으면 git이 한글 파일 이름을 따옴표로 감싸고 바이트를
    # `\354\204\244` 꼴로 바꿔 내보낸다(실측). 그 값을 그대로 들고 다니면 지우기가
    # "그런 파일 없습니다"로 실패하고, 첨부 기록의 경로와도 안 맞는다.
    res = _run(
        [
            "git", "-C", str(home), "ls-tree", "-r", "--name-only", "-z", "HEAD",
            "--", cfg.ATTACH_DIR_NAME,
        ],
        _GIT_TIMEOUT_SEC,
    )
    if res.returncode != 0:
        # 첨부 폴더가 아직 없으면 여기 걸린다 — 오류가 아니라 "아직 아무것도 안
        # 올렸다"이므로 빈 목록으로 다룬다.
        return []
    return [name for name in (res.stdout or "").split("\0") if name.strip()]


def download(name: str) -> bytes:
    """파일 하나를 꺼내 온다. 몸통이 없는 사본에서도 그 하나만 끌어온다.

    `memory_sync._run`을 쓰지 않는 유일한 자리다 — 그 함수는 결과를 문자열로
    디코딩하므로 그림·PDF 같은 파일이 깨진다. 여기서만 바이트 그대로 받는다.
    """
    import subprocess

    path = normalize_name(name)
    home = _home()
    res = subprocess.run(
        ["git", "-C", str(home), "cat-file", "blob", f"HEAD:{path}"],
        capture_output=True, timeout=_GIT_TIMEOUT_SEC, shell=False,
        stdin=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        raise AttachError(
            f"저장소에 그런 파일이 없습니다: {path} — 목록을 먼저 확인해 보세요."
        )
    return res.stdout


def delete(name: str, message: str) -> str:
    """파일 하나를 저장소에서 뺀다. 뺀 경로를 돌려준다.

    ⚠ 완전 삭제가 아니다 — git은 과거 이력을 남기므로 지우기 전 시점으로 거슬러
    올라가면 그 파일은 여전히 있다.
    """
    path = normalize_name(name)
    home = _home()
    if path not in set(list_paths()):
        raise AttachError(
            f"저장소에 그런 파일이 없습니다: {path} — 이미 지워졌을 수 있습니다."
        )
    _git(home, ["rm", "--sparse", "--quiet", path], "첨부 지우기")
    _git(home, ["commit", "-m", message], "첨부 지움 커밋")
    _git(home, ["push"], "첨부 지움 올리기")
    return path


def commit_message(action: str, path: str) -> str:
    """커밋 한 줄. 줄바꿈은 지운다 — 첫 줄이 곧 제목이라 섞이면 이력이 잘려 보인다."""
    return " ".join(f"attach: {action} {path}".split())
