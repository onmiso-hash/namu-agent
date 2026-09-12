"""sessions.yaml 스토어 — 세션 측정 그릇(namu-self-improvement-loop).

세션이 끝날 때 나이테를 **그 세션 하나에만** 돌려 나온 값을 담는다. 쓰는 곳은 세션
종료 훅(hooks/session_end_naite.py) 하나뿐이고, 읽는 곳은 주간 점검
(naite/weekly_check.py) 하나뿐이다.

왜 이 그릇이 필요한가
---------------------
주간 점검의 주된 지표인 "세션당 어긋남 건수"는 대화 기록(`~/.claude/projects`)에서
계산한다. 그런데 그 대화 기록은 두 가지 성질을 갖는다.

1. 동기화되지 않는다. 그 기계에서 연 세션만 있고, 웹에서 연 세션은 아예 없다.
2. 약 28일이 지나면 사라진다. 2026-09-08에 몇 시간 사이에 파일 98개가 94개로 줄고
   가장 오래된 날이 08-09에서 08-11로 밀리는 것을 실제로 관측했다.

그래서 그때그때 재서 남겨 두지 않으면 "지난주보다 나아졌는가"를 나중에 영영 답할 수
없다. 기억은 동기화되므로, 이 그릇에 남기면 어느 기계에서 연 세션이든 한자리에서
합산된다.

왜 숫자만이 아니라 사람 발화 원문까지 담는가
--------------------------------------------
숫자만 남기면 판정 규칙을 고쳤을 때 과거를 다시 잴 수 없다. 2026-09-09에 실제로 그
재측정을 해서 되돌림 판정의 오탐을 27%에서 19%로 줄인 일이 있다. 원문이 함께 있으면
규칙을 고친 뒤 지나간 세션에 다시 적용할 수 있다. 2026-09-11 실측으로 한 달치가 약
39KB이므로 저장소에 부담이 되지 않는다.

요청 중단과 도구 거절은 발화가 아니라 기록 줄에 붙은 표지라 원문으로 복원되지
않는다. 그래서 그 시각 목록(`interrupts`·`denials`)을 따로 담는다 — 이 둘이 있어야
나중에 `naite.되돌림_찾기`의 결과를 그대로 재현할 수 있다.

형식
----
profile.yaml·attachments.yaml과 같은 append-only 다중 문서(`---` 구분)다. 같은
세션을 이어서 열면(`--resume`) 항목이 하나 더 붙는다. 고쳐 쓰지 않으므로, 합산하는
쪽은 session_id마다 **마지막 항목 하나만** 세어야 한다(`latest_by_session`).
"""
from datetime import datetime

import yaml
from ulid import ULID

import config as cfg


def _sessions_path(paths: "cfg.DataPaths | None" = None):
    p = paths or cfg.data_paths_for()
    return p.sessions_yaml or cfg.SESSIONS_YAML_PATH


def record_session(
    session_id: str,
    misalignments: int,
    structural_marks: int,
    utterances: list,
    interrupts: list | None = None,
    denials: list | None = None,
    project: str | None = None,
    title: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    end_reason: str | None = None,
    paths: "cfg.DataPaths | None" = None,
) -> str:
    """세션 하나의 측정값을 남기고 id를 반환한다(append-only).

    `utterances`는 `{"at": 시각, "text": 원문}` 목록이다. 시각은 대화 기록에 적힌
    형식을 그대로 옮긴다 — 나이테가 그 형식을 전제로 정렬하므로 여기서 바꾸면
    재측정 결과가 원래와 달라진다.
    """
    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("session_id는 필수입니다")

    doc = {
        "id": str(ULID()),
        "timestamp": cfg.now().isoformat(),
        "machine": cfg.NAMU_MACHINE,
        "session_id": session_id,
        "project": project,
        "title": title,
        "summary": "어긋남 %d건 · 구조 표지 %d건 · 사람 발화 %d건 (%s)" % (
            int(misalignments), int(structural_marks), len(utterances), project or "?",
        ),
        "misalignments": int(misalignments),
        "structural_marks": int(structural_marks),
        "utterance_count": len(utterances),
        "started_at": started_at,
        "ended_at": ended_at,
        "end_reason": end_reason,
        "interrupts": list(interrupts or []),
        "denials": list(denials or []),
        "utterances": utterances,
    }

    yaml_path = _sessions_path(paths)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(
        doc, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    return doc["id"]


def load_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """기록 전부를 적은 순서(오래된 것 먼저)로 반환. 파일이 없으면 빈 목록.

    깨진 yaml에 예외를 던지지 않는 것은 memo.load_all·attachments.load_all과 같은
    판단이다 — 한 항목이 깨졌다고 주간 점검 전체가 실패하면 손해가 훨씬 크다.
    """
    yaml_path = _sessions_path(paths)
    try:
        raw = yaml_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        docs = list(yaml.safe_load_all(raw))
    except yaml.YAMLError:
        return []
    return [d for d in docs if isinstance(d, dict) and d.get("session_id")]


def latest_by_session(paths: "cfg.DataPaths | None" = None) -> dict:
    """session_id마다 마지막 항목 하나씩 반환한다.

    같은 세션을 이어서 열면 항목이 또 붙고, 그 항목은 앞 항목의 발화를 전부 포함한
    더 긴 기록이다. 둘을 다 세면 어긋남이 두 배로 보인다.
    """
    latest: dict = {}
    for entry in load_all(paths):
        latest[str(entry["session_id"])] = entry
    return latest


def entry_time(entry: dict) -> "datetime | None":
    """이 세션이 언제 것인지 가리는 시각. 첫 발화 시각을 우선한다.

    timestamp(적은 시각)가 아니라 첫 발화 시각을 쓰는 이유: `--resume`으로 오래된
    세션을 오늘 이어서 열면 적은 시각은 오늘이 되지만, 그 세션이 실제로 벌어진 때는
    처음 연 날이다. 기간을 나눠 견줄 때 그 둘이 갈리면 같은 세션이 주마다 옮겨 다닌다.

    **글자로 견주지 않고 시각으로 바꿔서 돌려준다.** 대화 기록의 시각은 세계 표준시에
    `Z`가 붙은 형식이고 나무가 적는 시각은 `+09:00`이 붙은 형식이라, 문자열끼리
    견주면 같은 순간이 다른 순서로 줄을 선다.
    """
    for 칸 in ("started_at", "timestamp"):
        값 = entry.get(칸)
        if not 값:
            continue
        try:
            return datetime.fromisoformat(str(값).replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def since(기준시각: "datetime", paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """그 시각 이후에 시작된 세션의 측정값만, 세션마다 하나씩 반환한다.

    시각을 읽을 수 없는 항목은 뺀다 — 언제 것인지 모르는 값을 기간별 비교에 넣으면
    그 기간의 평균이 조용히 틀어진다.
    """
    골라낸 = []
    for entry in latest_by_session(paths).values():
        때 = entry_time(entry)
        if 때 is not None and 때 >= 기준시각:
            골라낸.append(entry)
    return 골라낸
