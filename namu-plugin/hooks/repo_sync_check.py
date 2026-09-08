#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""코드 저장소가 원격보다 뒤처졌는지 검사한다.

왜 만들었나
-----------
2026-09-08에 사고가 있었다. 기억 저장소(~/.namu)만 최신으로 맞추고 코드 저장소는
확인하지 않은 채 개발을 시작했다. 그때 onnamu-project 원격에는 이미 커밋이 7개
있었고, 그중 하나가 그 세션에서 하려던 작업 그 자체였다. 같은 기능을 두 번
만들었고, 이미 배포까지 되어 있던 것을 뒤늦게 알았다.

두 자리에서 검사한다
--------------------
  session  세션을 시작할 때. 일감 폴더와 그 바로 아래 폴더들 가운데 저장소인
           것을 찾아 원격을 받아 오고, 뒤처진 것을 알린다.
  pretool  파일을 고치기 직전에. 그 파일이 속한 저장소가 뒤처져 있으면 사용자에게
           물어본다. 세션 시작 때 받아 둔 것이 오래되었으면 이때 다시 받는다.

받아 오기(fetch)만 하고 합치지(merge) 않는다. 합치는 일은 사람이 정한다.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

FETCH_TIMEOUT = 12          # 저장소 하나를 받아 오는 데 기다릴 초
FETCH_MAX_AGE = 1800        # 이 초보다 오래된 것만 다시 받는다(30분)
PRETOOL_FETCH_TIMEOUT = 8


def git(repo, *args, timeout=10):
    """git 명령 하나를 돌리고 결과 글자를 돌려준다. 실패하면 None."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def is_repo(path):
    return os.path.isdir(os.path.join(path, ".git"))


def fetch_age(repo):
    """마지막으로 원격을 받아 온 뒤 몇 초가 지났나. 받은 적이 없으면 아주 큰 값."""
    head = os.path.join(repo, ".git", "FETCH_HEAD")
    try:
        import time
        return time.time() - os.path.getmtime(head)
    except Exception:
        return 10 ** 9


def refresh(repo, timeout):
    git(repo, "fetch", "--quiet", timeout=timeout)


def behind_ahead(repo):
    """원격보다 몇 개 뒤처졌고 몇 개 앞섰나. 견줄 상대가 없으면 None."""
    counts = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if not counts:
        return None
    try:
        ahead, behind = (int(x) for x in counts.split())
    except ValueError:
        return None
    return behind, ahead


def find_repos(base):
    """일감 폴더 자신과 그 바로 아래 폴더들 가운데 저장소인 것."""
    found = []
    top = git(base, "rev-parse", "--show-toplevel")
    if top:
        found.append(top)
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith("."):
                continue
            path = os.path.join(base, name)
            if os.path.isdir(path) and is_repo(path) and path not in found:
                found.append(path)
    except Exception:
        pass
    return found


def check(repo, timeout):
    if fetch_age(repo) > FETCH_MAX_AGE:
        refresh(repo, timeout)
    return repo, behind_ahead(repo)


def mode_session():
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    repos = find_repos(base)
    if not repos:
        return
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda r: check(r, FETCH_TIMEOUT), repos))

    뒤처진 = [(r, ba[0], ba[1]) for r, ba in results if ba and ba[0] > 0]
    if not 뒤처진:
        return

    줄 = ["### ⚠ 코드 저장소가 원격보다 뒤처져 있습니다", ""]
    for repo, behind, ahead in 뒤처진:
        이름 = os.path.basename(repo)
        꼬리 = ", 이 기계에만 있는 커밋 %d개" % ahead if ahead else ""
        줄.append("- **%s** — 원격에 새 커밋 %d개%s (`%s`)" % (이름, behind, 꼬리, repo))
    줄 += [
        "",
        "**여기 적힌 폴더의 코드를 읽거나 고치기 전에 먼저 사용자에게 알리고 "
        "`git -C <폴더> pull` 승인을 받으십시오.** 원격에서 이미 끝난 일을 다시 "
        "만드는 사고가 2026-09-08에 실제로 있었습니다. 낡은 코드를 근거로 "
        "\"이 기능은 없다\"고 단정하지 마십시오.",
    ]
    print("\n".join(줄))


def mode_pretool():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    target = (payload.get("tool_input") or {}).get("file_path") or ""
    if not target:
        return
    folder = os.path.dirname(os.path.abspath(target))
    if not os.path.isdir(folder):
        return
    repo = git(folder, "rev-parse", "--show-toplevel")
    if not repo:
        return
    if fetch_age(repo) > FETCH_MAX_AGE:
        refresh(repo, PRETOOL_FETCH_TIMEOUT)
    ba = behind_ahead(repo)
    if not ba or ba[0] == 0:
        return
    behind = ba[0]
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "이 파일이 속한 저장소(%s)가 원격보다 커밋 %d개만큼 뒤처져 있습니다. "
                "낡은 코드 위에 고치면 원격에서 이미 끝난 일을 다시 만들게 됩니다. "
                "먼저 `git -C %s pull`로 맞춘 뒤 다시 고치는 것을 권합니다."
                % (os.path.basename(repo), behind, repo)
            ),
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    모드 = sys.argv[1] if len(sys.argv) > 1 else "session"
    try:
        if 모드 == "pretool":
            mode_pretool()
        else:
            mode_session()
    except Exception:
        pass    # 검사가 실패해도 세션을 막지 않는다
