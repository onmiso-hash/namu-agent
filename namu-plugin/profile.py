"""profile.yaml 스토어 — 2그릇 메모리(namu-49)의 두 번째 그릇.

learnings.yaml(교훈/대화기록)과 달리 profile.yaml은 사실·선호(fact)만 담는다.
작은 데이터라 SQLite 캐시 없이 통째 로딩한다. append-only + supersedes 포인터로
정정을 표현한다(수정·삭제 금지 — db.py의 learnings와 같은 원칙).
"""
from datetime import datetime, timezone

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
    timestamp = datetime.now(timezone.utc).isoformat()
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


def load_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    p = paths or cfg.data_paths_for()
    yaml_path = p.profile_yaml
    if not yaml_path.exists():
        return []
    return [d for d in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")) if d]


def active(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """다른 어떤 항목의 supersedes 값으로도 지목되지 않은 항목만(원래 순서 유지)."""
    docs = load_all(paths=paths)
    superseded_ids = {d.get("supersedes") for d in docs if d.get("supersedes")}
    return [d for d in docs if d.get("id") not in superseded_ids]
