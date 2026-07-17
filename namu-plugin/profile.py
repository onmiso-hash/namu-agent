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
    statement: str,
    source: str,
    supersedes: str | None = None,
    verified_by: str = "human",
    tags: list | None = None,
) -> str:
    if not source:
        raise ValueError("source는 필수입니다")
    if verified_by not in _VALID_VERIFIED_BY:
        raise ValueError(f"verified_by는 {_VALID_VERIFIED_BY} 중 하나여야 합니다")

    if tags is None:
        tags = []

    entry_id = str(ULID())
    timestamp = datetime.now(timezone.utc).isoformat()
    machine = cfg.NAMU_MACHINE

    doc = {
        "id": entry_id,
        "timestamp": timestamp,
        "subject": subject,
        "statement": statement,
        "source": source,
        "supersedes": supersedes,
        "machine": machine,
        "verified_by": verified_by,
        "tags": tags,
    }

    yaml_path = cfg.PROFILE_YAML_PATH
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    return entry_id


def load_all() -> list[dict]:
    yaml_path = cfg.PROFILE_YAML_PATH
    if not yaml_path.exists():
        return []
    return [d for d in yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")) if d]


def active() -> list[dict]:
    """다른 어떤 항목의 supersedes 값으로도 지목되지 않은 항목만(원래 순서 유지)."""
    docs = load_all()
    superseded_ids = {d.get("supersedes") for d in docs if d.get("supersedes")}
    return [d for d in docs if d.get("id") not in superseded_ids]
