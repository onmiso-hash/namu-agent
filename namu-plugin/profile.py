"""profile.yaml 스토어 — 개인 사실 그릇(namu-49에서 두 번째 그릇으로 생겼다. 지금
그릇 목록은 `config.BOWLS`가 정한다).

learnings.yaml(교훈/대화기록)과 달리 profile.yaml은 사실·선호(fact)만 담는다.
원본은 이 파일이고 통째 로딩한다 — 검색 색인(`db`의 `bowl_profile` 표)은 이 원본에서
다시 만드는 캐시일 뿐이다(fts5-memo-tasks-index 이후). append-only + supersedes
포인터로 정정을 표현한다(수정·삭제 금지 — db.py의 learnings와 같은 원칙).
"""
import re

import yaml
from ulid import ULID

import config as cfg

_VALID_VERIFIED_BY = {"human", "ai", "unverified"}


def record_fact(
    subject: str,
    statement: str | None = None,
    source: str | None = None,
    supersedes: str | None = None,
    verified_by: str = "human",
    tags: list | None = None,
    via: str | None = None,
    paths: "cfg.DataPaths | None" = None,
    *,
    summary: str | None = None,
    reason: str | None = None,
    body: str | None = None,
) -> str:
    """개인 사실 한 건을 남긴다(append-only).

    namu-65 3단계로 3층(summary/reason/body)을 도입했다. 옛 이름과의 관계:
    `statement` → `summary`(한 줄) + `body`(상세), `source` → `reason`(어떻게 아는가).
    축 이름인 `subject`는 그대로 둔다 — 교훈 그릇에서 `task`를 유지한 것과 같은
    판단이다(저장 키를 바꾸면 읽는 곳이 한꺼번에 흔들린다).

    옛 이름으로 부르면 새 칸으로 **옮겨 저장한다** — 말없이 버리지 않는다. 새 이름과
    옛 이름을 함께 주면 새 이름이 이긴다(입력 경계가 이미 그 조합을 거절하므로 여기까지
    오지 않는다).
    """
    if summary is None and statement is not None:
        summary = statement
    if reason is None and source is not None:
        reason = source

    if not reason:
        raise ValueError("reason(어떻게 아는가)은 필수입니다")
    if verified_by not in _VALID_VERIFIED_BY:
        raise ValueError(f"verified_by는 {_VALID_VERIFIED_BY} 중 하나여야 합니다")

    if tags is None:
        tags = []

    p = paths or cfg.data_paths_for()

    entry_id = str(ULID())
    # 기준 시간대(cfg.now)로 찍는다 — namu-71. db.record와 같은 이유로 여기만 UTC였다.
    timestamp = cfg.now().isoformat()
    machine = cfg.NAMU_MACHINE

    doc = {
        "id": entry_id,
        "timestamp": timestamp,
        "subject": subject,
        "summary": summary,
        "reason": reason,
        "body": body,
        "supersedes": supersedes,
        "machine": machine,
        "verified_by": verified_by,
        "tags": tags,
        "via": via,
    }

    yaml_path = p.profile_yaml
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    return entry_id


def layers(doc: dict) -> tuple[str, str, str]:
    """항목 하나에서 (summary, reason, body)를 꺼낸다. **읽는 쪽은 전부 이걸 쓴다.**

    3층 이전에 쌓인 항목은 `statement`/`source`라는 옛 이름을 갖고 있다. 폴백을 읽는
    곳마다 따로 적으면 한 곳만 빠뜨려도 그 화면에서만 사실이 빈칸으로 보이는데,
    그런 실패는 예외가 아니라 침묵이라 오래 발견되지 않는다(namu-62 훅 오탐과 같은
    함정). 그래서 폴백을 여기 한 곳에만 둔다.
    """
    summary = doc.get("summary") or doc.get("statement") or ""
    reason = doc.get("reason") or doc.get("source") or ""
    body = doc.get("body") or ""
    return str(summary), str(reason), str(body)


# 문서 경계 줄. record_fact는 언제나 `---` 한 줄 뒤에 문서를 붙이고, safe_dump는 여러 줄
# 값을 들여쓰므로 본문 안에서 이 줄이 맨 앞에 설 일이 없다.
_DOC_SEPARATOR = re.compile(r"^---[ \t]*$", re.MULTILINE)


def _load(paths: "cfg.DataPaths | None" = None) -> tuple[list[dict], list[str]]:
    """(읽은 항목들, 건너뛴 문제 목록). 읽는 쪽은 `load_all`/`active`/`problems`를 쓴다.

    ## 왜 예외를 밖으로 내지 않는가 (2026-09-25 검토 실측)

    문서 하나가 깨지거나(따옴표·괄호가 안 닫힘) 사전이 아닌 문서(목록 등)가 끼면
    예전에는 예외가 그대로 올라가 **`namu_recall` 전체가 실패**했다 — 쪽지·교훈·열린
    작업까지 한꺼번에 안 보인다. git 병합이나 손 편집으로 충분히 생길 수 있는 일이다.
    쪽지 그릇(`memo.load_all`)은 같은 상황을 빈 목록으로 흡수한다.

    다만 쪽지처럼 **말없이 삼키지는 않는다**. 개인 사실은 "상시" 재알림처럼 매번
    기대는 기억이라, 하나가 조용히 빠지면 AI가 그 사실을 모른 채 일하게 된다 — 그래서
    건너뛴 것을 문제 목록으로 돌려주고 `namu_recall`이 `warnings`에 싣는다.

    성한 파일은 예전과 똑같이 한 번에 읽는다. 깨졌을 때만 `---` 경계로 잘라 문서마다
    따로 읽어, 깨진 문서 하나만 빼고 나머지는 살린다.
    """
    p = paths or cfg.data_paths_for()
    yaml_path = p.profile_yaml
    try:
        raw = yaml_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"개인 사실 파일을 읽지 못했습니다({yaml_path}): {exc}"]

    problems: list[str] = []
    try:
        docs = list(yaml.safe_load_all(raw))
    except yaml.YAMLError:
        docs = []
        for number, chunk in enumerate(_DOC_SEPARATOR.split(raw)):
            if not chunk.strip():
                continue
            try:
                docs.append(yaml.safe_load(chunk))
            except yaml.YAMLError as exc:
                where = getattr(exc, "problem_mark", None)
                line = f" {where.line + 1}째 줄 근처" if where is not None else ""
                problems.append(
                    f"개인 사실 파일({yaml_path.name})의 {number}번째 문서가 깨져 건너뛰었습니다"
                    f"({type(exc).__name__}{line}) — 파일을 열어 고쳐 주세요."
                )

    result: list[dict] = []
    skipped_non_dict = 0
    for doc in docs:
        if not doc:
            continue
        if isinstance(doc, dict):
            result.append(doc)
        else:
            skipped_non_dict += 1
    if skipped_non_dict:
        problems.append(
            f"개인 사실 파일({yaml_path.name})에 항목 모양이 아닌 문서 {skipped_non_dict}개가 "
            "있어 건너뛰었습니다(목록·글자 한 줄 등) — 파일을 열어 고쳐 주세요."
        )
    return result, problems


def load_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """읽을 수 있는 항목 전부(적힌 순서). 깨진 문서는 건너뛴다 — 무엇을 건너뛰었는지는
    `problems`가 말한다."""
    return _load(paths)[0]


def problems(paths: "cfg.DataPaths | None" = None) -> list[str]:
    """개인 사실 파일에서 읽지 못하고 건너뛴 것들(사람에게 보일 문장). 성하면 빈 목록."""
    return _load(paths)[1]


def active(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """다른 어떤 항목의 supersedes 값으로도 지목되지 않은 항목만(원래 순서 유지)."""
    docs = load_all(paths=paths)
    superseded_ids = {d.get("supersedes") for d in docs if d.get("supersedes")}
    return [d for d in docs if d.get("id") not in superseded_ids]
