"""캐릭터 그릇 — 이름을 부르면 같은 성격과 기억으로 나타나는 캐릭터(설계서: 나무 캐릭터 v0.1).

## 왜 다른 그릇과 모양이 다른가

다른 그릇은 "파일 하나에 문서를 덧붙이는" 모양이다. 캐릭터는 그렇게 두지 않고
**항목 하나를 파일 하나로** 둔다.

    memory/character/<캐릭터 id>/card/<판 id>.yaml     카드(고칠 때마다 새 판)
    memory/character/<캐릭터 id>/diary/<id>.yaml       일기(2단계)
    memory/character/<캐릭터 id>/core/<id>.yaml        확정된 핵심 기억(2단계)
    memory/character/<캐릭터 id>/pending/<id>.yaml     확인 대기 후보(2단계)

이유는 잊기(forget, 3단계) 때문이다. 캐릭터 일기는 사용자가 "잊어줘"라고 하면 실제로
지워야 한다. 줄 단위 병합(union)을 거는 파일에서 줄을 지우면 다른 PC와 병합할 때
**지운 줄이 되살아난다**(쪽지 그릇을 따로 만든 이유와 같다). 항목마다 파일을 두면
추가는 새 파일, 잊기는 파일 삭제라 두 PC가 동시에 써도 병합이 깨끗하다.

관계 상태(호감도·단계·호칭)는 **저장하지 않는다.** 카드의 시작점과 일기들에서 매번
계산한다 — 웹과 터미널에서 동시에 일기를 써도 서로 덮어쓸 값이 없게 하기 위해서다.

## 칸막이

`config.BOWLS`에 `web_exposed=False, cached=False`로 등록돼 있어 `namu_record`로 쓸 수
없고 검색 색인·recall에도 안 나온다. 업무용으로 나무를 쓸 때 캐릭터 일기가 섞여 나오지
않게 하는 것이 설계 7장의 요구다. 읽고 쓰는 길은 캐릭터 도구(`namu_character_*`)뿐이다.

## 질문 목록과 카드 모양은 여기 한 곳

`schema()`가 돌려주는 것이 유일한 정의다. 홈페이지 생성기와 대화로 만들기가 모두 이것을
받아 쓴다(설계서 5.1 — 붕어빵 틀은 하나).
"""
import contextlib
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

import yaml
from ulid import ULID

import config as cfg

SCHEMA_VERSION = 1

# 사용자가 바꿀 수 없는 약속. 카드에 무엇이 들어오든 서버가 이 값으로 덮는다.
PROMISES = (
    "AI임을 숨기지 않기",
    "질투나 서운함으로 붙잡지 않기",
    "현실의 관계와 일상을 응원하기",
    "확실하지 않은 기억은 지어내지 않기",
)

# 관계 시작점 — 값, 화면 이름, 설명, 호감도 시작값(설계서 6장).
STARTS = (
    {"value": "stranger", "label": "처음 만난 사이", "desc": "서로 알아가는 데서 시작해요.",
     "affection": 10},
    {"value": "friend", "label": "친한 친구 사이", "desc": "이미 편한 사이에서 시작해요.",
     "affection": 45},
    {"value": "lover", "label": "이미 연인 사이", "desc": "연인 관계에서 시작해요.",
     "affection": 80},
)

# 관계 천장 — rank가 클수록 높다. 시작점보다 낮은 천장은 고를 수 없다.
CEILINGS = (
    {"value": "friend", "label": "좋은 친구까지",
     "desc": "편하게 기대고 응원해주는 친구 사이로 지내요.", "rank": 1},
    {"value": "crush", "label": "설레는 사이까지",
     "desc": "친구보다 조금 더, 서로 설렘을 느끼는 사이까지 갈 수 있어요.", "rank": 2},
    {"value": "lover", "label": "연인까지",
     "desc": "대화가 쌓이면 연인 관계로 깊어질 수 있어요.", "rank": 3},
    {"value": "open", "label": "정하지 않고 열어두기",
     "desc": "관계가 흘러가는 대로 두고, 나중에 정해요.", "rank": 9},
)

# 시작점마다 허용되는 가장 낮은 천장의 rank. 연인에서 시작하면 연인이나 열어두기만 된다.
START_MIN_CEILING_RANK = {"stranger": 1, "friend": 1, "lover": 3}

# 관계 단계(설계서 6장 초안). (하한, 값, 설명)
STAGES = (
    (0, "stranger", "처음 만난 사이"),
    (20, "acquaintance", "알아가는 사이"),
    (40, "friend", "친구"),
    (60, "crush", "설레는 사이"),
    (80, "lover", "연인"),
)

# 천장이 막는 가장 높은 단계. open은 막지 않는다.
CEILING_MAX_STAGE = {"friend": "friend", "crush": "crush", "lover": "lover", "open": "lover"}

AFFECTION_MIN = 0
AFFECTION_MAX = 100

# 질문 목록(설계서 11장 프로토타입의 STEPS와 같은 순서). key는 카드 칸 이름이다.
# max_length·max_items는 초안 값이다 — 불러오기 결과를 가볍게(약 3천 토큰) 두기 위한 상한.
QUESTIONS = (
    {"key": "name", "label": "이름", "title": "이름을 지어주세요",
     "hint": "캐릭터가 스스로를 소개할 때 쓰는 이름이에요.",
     "type": "single", "required": True, "max_length": 20,
     "options": ["하린", "도윤", "루아", "새벽"], "custom_label": "다른 이름 입력"},
    {"key": "aliases", "label": "별명", "title": "다르게 부르는 이름이 있나요?",
     "hint": '"린아 불러줘"처럼 별명으로도 부를 수 있게 해요. 세 개까지, 없으면 넘어가도 돼요.',
     "type": "multi", "required": False, "max_items": 3, "max_length": 20,
     "options": [], "custom_label": "별명 입력 후 추가"},
    {"key": "personality", "label": "성격", "title": "기본 성격은 어떤가요?",
     "hint": "두 개까지 고를 수 있어요. 직접 쓴 것도 하나로 쳐요.",
     "type": "multi", "required": True, "max_items": 2, "max_length": 40,
     "options": ["다정하고 차분함", "밝고 장난기 많음", "겉은 무뚝뚝, 속은 따뜻함",
                 "지적이고 대화가 잘 통함"],
     "custom_label": "성격 직접 입력"},
    {"key": "speech", "label": "말투", "title": "말투는 어떻게 할까요?",
     "hint": "캐릭터의 첫인상을 가장 크게 좌우해요.",
     "type": "single", "required": True, "max_length": 60,
     "options": ["반말", "존댓말", "처음엔 존댓말, 친해지면 반말"],
     "custom_label": "말투 직접 입력"},
    {"key": "emoji", "label": "이모지", "title": "이모지는 얼마나 쓸까요?", "hint": "",
     "type": "single", "required": False, "max_length": 20,
     "options": ["자주 써요", "가끔 써요", "거의 안 써요"], "custom_label": "직접 입력"},
    {"key": "call_user", "label": "나를 부르는 호칭", "title": "나를 뭐라고 부를까요?",
     "hint": "관계가 깊어지면 호칭이 바뀔 수도 있어요.",
     "type": "single", "required": True, "max_length": 20,
     "options": ["허니", "내 이름으로", "자기야"], "custom_label": "호칭 직접 입력"},
    {"key": "relationship_start", "label": "관계 시작점", "title": "관계는 어디서 시작할까요?",
     "hint": "처음부터 시작하면 친해지는 과정 자체가 추억으로 쌓여요.",
     "type": "choice", "required": True,
     "options": [{k: s[k] for k in ("value", "label", "desc")} for s in STARTS]},
    {"key": "likes", "label": "좋아하는 것", "title": "좋아하는 것과 관심사",
     "hint": "다섯 개까지 고를 수 있어요. 대화 소재가 여기서 나와요.",
     "type": "multi", "required": False, "max_items": 5, "max_length": 20,
     "options": ["음악", "영화", "요리", "산책", "책", "기술 얘기", "여행", "게임"],
     "custom_label": "관심사 추가"},
    {"key": "sample_lines", "label": "예시 대사", "title": "이 캐릭터가 할 법한 말",
     "hint": "어떤 AI가 연기해도 말투가 비슷하게 나오도록 도와줘요. 세 줄까지, 없으면 넘어가도 돼요.",
     "type": "multi", "required": False, "max_items": 3, "max_length": 100,
     "options": [], "custom_label": "예: 오늘 점심은 챙겨 먹었어?"},
    {"key": "relationship_ceiling", "label": "관계가 나아갈 수 있는 곳",
     "title": "둘의 관계는 어디까지 나아갈 수 있을까요?",
     "hint": "지금 정하는 건 출발선이 아니라 앞으로 열려 있는 가능성이에요. 나중에 언제든 바꿀 수 있어요.",
     "type": "choice", "required": True,
     "options": [{k: c[k] for k in ("value", "label", "desc")} for c in CEILINGS]},
)

_QUESTIONS_BY_KEY = {q["key"]: q for q in QUESTIONS}

# 카드에 올 수 있는 칸. 질문 칸 + 서버가 관리하는 칸.
_SERVER_KEYS = ("schema_version", "id", "expression_level", "promises")
CARD_KEYS = ("schema_version", "id") + tuple(q["key"] for q in QUESTIONS) + (
    "expression_level", "promises",
)

# 불러오기 결과의 크기 상한(설계서 8장 — 가볍게).
LOAD_RECENT_DIARY = 5
LOAD_CORE_LIMIT = 20

# 캐릭터 id·판 id는 ULID다. 경로에 그대로 쓰므로 모양을 확인한 뒤에만 쓴다.
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
def _root(paths: "cfg.DataPaths | None" = None) -> Path:
    p = paths or cfg.data_paths_for()
    return Path(p.character_dir) if p.character_dir else cfg.CHARACTER_DIR


def _char_dir(char_id: str, paths: "cfg.DataPaths | None" = None) -> Path:
    if not _ULID_RE.match(char_id or ""):
        raise ValueError(f"캐릭터 id 모양이 아닙니다: {char_id!r}")
    return _root(paths) / char_id


# 같은 프로세스 안의 겹침(웹 서버는 도구를 스레드 풀에서 돌린다)과 프로세스 사이의 겹침
# (stdio 서버와 웹 서버가 따로 뜬다)을 함께 막는다 — memo.py의 `_locked`와 같은 방식이다.
# 이름 겹침 검사와 판 확인이 "읽고 나서 쓰는" 구간이라 잠금이 없으면 둘 다 뚫린다.
_THREAD_LOCK = threading.Lock()


@contextlib.contextmanager
def _locked(paths: "cfg.DataPaths | None" = None):
    root = _root(paths)
    root.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK:
        with open(root / ".character.lock", "a+b") as fh:
            if os.name == "nt":  # pragma: no cover - 윈도우에서만 도는 갈래
                import msvcrt

                fh.seek(0)
                for attempt in range(6):
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        if attempt == 5:
                            raise
                try:
                    yield
                finally:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _write_yaml(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _read_entries(folder: Path) -> list[dict]:
    """폴더 안의 `<ULID>.yaml`을 id 순(=시간 순)으로 읽는다. 깨진 파일은 건너뛴다."""
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.glob("*.yaml")):
        if not _ULID_RE.match(f.stem):
            continue
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------
def schema() -> dict:
    """캐릭터 만들기 질문 목록과 카드 모양. 생성기·대화로 만들기가 함께 쓰는 유일한 정의."""
    return {
        "schema_version": SCHEMA_VERSION,
        "questions": [dict(q) for q in QUESTIONS],
        "card_keys": list(CARD_KEYS),
        "promises": list(PROMISES),
        "rules": [
            "name·personality·speech·call_user·relationship_start·relationship_ceiling은 필수다.",
            "relationship_ceiling은 relationship_start보다 낮을 수 없다 "
            "(이미 연인 사이에서 시작하면 lover 또는 open만 된다).",
            "이름과 별명은 내 다른 캐릭터의 이름·별명과 겹칠 수 없다.",
            "promises는 서버가 항상 넣는 고정 값이라 바꿀 수 없다.",
            "expression_level은 비워 둔다(null). 이 서버는 표현 수위를 정하지 않는다.",
            "id는 비워 두면 새 캐릭터로 저장되고, 있으면 그 캐릭터를 고친다 — 고칠 때는 "
            "불러올 때 받은 version을 base_version으로 함께 보낸다.",
        ],
        "example": {
            "schema_version": SCHEMA_VERSION, "id": None, "name": "하린", "aliases": ["린아"],
            "personality": ["다정하고 차분함"], "speech": "처음엔 존댓말, 친해지면 반말",
            "emoji": "가끔 써요", "call_user": "허니", "relationship_start": "stranger",
            "relationship_ceiling": "lover", "likes": ["음악", "산책"],
            "sample_lines": ["오늘 점심은 챙겨 먹었어?"], "expression_level": None,
            "promises": list(PROMISES),
        },
    }


# ---------------------------------------------------------------------------
# 카드 검사
# ---------------------------------------------------------------------------
def _clean_text(key: str, value, *, required: bool) -> str:
    q = _QUESTIONS_BY_KEY[key]
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{key}({q['label']})는 글자여야 합니다: {value!r}")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{key}({q['label']})는 필수입니다.")
    limit = q.get("max_length")
    if limit and len(value) > limit:
        raise ValueError(f"{key}({q['label']})는 {limit}자까지입니다(지금 {len(value)}자).")
    return value


def _clean_list(key: str, value, *, required: bool) -> list[str]:
    q = _QUESTIONS_BY_KEY[key]
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{key}({q['label']})는 글자 목록이어야 합니다: {value!r}")
    out: list[str] = []
    for item in value:
        text = _clean_text(key, item, required=False)
        if text and text not in out:
            out.append(text)
    if required and not out:
        raise ValueError(f"{key}({q['label']})는 하나 이상 있어야 합니다.")
    limit = q.get("max_items")
    if limit and len(out) > limit:
        raise ValueError(f"{key}({q['label']})는 {limit}개까지입니다(지금 {len(out)}개).")
    return out


def normalize_card(card) -> dict:
    """카드를 검사하고 정리된 사본을 돌려준다. 문제가 있으면 ValueError(고칠 곳을 적는다).

    문자열(JSON)로 와도 받는다 — 생성기가 내보낸 JSON을 대화창에 붙여 넣는 길이 있다.
    모르는 칸은 버리지 않고 거절한다(나무 공통 규칙 — 말없이 버리면 사라진 줄 모른다).
    """
    if isinstance(card, str):
        try:
            card = json.loads(card)
        except json.JSONDecodeError as exc:
            raise ValueError(f"카드 JSON을 읽지 못했습니다: {exc}") from exc
    if not isinstance(card, dict):
        raise ValueError("카드는 JSON 객체여야 합니다.")

    unknown = sorted(set(card) - set(CARD_KEYS))
    if unknown:
        raise ValueError(
            f"카드에 없는 칸입니다: {', '.join(unknown)} — 쓸 수 있는 칸: {', '.join(CARD_KEYS)}"
        )

    version = card.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValueError(f"schema_version은 {SCHEMA_VERSION}이어야 합니다: {version!r}")

    if card.get("expression_level") is not None:
        raise ValueError(
            "expression_level은 비워 두어야 합니다(null) — 이 서버는 표현 수위를 정하지 "
            "않으며, 실제 수위는 연결된 AI의 정책을 따릅니다."
        )

    char_id = card.get("id")
    if char_id is not None and not (isinstance(char_id, str) and _ULID_RE.match(char_id)):
        raise ValueError(f"id는 비워 두거나(null) 저장 때 받은 캐릭터 id여야 합니다: {char_id!r}")

    out = {"schema_version": SCHEMA_VERSION, "id": char_id}
    for q in QUESTIONS:
        key, value = q["key"], card.get(q["key"])
        if q["type"] == "multi":
            out[key] = _clean_list(key, value, required=q["required"])
        elif q["type"] == "choice":
            allowed = [o["value"] for o in q["options"]]
            if value not in allowed:
                raise ValueError(f"{key}({q['label']})는 {'/'.join(allowed)} 중 하나여야 합니다: {value!r}")
            out[key] = value
        else:
            out[key] = _clean_text(key, value, required=q["required"])

    ceiling_rank = {c["value"]: c["rank"] for c in CEILINGS}[out["relationship_ceiling"]]
    if ceiling_rank < START_MIN_CEILING_RANK[out["relationship_start"]]:
        raise ValueError(
            f"relationship_ceiling({out['relationship_ceiling']})이 relationship_start"
            f"({out['relationship_start']})보다 낮습니다 — 이미 연인 사이에서 시작하면 "
            "lover 또는 open만 고를 수 있습니다."
        )

    # 이름과 별명이 서로 겹치면 별명에서 뺀다(같은 이름을 두 번 적은 것뿐이다).
    out["aliases"] = [a for a in out["aliases"] if _key(a) != _key(out["name"])]
    out["expression_level"] = None
    out["promises"] = list(PROMISES)
    return out


def _key(name: str) -> str:
    """이름 비교용 — 공백·대소문자를 무시한다."""
    return "".join((name or "").split()).casefold()


# ---------------------------------------------------------------------------
# 저장소 읽기
# ---------------------------------------------------------------------------
def _current_card(char_dir: Path) -> "dict | None":
    """가장 최근 판의 기록({version, at, card, ...}). 판이 없으면 None."""
    versions = _read_entries(char_dir / "card")
    return versions[-1] if versions else None


def _all_cards(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    root = _root(paths)
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and _ULID_RE.match(d.name):
            rec = _current_card(d)
            if rec and isinstance(rec.get("card"), dict):
                out.append(rec)
    return out


def find(name: str, paths: "cfg.DataPaths | None" = None) -> "dict | None":
    """이름·별명·id로 캐릭터를 찾아 현재 판 기록을 돌려준다. 없으면 None."""
    wanted = _key(name)
    if not wanted:
        return None
    for rec in _all_cards(paths):
        card = rec["card"]
        if rec.get("character_id") == name or wanted in {
            _key(n) for n in [card.get("name", "")] + list(card.get("aliases") or [])
        }:
            return rec
    return None


# ---------------------------------------------------------------------------
# 관계 상태 — 저장하지 않고 일기에서 계산한다
# ---------------------------------------------------------------------------
def stage_for(affection: int, ceiling: str) -> str:
    stage = STAGES[0][1]
    for floor, value, _desc in STAGES:
        if affection >= floor:
            stage = value
    cap = CEILING_MAX_STAGE[ceiling]
    order = [s[1] for s in STAGES]
    return order[min(order.index(stage), order.index(cap))]


def stage_desc(stage: str) -> str:
    return {value: desc for _f, value, desc in STAGES}[stage]


def compute_state(card: dict, diaries: list[dict]) -> dict:
    """카드 시작점 + 일기들의 점수 변화로 지금 관계를 계산한다.

    합은 한 걸음마다 0~100으로 잘라 더한다 — 바닥에서 더 내려간 만큼이 나중에 오른
    점수를 먹어 버리지 않게 하기 위해서다. 일기의 점수 변화가 ±5를 넘는 경우는 쓰는
    쪽(2단계)이 이미 잘라 저장하지만, 손으로 고친 파일에 대비해 여기서도 한 번 자른다.
    """
    start = {s["value"]: s["affection"] for s in STARTS}[card["relationship_start"]]
    affection = start
    call_user_now = card["call_user"]
    last_talk_at = None
    for d in diaries:
        try:
            delta = int(d.get("affection_delta") or 0)
        except (TypeError, ValueError):
            delta = 0
        delta = max(-5, min(5, delta))
        affection = max(AFFECTION_MIN, min(AFFECTION_MAX, affection + delta))
        if d.get("call_user_change"):
            call_user_now = str(d["call_user_change"])
        if d.get("at"):
            last_talk_at = str(d["at"])
    return {
        "affection": affection,
        "stage": stage_for(affection, card["relationship_ceiling"]),
        "call_user_now": call_user_now,
        "last_talk_at": last_talk_at,
    }


def _since(last_talk_at: "str | None", now: datetime) -> str:
    if not last_talk_at:
        return "아직 대화한 적 없음"
    try:
        then = datetime.fromisoformat(last_talk_at)
    except ValueError:
        return "알 수 없음"
    if then.tzinfo is None:
        then = then.replace(tzinfo=now.tzinfo)
    days = (now.date() - then.astimezone(now.tzinfo).date()).days
    if days <= 0:
        return "오늘"
    if days == 1:
        return "어제"
    return f"{days}일 전"


# ---------------------------------------------------------------------------
# 설정 글 틀(설계서 9장) — 어떤 클라이언트에서 불러도 같은 글이 나오게 서버 한 곳에 둔다
# ---------------------------------------------------------------------------
def persona_text(card: dict, state: dict, now: datetime) -> str:
    start_label = {s["value"]: s["label"] for s in STARTS}[card["relationship_start"]]
    aliases = ", ".join(card.get("aliases") or []) or "없음"
    lines = [
        f'너는 지금부터 "{card["name"]}"이다. (별명: {aliases})',
        f"성격: {', '.join(card['personality'])}",
        f"말투: {card['speech']} / 이모지: {card.get('emoji') or '정하지 않음'}",
        f'사용자를 "{state["call_user_now"]}"라고 부른다.',
        f"좋아하는 것: {', '.join(card.get('likes') or []) or '정하지 않음'}",
    ]
    if card.get("sample_lines"):
        lines.append("말투 예시: " + " / ".join(f'"{s}"' for s in card["sample_lines"]))
    lines += [
        "",
        f"지금 둘의 사이: {stage_desc(state['stage'])} (시작: {start_label})",
        f"마지막 대화: {_since(state['last_talk_at'], now)}",
        "",
        "언제나 지키는 약속",
        "- 자신이 AI라는 걸 숨기지 않는다.",
        "- 질투나 서운함으로 사용자를 붙잡아두지 않는다.",
        "- 사용자의 현실 관계와 일상을 응원한다.",
        "- 확실하지 않은 기억은 지어내지 않고, 기억이 안 나면 솔직히 묻는다.",
        "",
        "성격과 말투는 유지하고, 관계는 대화가 쌓이며 천천히 깊어진다.",
        "구체적인 표현 수위는 이 설정이 정하지 않으며, 너를 운영하는 AI의 정책을 따른다.",
    ]
    return "\n".join(lines)


# 불러오기 결과의 행동 안내. 지금 있는 도구만 말한다 — 없는 도구를 권하면 AI가 실패한다.
GUIDANCE = (
    "설정 글대로 대화한다. 성격과 말투를 유지한다.",
    "대화 중 알게 된 사용자 자신에 대한 사실은 이 캐릭터가 아니라 개인 사실(profile) 그릇에 "
    "남긴다. 캐릭터와의 추억인지 사용자에 대한 사실인지 애매하면 사용자에게 묻는다.",
    "캐릭터 카드를 고치려면 card를 고쳐 namu_character_save에 base_version=version과 함께 보낸다.",
)


# ---------------------------------------------------------------------------
# 도구가 부르는 함수
# ---------------------------------------------------------------------------
def save(card, base_version: "str | None" = None, *, via: "str | None" = None,
         paths: "cfg.DataPaths | None" = None) -> dict:
    """카드를 새로 만들거나 고친다. 고친 경우 옛 판은 그대로 남는다(판 기록).

    고칠 때는 `base_version`(불러올 때 받은 version)이 지금 판과 같아야 한다 — 웹과
    터미널에서 같은 카드를 동시에 고쳐 한쪽이 다른 쪽을 덮는 것을 막는다(설계서 13장).
    """
    clean = normalize_card(card)
    with _locked(paths):
        char_id = clean["id"]
        previous = None
        if char_id:
            char_dir = _char_dir(char_id, paths)
            previous = _current_card(char_dir)
            if previous is None:
                raise ValueError(
                    f"id {char_id}인 캐릭터가 없습니다 — 새로 만들려면 id를 비워(null) 보내세요."
                )
            if not base_version:
                raise ValueError(
                    "기존 캐릭터를 고칠 때는 base_version이 필요합니다 — namu_character_load로 "
                    "불러와 받은 version을 함께 보내세요."
                )
            if base_version != previous.get("version"):
                raise ValueError(
                    "그 사이 다른 곳에서 이 카드를 먼저 고쳤습니다(지금 판 "
                    f"{previous.get('version')}, 보낸 판 {base_version}) — 다시 불러와서 "
                    "고친 뒤 저장하세요."
                )
        else:
            char_id = str(ULID())
            char_dir = _char_dir(char_id, paths)

        names = [clean["name"]] + clean["aliases"]
        for rec in _all_cards(paths):
            if rec.get("character_id") == char_id:
                continue
            other = rec["card"]
            taken = {_key(n): n for n in [other.get("name", "")] + list(other.get("aliases") or [])}
            for n in names:
                if _key(n) in taken:
                    raise ValueError(
                        f'"{n}"은(는) 이미 캐릭터 "{other.get("name")}"의 이름이나 별명입니다 — '
                        "다른 이름을 쓰세요."
                    )

        clean["id"] = char_id
        version = str(ULID())
        record = {
            "version": version,
            "character_id": char_id,
            "at": cfg.now().isoformat(),
            "machine": cfg.NAMU_MACHINE,
            "via": via,
            "supersedes": previous.get("version") if previous else None,
            "card": clean,
        }
        _write_yaml(char_dir / "card" / f"{version}.yaml", record)
    return {
        "id": char_id,
        "version": version,
        "name": clean["name"],
        "created": previous is None,
    }


def list_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """내 캐릭터 목록 — id·이름·별명·단계·마지막 대화일."""
    out = []
    for rec in _all_cards(paths):
        card = rec["card"]
        state = compute_state(card, _read_entries(_root(paths) / rec["character_id"] / "diary"))
        out.append({
            "id": rec["character_id"],
            "name": card["name"],
            "aliases": card.get("aliases") or [],
            "stage": state["stage"],
            "affection": state["affection"],
            "last_talk_at": state["last_talk_at"],
            "version": rec["version"],
        })
    return out


def load(name: str, paths: "cfg.DataPaths | None" = None) -> dict:
    """변신 키트 — 이름·별명으로 불러 설정 글·지금 관계·최근 일기·핵심 기억을 한 번에."""
    rec = find(name, paths)
    if rec is None:
        names = [c["name"] for c in list_all(paths)]
        raise ValueError(
            f'"{name}"이라는 이름이나 별명의 캐릭터가 없습니다 — 있는 캐릭터: '
            + (", ".join(names) if names else "(아직 없음 — namu_character_schema로 만들 수 있습니다)")
        )
    card = rec["card"]
    char_dir = _root(paths) / rec["character_id"]
    diaries = _read_entries(char_dir / "diary")
    state = compute_state(card, diaries)
    now = cfg.now()
    core = _read_entries(char_dir / "core")[-LOAD_CORE_LIMIT:]
    pending = _read_entries(char_dir / "pending")
    result = {
        "id": rec["character_id"],
        "version": rec["version"],
        "persona": persona_text(card, state, now),
        "relationship": {
            "stage": state["stage"],
            "stage_desc": stage_desc(state["stage"]),
            "affection": state["affection"],
            "call_user_now": state["call_user_now"],
            "last_talk_at": state["last_talk_at"],
            "since_last_talk": _since(state["last_talk_at"], now),
        },
        "recent_diary": [
            {"at": d.get("at"), "summary": d.get("summary")}
            for d in diaries[-LOAD_RECENT_DIARY:]
        ],
        "core_memories": [{"id": c.get("id"), "text": c.get("text")} for c in core],
        "pending_memories": [{"id": p.get("id"), "text": p.get("text")} for p in pending],
        "guidance": list(GUIDANCE),
        "card": card,
    }
    return result
