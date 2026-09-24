#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""배포된 판이 저장소 최신 판보다 뒤처졌는지 검사한다.

왜 만들었나
-----------
2026-09-08에 나무에 쌓인 교훈 264건을 부류로 나눠 세어 보니, '배포·판 어긋남'이
교훈 20건·실패 3건으로 두 번째로 큰 부류였다. 그 안에서 같은 모양이 네 번
되풀이됐다.

  2026-07-31  겉 판을 올려도 안에 실린 코어는 따라오지 않는다 —
              v0.1.13 배포는 성공했는데 속에 든 기억 엔진은 2주 전 것이었다
  2026-07-31  코어를 품고 미러링하는 서비스에서는 핀만 올려도 소용없다
  2026-08-14  "빌려 쓰는 사본이 아직 낡아서"를 이유로 방어선을 낮추면 배포 시점에 어긋난다
  2026-09-04  코어를 고쳐도 클라우드가 안 따라오는 자리가 있다

여기에 경보가 없다는 기록도 따로 있다.

  2026-08-02  개인용 원격 MCP만 4단계 뒤처져도 아무 경보가 없다 —
              발견은 사용자의 육안 질문이었다

무엇을 재나
-----------
  돌고 있는 판   미니PC의 컨테이너 이미지 꼬리표(docker ps에 그대로 찍힌다)
  저장소 판      그 서비스를 만드는 저장소의 원격 최신 태그
  빌린 본체 판   vendor/namu-agent가 붙들고 있는 태그 대 본체 원격 최신 태그

잣대는 반드시 원격 최신 태그다
------------------------------
2026-08-01 교훈: "재발방지 검사의 잣대를 '다른 배포 대상이 지금 쓰는 값'으로 두면,
둘 다 뒤처졌을 때 통과가 나온다 — 잣대는 진실의 원천이어야 한다."
그래서 로컬 태그 목록을 믿지 않고 매번 원격에 물어본다(git ls-remote).

감시 대상은 코드가 아니라 설정에 적는다
---------------------------------------
어느 컨테이너를 보고 어느 저장소를 잣대로 삼을지는 기계마다 다르다. 그래서
감시 대상은 코드가 아니라 `~/.namu/config/version_targets.json` 에 적는다. 이
폴더는 기계끼리 동기화되므로 설정도 함께 따라간다. 설정이 없는 기계에서는
검사할 대상이 없다는 뜻이므로 아무 말도 하지 않고 조용히 끝낸다.

알리기만 하고 막지 않는다. 무엇을 배포할지는 사람이 정한다.
집 밖이라 미니PC에 못 닿으면 돌고 있는 판 검사만 조용히 건너뛴다.
"""

import json
import os
import re
import subprocess
import sys
import time

LS_REMOTE_TIMEOUT = 12      # 원격 태그를 물어보는 데 기다릴 초
SSH_TIMEOUT = 15            # 미니PC에 물어보는 데 기다릴 초
CACHE_MAX_AGE = 1800        # 이 초보다 오래된 결과만 다시 잰다(30분)
CACHE_PATH = os.path.expanduser("~/.cache/claude-version-drift.json")
설정_경로 = os.path.expanduser("~/.namu/config/version_targets.json")

TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _표준출력_utf8():
    """표준출력을 UTF-8로 맞춘다.

    한글 윈도우에서 훅의 표준출력이 파이프면 기본 인코딩이 cp949라, 🌳·⚠ 같은 글자를
    찍는 순간 UnicodeEncodeError가 나고 맨 끝의 넓은 except가 그것을 삼켜 **알림이
    소리 없이 사라진다**(session_recall.py에서 먼저 겪은 버그와 같다 —
    test_session_recall_encoding.py). 바꿀 수 없는 스트림이면 그대로 둔다.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def 목록_읽기(데이터, 키, 칸들):
    """설정의 목록 하나를 (칸1, 칸2, 이름) 꼴로 바꾼다. 없으면 빈 목록."""
    항목들 = 데이터.get(키)
    if not isinstance(항목들, list):
        return []          # 목록이 없으면 그 검사만 건너뛴다
    나온것 = []
    for 항목 in 항목들:
        if not isinstance(항목, dict):
            continue
        값 = [str(항목.get(칸) or "").strip() for 칸 in 칸들]
        if all(값):
            나온것.append(tuple(값))
    return 나온것


def 설정_읽기():
    """감시 대상 설정을 읽는다. 없거나 읽을 수 없으면 None.

    이 플러그인은 공개 저장소에 있어서 다른 사람도 설치할 수 있다. 그 사람들에게는
    미니PC도 해당 컨테이너도 없으므로, 설정이 없으면 아무 말도 하지 않고 끝낸다.
    """
    try:
        with open(설정_경로, encoding="utf-8") as f:
            데이터 = json.load(f)
    except Exception:
        return None
    if not isinstance(데이터, dict):
        return None
    return {
        # 비어 있으면 컨테이너 검사만 건너뛴다 — 빌린 본체 검사는 그대로 한다
        "ssh_호스트": str(데이터.get("ssh_호스트") or "").strip(),
        "돌고_있는_판": 목록_읽기(데이터, "돌고_있는_판",
                                ("컨테이너", "저장소", "이름")),
        "빌린_본체": 목록_읽기(데이터, "빌린_본체", ("사본", "저장소", "이름")),
    }


def 판_숫자(tag):
    """'v0.1.77' 을 (0, 1, 77) 로 바꾼다. 모양이 다르면 None."""
    m = TAG_RE.match((tag or "").strip())
    return tuple(int(g) for g in m.groups()) if m else None


def 조사(말, 받침있음, 받침없음):
    """앞말의 끝 글자에 받침이 있는지 보고 조사를 고른다."""
    끝 = (말 or "")[-1:]
    if not 끝 or not ("가" <= 끝 <= "힣"):
        return 받침없음
    return 받침있음 if (ord(끝) - 0xAC00) % 28 else 받침없음


def git(repo, *args, timeout=10):
    try:
        # 인코딩을 적지 않으면 윈도우에서 cp949로 읽는다(repo_sync_check.git과 같은 까닭).
        r = subprocess.run(["git", "-C", repo, *args],
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except Exception:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def 원격_태그들(repo):
    """원격이 갖고 있는 판 목록. 이것이 잣대다 — 로컬 태그는 믿지 않는다."""
    out = git(repo, "ls-remote", "--tags", "origin", timeout=LS_REMOTE_TIMEOUT)
    if out is None:
        return None
    태그 = set()
    for 줄 in out.splitlines():
        이름 = 줄.rsplit("refs/tags/", 1)[-1].removesuffix("^{}")
        if 판_숫자(이름):
            태그.add(이름)
    return sorted(태그, key=판_숫자) or None


def 돌고_있는_판(ssh_호스트):
    """설정에 적힌 기계의 컨테이너 이미지 꼬리표를 읽는다. 못 닿으면 None."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
             ssh_호스트, "docker ps --format '{{.Names}}\\t{{.Image}}'"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=SSH_TIMEOUT,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    표 = {}
    for 줄 in r.stdout.splitlines():
        줄 = 줄.strip().strip("'")
        if "\t" not in 줄:
            continue
        이름, 이미지 = 줄.split("\t", 1)
        표[이름.strip()] = 이미지.strip().rsplit(":", 1)[-1] if ":" in 이미지 else None
    return 표


def 뒤처진_판_수(현재, 태그들):
    """현재 판보다 뒤에 나온 판이 몇 개인지 센다."""
    n = 판_숫자(현재)
    if n is None:
        return None
    return sum(1 for t in 태그들 if 판_숫자(t) > n)


def 캐시_읽기(base):
    """30분 안에 **같은 일감 폴더**에서 잰 결과가 있으면 그것을 돌려준다. 없으면 None.

    검사 결과는 일감 폴더(`base`)에 따라 달라진다 — 저장소와 빌린 본체를 그 폴더
    아래에서 찾기 때문이다. 캐시 파일은 기계에 하나뿐이라, 잰 폴더를 함께 적어 두고
    대조하지 않으면 다른 폴더에서 연 세션이 앞 폴더의 결과(경보든 침묵이든)를 30분
    동안 그대로 받는다. 폴더가 다르면 새로 잰다.
    """
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            데이터 = json.load(f)
        if 데이터.get("기준") != os.path.abspath(base):
            return None
        if time.time() - 데이터.get("잰_때", 0) < CACHE_MAX_AGE:
            return 데이터.get("줄")
    except Exception:
        pass
    return None


def 캐시_쓰기(base, 줄):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"잰_때": time.time(), "기준": os.path.abspath(base), "줄": 줄},
                      f, ensure_ascii=False)
    except Exception:
        pass


def 검사(base, 설정):
    """어긋난 것들의 설명 줄 목록을 돌려준다. 다 맞으면 빈 목록."""
    어긋남 = []
    최신 = {}   # 저장소 폴더 이름 -> 원격 태그 목록

    def 태그들(폴더):
        if 폴더 not in 최신:
            경로 = os.path.join(base, 폴더)
            최신[폴더] = 원격_태그들(경로) if os.path.isdir(경로) else None
        return 최신[폴더]

    # 1. 돌고 있는 판 대 저장소 최신 판
    #    ssh 호스트가 비어 있으면 이 검사만 건너뛴다
    돌고 = (돌고_있는_판(설정["ssh_호스트"])
           if 설정["ssh_호스트"] and 설정["돌고_있는_판"] else None)
    if 돌고 is not None:
        for 컨테이너, 폴더, 이름 in 설정["돌고_있는_판"]:
            현재 = 돌고.get(컨테이너)
            목록 = 태그들(폴더)
            if not 현재 or not 목록:
                continue
            n = 뒤처진_판_수(현재, 목록)
            if n:
                어긋남.append(
                    "- **%s**%s %s로 돌고 있는데 저장소 최신은 %s입니다 — %d판 뒤처졌습니다"
                    % (이름, 조사(이름, "이", "가"), 현재, 목록[-1], n))

    # 2. 빌려 쓰는 본체 핀 대 본체 최신 판
    for 사본, 본체, 이름 in 설정["빌린_본체"]:
        경로 = os.path.join(base, 사본)
        if not os.path.isdir(경로):
            continue
        핀 = git(경로, "describe", "--tags", "--abbrev=0")
        목록 = 태그들(본체)
        if not 핀 or not 목록:
            continue
        n = 뒤처진_판_수(핀, 목록)
        if n:
            어긋남.append(
                "- **%s**%s %s에 멈춰 있는데 본체 최신은 %s입니다 — %d판 뒤처졌습니다"
                % (이름, 조사(이름, "이", "가"), 핀, 목록[-1], n))
    return 어긋남


def main():
    설정 = 설정_읽기()
    if 설정 is None:
        return      # 감시 대상을 적어 두지 않은 기계다 — 조용히 끝낸다
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    줄 = 캐시_읽기(base)
    if 줄 is None:
        줄 = 검사(base, 설정)
        캐시_쓰기(base, 줄)
    if not 줄:
        return      # 다 맞으면 아무 말도 하지 않는다
    print("\n".join(
        ["### ⚠ 배포된 판이 저장소 최신 판보다 뒤처져 있습니다", ""]
        + 줄
        + ["",
           "**배포하라는 지시를 받으면 여기 적힌 것부터 사용자에게 알리십시오.** "
           "겉 판만 올리고 안에 실린 본체는 낡은 채로 나가는 사고가 2026-07-31과 "
           "2026-09-04에 실제로 있었습니다. 판이 맞는지는 \"빌드했다\"는 로그가 "
           "아니라 지금 돌고 있는 것의 꼬리표로 확인하십시오."]))


if __name__ == "__main__":
    _표준출력_utf8()
    try:
        main()
    except Exception:
        pass    # 검사가 실패해도 세션을 막지 않는다
