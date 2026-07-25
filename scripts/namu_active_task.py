#!/usr/bin/env python3
"""NAMU 열린 task 목록 — Claude Code & agy `/namu` 스킬 공용. 단일 출처에서 출력.

기본 출력은 slug 한 줄씩(가장 최근 활동 순). 예전에는 "활성 task 1개"만 찍었는데,
실측상 열린 task가 여럿인데도 1개만 보이는 게 브리핑이 계속 빗나간 원인이었다
(namu-57 증상 A) — 목록을 전부 넘기고 무엇을 이어갈지는 사용자가 고르게 한다.
하위 호환: 첫 줄은 여전히 예전과 같은 task(가장 최근 활동)이고, 열린 task가
1개뿐이면 출력이 예전과 완전히 동일하다. 0개면 빈 출력.

`--json`을 주면 브리핑에 필요한 항목(slug/title/최근 ts/다음 할 일)까지 함께
내보낸다 — 스킬이 task 폴더 여러 개를 손으로 파싱하지 않아도 되도록.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "namu-plugin"))
from task_resolve import open_tasks_briefing, tasks_root_for


def _collect() -> list[dict]:
    # tasks 저장 위치는 개인 풀 ~/.namu/tasks/<basename(cwd)>/(namu-34) — 메모리 루트
    # (cfg.NAMU_DATA_ROOT)과는 무관하게 항상 현재 프로젝트 폴더(cwd)의 폴더명을 키로 찾는다.
    # statusLine/브리핑 훅과 동일 규칙.
    #
    # 코어 로직(열린 task 나열 + next 추출)은 task_resolve.open_tasks_briefing에
    # 단일화됐다(namu-57 2단계 보완, namu_recall 도구와 공유) — 이 스크립트는 project
    # 하나로 좁혀 호출하고, 기존 출력 계약(slug/title/last_ts/next, project 키 없음)을
    # 지키려고 project 키만 벗겨낸다.
    project = tasks_root_for(os.getcwd()).name
    rows = open_tasks_briefing([project])
    return [
        {"slug": r["slug"], "title": r["title"], "last_ts": r["last_ts"], "next": r["next"]}
        for r in rows
    ]


def main() -> None:
    as_json = "--json" in sys.argv[1:]
    try:
        rows = _collect()
    except Exception:
        # 브리핑은 읽기 전용 보조 기능 — 어떤 이유로든 실패하면 조용히 빈 출력
        rows = []

    if as_json:
        print(json.dumps(rows, ensure_ascii=False))
        return
    for row in rows:
        print(row["slug"])


if __name__ == "__main__":
    main()
