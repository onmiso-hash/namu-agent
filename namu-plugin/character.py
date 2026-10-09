"""캐릭터 그릇 — 이름을 부르면 같은 성격과 기억으로 나타나는 캐릭터(설계서: 나무 캐릭터 v0.1).

## 왜 다른 그릇과 모양이 다른가

다른 그릇은 "파일 하나에 문서를 덧붙이는" 모양이다. 캐릭터는 그렇게 두지 않고
**항목 하나를 파일 하나로** 둔다.

    memory/character/<캐릭터 id>/card/<판 id>.yaml     카드(고칠 때마다 새 판)
    memory/character/<캐릭터 id>/diary/<id>.yaml       일기(2단계)
    memory/character/<캐릭터 id>/core/<id>.yaml        확정된 핵심 기억(2단계)
    memory/character/<캐릭터 id>/pending/<id>.yaml     확인 대기 후보(2단계)
    memory/character/<캐릭터 id>/archive/<id>.yaml     대화 원문(3단계, 사용자가 요청한 것만)

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
import hashlib
import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

import yaml
from ulid import ULID

import attachments
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
    # 사용자가 캐릭터마다 정하는 규칙. 고정 약속(PROMISES)과 달리 바꿀 수 있고, 설정 글의
    # 고정 약속 아래에 실린다 — 어긋나면 고정 약속이 우선이다(설정 글에 그렇게 적는다).
    {"key": "custom_rules", "label": "지키는 규칙", "title": "이 캐릭터가 늘 지킬 규칙",
     "hint": "대화할 때마다 꼭 지킬 것을 적어요. 다섯 줄까지, 없으면 넘어가도 돼요.",
     "type": "multi", "required": False, "max_items": 5, "max_length": 100,
     "options": [], "custom_label": "예: 내가 힘들다고 하면 먼저 쉬자고 말해 줘"},
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
    "portrait", "emotion_photos", "expression_level", "promises",
)

# 불러오기 결과의 크기 상한(설계서 0·8장 — 가볍게). 2026-10-08: 모든 칸을 채운 최악값이
# 13,272자로 목표(약 3천 토큰)를 넘어 실측 후 다시 정했다(5→3, 20→10). 대기 후보는 서버가
# 이미 합계 10개(PENDING_MAX)로 막고 있어 따로 줄이지 않았다.
LOAD_RECENT_DIARY = 3
LOAD_CORE_LIMIT = 10

# 일기 한 편의 상한(설계서 5.3·6장 초안 값). 점수 변화 폭은 compute_state도 같은 값으로 자른다.
DELTA_LIMIT = 5
DIARY_SUMMARY_MAX = 500
DIARY_MOOD_MAX = 20
DIARY_REASON_MAX = 100
DIARY_TOPICS_MAX = 5
DIARY_TOPIC_MAX = 20

# 핵심 기억 후보(설계서 5.4). 일기 한 편에 몇 개까지, 확인 대기로 몇 개까지 쌓이게 둘지.
# 대기 후보는 불러올 때마다 전부 실리므로, 상한이 없으면 불러오기가 한없이 무거워진다.
CORE_TEXT_MAX = 200
CORE_CANDIDATES_PER_DIARY = 3
PENDING_MAX = 10
CORE_ACTIONS = ("list", "confirm", "reject")
# 화면용 글(display)에 싣는 양. 원래 기록 칸은 따로 다 실리므로, 화면용 글은 줄여 실어
# 불러오기 크기가 두 배로 늘지 않게 한다.
DISPLAY_SUMMARY_CHARS = 120
DISPLAY_CORE_ITEMS = 5
DISPLAY_CORE_CHARS = 60
# 원문 보관(설계서 5.5) — 대화 한 번의 원문은 길 수 있지만 끝이 없으면 저장소가 무거워진다.
# 상한은 조각 하나의 크기다. 긴 대화는 일기 하나에 조각을 이어 붙여(append_to) 남긴다.
ARCHIVE_TEXT_MAX = 50000
ARCHIVE_PARTS_MAX = 20
# 대표사진·감정별 사진(설계서 확장). 카드에는 사진 몸통이 아니라 첨부 그릇에 올린 파일의
# 저장소 안 경로(문자열)만 참조로 담는다 — attachments.current_files()가 돌려주는 'path'다.
PHOTO_PATH_MAX = 300
PHOTO_EMOTION_LABEL_MAX = 20
PHOTO_EMOTION_MAX = 12
# 잊기(설계서 8·12장). pending은 core(action=reject)가 이미 지우므로 대상에 넣지 않는다 —
# 일기를 잊을 때 딸린 후보로만 함께 지워진다.
FORGET_TARGETS = ("diary", "core", "archive", "character")
FORGET_LIST_MAX = 20
FORGET_PREVIEW_CHARS = 80

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
            "custom_rules는 선택이며 설정 글의 고정 약속 아래에 실린다. 고정 약속과 어긋나면 "
            "고정 약속이 우선이다.",
            "portrait·emotion_photos는 선택이며, 먼저 namu_upload_file로 올린 파일의 경로만 "
            "쓸 수 있다.",
        ],
        "example": {
            "schema_version": SCHEMA_VERSION, "id": None, "name": "하린", "aliases": ["린아"],
            "personality": ["다정하고 차분함"], "speech": "처음엔 존댓말, 친해지면 반말",
            "emoji": "가끔 써요", "call_user": "허니", "relationship_start": "stranger",
            "relationship_ceiling": "lover", "likes": ["음악", "산책"],
            "sample_lines": ["오늘 점심은 챙겨 먹었어?"],
            "custom_rules": ["내가 힘들다고 하면 먼저 쉬자고 말해 줘"],
            "portrait": None, "emotion_photos": {},
            "expression_level": None,
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


def _check_photo_path(field: str, path) -> str:
    """portrait·emotion_photos의 값(경로) 하나를 모양만 검사한다 — 첨부 그릇에 실제로
    있는지는 호출하는 쪽이 `_live_attachment_paths`로 한 번에 확인한다."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"{field}는 비워 두거나(null) 첨부 파일 경로여야 합니다: {path!r}")
    path = path.strip()
    if len(path) > PHOTO_PATH_MAX:
        raise ValueError(f"{field}는 {PHOTO_PATH_MAX}자까지입니다(지금 {len(path)}자).")
    return path


def _live_attachment_paths(paths: "cfg.DataPaths | None") -> set[str]:
    return {e.get("path") for e in attachments.current_files(paths) if e.get("path")}


def _check_photo_exists(field: str, path: str, live: set[str]) -> None:
    if path not in live:
        raise ValueError(
            f"{field}: 그런 첨부 파일이 없습니다: {path!r} — 먼저 namu_upload_file로 올리고 "
            "그 경로를 쓰세요."
        )


def normalize_card(card, paths: "cfg.DataPaths | None" = None) -> dict:
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

    # 대표사진·감정별 사진 — 카드에는 첨부 그릇에 올린 파일의 경로(문자열)만 참조로 담는다.
    portrait = card.get("portrait")
    emotion_photos = card.get("emotion_photos")
    needed: set[str] = set()
    if portrait is not None:
        portrait = _check_photo_path("portrait", portrait)
        needed.add(portrait)
    cleaned_emotions: dict[str, str] = {}
    if emotion_photos is not None:
        if not isinstance(emotion_photos, dict):
            raise ValueError(f"emotion_photos는 객체(감정 이름→경로)여야 합니다: {emotion_photos!r}")
        if len(emotion_photos) > PHOTO_EMOTION_MAX:
            raise ValueError(
                f"emotion_photos는 {PHOTO_EMOTION_MAX}개까지입니다(지금 {len(emotion_photos)}개)."
            )
        seen_labels: set[str] = set()
        for raw_label, raw_path in emotion_photos.items():
            label = " ".join(str(raw_label or "").split())
            if not label:
                raise ValueError(f"emotion_photos의 감정 이름이 비어 있습니다: {raw_label!r}")
            # 공백·대소문자만 다른 이름은 같은 감정이다 — 덮어써 말없이 버리지 않고 거절한다.
            if _key(label) in seen_labels:
                raise ValueError(
                    f"emotion_photos의 감정 이름 '{label}'이 겹칩니다(공백·대소문자를 정리하면 "
                    "같은 이름) — 하나만 쓰세요."
                )
            seen_labels.add(_key(label))
            if len(label) > PHOTO_EMOTION_LABEL_MAX:
                raise ValueError(
                    f"emotion_photos의 감정 이름({label})은 {PHOTO_EMOTION_LABEL_MAX}자까지입니다"
                    f"(지금 {len(label)}자)."
                )
            path = _check_photo_path(f"emotion_photos[{label}]", raw_path)
            cleaned_emotions[label] = path
            needed.add(path)
    if needed:
        live = _live_attachment_paths(paths)
        if portrait is not None:
            _check_photo_exists("portrait", portrait, live)
        for label, path in cleaned_emotions.items():
            _check_photo_exists(f"emotion_photos[{label}]", path, live)
    out["portrait"] = portrait
    out["emotion_photos"] = cleaned_emotions
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
    쪽(`write_diary`)이 이미 잘라 저장하지만, 손으로 고친 파일에 대비해 여기서도 한 번 자른다.

    마지막 단계 변화(`last_stage_change`)도 저장하지 않고 일기를 다시 훑어 찾는다 —
    일기를 잊으면(3단계) 그 일기가 만든 단계 변화도 함께 사라져야 하기 때문이다.
    """
    start = {s["value"]: s["affection"] for s in STARTS}[card["relationship_start"]]
    ceiling = card["relationship_ceiling"]
    affection = start
    stage = stage_for(affection, ceiling)
    call_user_now = card["call_user"]
    last_talk_at = None
    last_stage_change = None
    for d in diaries:
        try:
            delta = int(d.get("affection_delta") or 0)
        except (TypeError, ValueError):
            delta = 0
        delta = max(-DELTA_LIMIT, min(DELTA_LIMIT, delta))
        affection = max(AFFECTION_MIN, min(AFFECTION_MAX, affection + delta))
        new_stage = stage_for(affection, ceiling)
        if new_stage != stage:
            last_stage_change = {"from": stage, "to": new_stage, "at": d.get("at")}
            stage = new_stage
        if d.get("call_user_change"):
            call_user_now = str(d["call_user_change"])
        if d.get("at"):
            last_talk_at = str(d["at"])
    return {
        "affection": affection,
        "stage": stage,
        "call_user_now": call_user_now,
        "last_talk_at": last_talk_at,
        "last_stage_change": last_stage_change,
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


_WEEKDAYS = "월화수목금토일"


def _clock(t: datetime) -> str:
    h = t.hour
    if h < 5:
        part = "새벽"
    elif h < 9:
        part = "아침"
    elif h < 12:
        part = "오전"
    elif h < 13:
        part = "낮"
    elif h < 18:
        part = "오후"
    elif h < 21:
        part = "저녁"
    else:
        part = "밤"
    text = f"{part} {h % 12 or 12}시"
    return f"{text} {t.minute}분" if t.minute else text


def _when(at: "str | None", now: datetime) -> "str | None":
    """사람이 읽는 시각 — "10월 8일(수) 저녁 7시 57분 · 3일 전". 해가 다르면 연도를 붙인다.

    AI가 ISO 시각을 저마다 다르게 풀어 쓰지 않도록 서버가 한 가지 모양으로 만들어 준다.
    """
    if not at:
        return None
    try:
        then = datetime.fromisoformat(at)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=now.tzinfo)
    t = then.astimezone(now.tzinfo)
    date = f"{t.month}월 {t.day}일({_WEEKDAYS[t.weekday()]})"
    if t.year != now.year:
        date = f"{t.year}년 {date}"
    return f"{date} {_clock(t)} · {_since(at, now)}"


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
    ]
    if card.get("custom_rules"):
        lines += ["", "이 캐릭터가 따로 지키는 규칙 (위 약속과 어긋나면 위 약속을 따른다)"]
        lines += [f"- {r}" for r in card["custom_rules"]]
    lines += [
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
    "사용자가 대화를 마무리하는 신호를 주면 namu_character_diary로 일기를 한 편 남긴다 — "
    "캐릭터 시점의 짧은 요약, 호감도 변화(-5~+5)와 그 이유. 오래 간직할 만한 순간은 "
    "core_candidates로 함께 보낸다(후보일 뿐 바로 핵심 기억이 되지 않는다).",
    "pending_memories가 있으면 대화 흐름에 맞춰 자연스럽게 \"이거 오래 기억해도 될까?\" 하고 "
    "사용자에게 묻는다. 사용자가 좋다고 한 것만 namu_character_core(action=confirm)로 "
    "확정하고, 싫다고 한 것은 action=reject로 지운다. 묻지 않고 확정하지 않는다.",
    "불러온 뒤 display를 고치거나 줄이지 말고 그대로 먼저 보여 준 다음, 설정 글대로 말을 건넨다. "
    "날짜를 말할 때는 at이 아니라 when의 표현을 쓴다.",
    "사용자가 \"이 대화 통째로 남겨줘\"처럼 원문 보관을 부탁했을 때만 일기에 archive(대화 원문)를 "
    "함께 보낸다. 부탁받지 않은 원문은 보내지 않는다. 대화 한 번에 일기는 한 편이다 — 원문이 "
    f"{ARCHIVE_TEXT_MAX}자를 넘으면 나눠서, 첫 조각은 일기와 함께 보내고 나머지는 "
    "append_to=<그 일기 id>와 archive만 넣어 차례로 보낸다(일기를 새로 쓰지 않는다).",
    "사용자가 \"잊어줘\"라고 하면 namu_character_forget으로 지운다 — 먼저 미리 보기를 받아 함께 "
    "지워질 것과 notice(GitHub 이력에 남는 한계)를 보여 주고, 사용자가 좋다고 한 뒤에만 confirm을 "
    "넣어 다시 부른다.",
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
    clean = normalize_card(card, paths)
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


def _require(name: str, paths: "cfg.DataPaths | None" = None) -> dict:
    """find와 같되, 없으면 있는 캐릭터 이름을 적어 거절한다."""
    rec = find(name, paths)
    if rec is None:
        names = [c["name"] for c in list_all(paths)]
        raise ValueError(
            f'"{name}"이라는 이름이나 별명의 캐릭터가 없습니다 — 있는 캐릭터: '
            + (", ".join(names) if names else "(아직 없음 — namu_character_schema로 만들 수 있습니다)")
        )
    return rec


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
            "last_talk_when": _when(state["last_talk_at"], cfg.now()),
            "version": rec["version"],
        })
    return out


def _archive_parts(char_dir: Path) -> dict[str, list[dict]]:
    """일기 id → 그 일기의 원문 조각(번호순). 원문이 있는지는 일기에 적지 않고 여기서 센다 —
    조각을 나중에 이어 붙이거나 하나만 잊어도 일기 파일을 고쳐 쓸 일이 없게 하려고."""
    parts: dict[str, list[dict]] = {}
    for doc in _read_entries(char_dir / "archive"):
        parts.setdefault(doc.get("diary_id"), []).append(doc)
    for docs in parts.values():
        docs.sort(key=lambda d: (d.get("part") or 1, d.get("id") or ""))
    return parts


def _quote_line(text) -> str:
    """인용 상자 한 줄 — 줄바꿈과 마크다운 머리 기호가 상자를 깨지 않게 다듬는다."""
    return " ".join(str(text or "").split()).lstrip("#>")


def display_text(card: dict, state: dict, diaries: list[dict], core: list[dict],
                 pending_count: int, now: datetime) -> str:
    """화면에 그대로 보여 줄 마크다운 — 인용 상자(`>`) 한 덩어리.

    claude.ai와 Claude Code가 모두 그려 주는 모양 가운데 한글 폭에 흔들리지 않는 것을
    골랐다(선으로 그린 상자는 한글 폭 때문에 오른쪽 선이 어긋난다). AI가 데이터를 받아
    저마다 꾸미면 매번 모양이 달라지므로 서버가 완성된 글을 만든다.
    """
    lines = [
        f"> **🌸 {_quote_line(card['name'])}** · {stage_desc(state['stage'])} · "
        f"호감도 {state['affection']}/{AFFECTION_MAX}",
        f"> 마지막 대화: {_when(state['last_talk_at'], now) or '아직 대화한 적 없음'}",
    ]
    if diaries:
        lines += [">", "> **📔 최근 일기**"]
        for d in reversed(diaries):
            mood = f" ({_quote_line(d.get('mood'))})" if d.get("mood") else ""
            lines.append(f"> - **{_when(d.get('at'), now) or '때를 알 수 없음'}**{mood}  ")
            lines.append(f">   {_quote_line(_short(d.get('summary'), DISPLAY_SUMMARY_CHARS))}")
    if core:
        lines += [">", "> **💝 간직한 기억**"]
        shown = core[-DISPLAY_CORE_ITEMS:]
        lines += [f"> - {_quote_line(_short(c.get('text'), DISPLAY_CORE_CHARS))}"
                  for c in reversed(shown)]
        if len(core) > len(shown):
            lines.append(f"> - 외 {len(core) - len(shown)}개")
    if card.get("custom_rules"):
        lines += [">", f"> 📜 이 캐릭터가 지키는 규칙 {len(card['custom_rules'])}개"]
    if pending_count:
        lines += [">", f"> 💭 간직할지 묻기를 기다리는 기억 {pending_count}개"]
    return "\n".join(lines)


def load(name: str, paths: "cfg.DataPaths | None" = None) -> dict:
    """변신 키트 — 이름·별명으로 불러 설정 글·지금 관계·최근 일기·핵심 기억을 한 번에."""
    rec = _require(name, paths)
    # custom_rules가 생기기 전에 저장한 카드에는 이 칸이 없다 — 빈 목록으로 채워 돌려준다.
    card = {**rec["card"], "custom_rules": rec["card"].get("custom_rules") or []}
    char_dir = _root(paths) / rec["character_id"]
    diaries = _read_entries(char_dir / "diary")
    state = compute_state(card, diaries)
    now = cfg.now()
    core = _read_entries(char_dir / "core")[-LOAD_CORE_LIMIT:]
    pending = _read_entries(char_dir / "pending")
    recent = diaries[-LOAD_RECENT_DIARY:]
    parts = _archive_parts(char_dir)
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
            "last_talk_when": _when(state["last_talk_at"], now),
            "since_last_talk": _since(state["last_talk_at"], now),
            "last_stage_change": state["last_stage_change"],
        },
        "recent_diary": [
            {"id": d.get("id"), "at": d.get("at"), "when": _when(d.get("at"), now),
             "summary": d.get("summary"), "mood": d.get("mood"),
             "archive_parts": len(parts.get(d.get("id"), []))}
            for d in recent
        ],
        "core_memories": [{"id": c.get("id"), "text": c.get("text")} for c in core],
        "pending_memories": [{"id": p.get("id"), "text": p.get("text")} for p in pending],
        "display": display_text(card, state, recent, core, len(pending), now),
        "guidance": list(GUIDANCE),
        "card": card,
    }
    return result


# ---------------------------------------------------------------------------
# 2단계 — 일기와 핵심 기억(설계서 5.3·5.4·6장)
# ---------------------------------------------------------------------------
def _text(field: str, value, limit: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field}는 글자여야 합니다: {value!r}")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{field}는 비워 둘 수 없습니다.")
    if len(value) > limit:
        raise ValueError(f"{field}는 {limit}자까지입니다(지금 {len(value)}자).")
    return value


def _texts(field: str, value, max_items: int, limit: int) -> list[str]:
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field}는 글자 목록이어야 합니다: {value!r}")
    out: list[str] = []
    for item in value:
        text = _text(field, item, limit)
        if text and text not in out:
            out.append(text)
    if len(out) > max_items:
        raise ValueError(f"{field}는 {max_items}개까지입니다(지금 {len(out)}개).")
    return out


def _delta(value) -> int:
    """호감도 변화는 정수만 받는다. 범위는 여기서 거절하지 않고 쓰는 쪽이 자른다."""
    if isinstance(value, bool):
        raise ValueError(f"affection_delta는 정수여야 합니다: {value!r}")
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d+\s*", value):
        return int(value)
    raise ValueError(f"affection_delta는 -{DELTA_LIMIT}~{DELTA_LIMIT} 사이의 정수여야 합니다: {value!r}")


def _brief(state: dict) -> dict:
    return {
        "affection": state["affection"],
        "stage": state["stage"],
        "stage_desc": stage_desc(state["stage"]),
        "call_user_now": state["call_user_now"],
    }


def _archive_text(archive) -> "str | None":
    if archive is not None and not isinstance(archive, str):
        raise ValueError(f"archive는 대화 원문(글자)이어야 합니다: {type(archive).__name__}")
    return archive if archive and archive.strip() else None


def _archive_too_long(archive: str) -> str:
    return (
        f"archive(대화 원문) 조각은 {ARCHIVE_TEXT_MAX}자까지입니다(지금 {len(archive)}자) — "
        f"{ARCHIVE_TEXT_MAX}자 이하로 나눠 append_to=<일기 id>와 archive만 넣어 차례로 보내세요."
    )


def _write_archive_part(char_dir: Path, char_id: str, diary_id: str, part: int, text: str,
                        via: "str | None") -> dict:
    archive_id = str(ULID())
    at = cfg.now().isoformat()
    _write_yaml(char_dir / "archive" / f"{archive_id}.yaml", {
        "id": archive_id,
        "character_id": char_id,
        "diary_id": diary_id,
        "part": part,
        "at": at,
        "machine": cfg.NAMU_MACHINE,
        "via": via,
        "text": text,
    })
    return {"id": archive_id, "part": part, "at": at, "chars": len(text)}


def _append_archive(name: str, diary_id, archive, *, via: "str | None",
                    paths: "cfg.DataPaths | None") -> dict:
    """이미 쓴 일기에 원문 조각 하나를 이어 붙인다. 일기·호감도·후보는 건드리지 않는다."""
    diary_id = str(diary_id).strip()
    if not _ULID_RE.match(diary_id):
        raise ValueError(f"append_to는 이어 붙일 일기의 id여야 합니다: {diary_id!r}")
    archive = _archive_text(archive)
    if not archive:
        raise ValueError("append_to를 쓸 때는 이어 붙일 원문 조각을 archive에 넣어 보내세요.")
    if len(archive) > ARCHIVE_TEXT_MAX:
        raise ValueError(_archive_too_long(archive) + " 이번 조각은 저장하지 않았습니다.")
    with _locked(paths):
        rec = _require(name, paths)
        card, char_id = rec["card"], rec["character_id"]
        char_dir = _char_dir(char_id, paths)
        if not (char_dir / "diary" / f"{diary_id}.yaml").is_file():
            raise ValueError(
                f'"{card["name"]}"에게 id {diary_id}인 일기가 없습니다 — 이어 붙일 일기는 '
                "namu_character_diary가 돌려준 id입니다."
            )
        have = _archive_parts(char_dir).get(diary_id, [])
        if len(have) >= ARCHIVE_PARTS_MAX:
            raise ValueError(
                f"일기 하나에 원문 조각은 {ARCHIVE_PARTS_MAX}개까지입니다 — 이번 조각은 저장하지 "
                "않았습니다."
            )
        part = max((d.get("part") or 1 for d in have), default=0) + 1
        saved = _write_archive_part(char_dir, char_id, diary_id, part, archive, via)
    return {
        "id": diary_id,
        "character": card["name"],
        "appended": True,
        "archive": saved,
        "archive_parts": len(have) + 1,
        "archive_chars": sum(len(d.get("text") or "") for d in have) + saved["chars"],
    }


def write_diary(name: str, summary: "str | None" = None, affection_delta=0,
                delta_reason: "str | None" = None, *,
                mood: "str | None" = None, call_user_change: "str | None" = None,
                topics=None, core_candidates=None, archive: "str | None" = None,
                append_to: "str | None" = None,
                via: "str | None" = None, paths: "cfg.DataPaths | None" = None) -> dict:
    """일기 한 편을 남긴다 — 대화 한 번(또는 사용자가 마무리 신호를 준 때)마다 하나.

    - 호감도 변화는 ±5로 자른다. 잘랐으면 원래 값을 `affection_delta_requested`로 함께
      남긴다(설계서 6장 — AI가 더 큰 값을 보낸 사실도 기록으로 남긴다).
    - 변화가 0이 아니면 이유가 필수다(설계서 5.3 — 점수 변화에는 반드시 이유를 붙인다).
    - 핵심 기억 후보는 `pending`에만 쓴다. core로 가는 길은 `core(action="confirm")` 하나뿐이고,
      그것도 대기 후보의 id로만 확정한다 — AI가 core에 직접 쓰는 길을 만들지 않는다(5.4).
    - 관계 상태는 쓰지 않는다. 쓰기 전후를 계산해 단계가 바뀌었으면 돌려줄 뿐이다.
    - `archive`는 사용자가 "이 대화 통째로 남겨줘"라고 했을 때만 AI가 넘기는 원문이다
      (설계서 5.5). 받은 그대로 저장한다 — 요약과 달리 줄바꿈도 다듬지 않는다. 원문이
      조각 상한을 넘어도 일기는 저장하고 원문만 돌려보낸다 — 대화가 있었다는 기록이 원문
      크기 때문에 사라지면 안 된다. 나머지는 `append_to`(일기 id)로 이어 붙인다. 조각마다
      번호(`part`)와 받은 시각이 붙고, 호감도는 일기 한 편으로만 센다.
    """
    if append_to is not None and str(append_to).strip():
        extra = [k for k, v in (("summary", summary), ("delta_reason", delta_reason),
                                ("mood", mood), ("call_user_change", call_user_change),
                                ("topics", topics), ("core_candidates", core_candidates)) if v]
        if _delta(affection_delta):
            extra.append("affection_delta")
        if extra:
            raise ValueError(
                f"append_to(원문 이어 붙이기)에는 archive만 보냅니다 — {', '.join(extra)}는 이미 "
                "쓴 일기에 들어 있으니 빼고 보내세요. 아무것도 저장하지 않았습니다."
            )
        return _append_archive(name, append_to, archive, via=via, paths=paths)

    summary = _text("summary", summary, DIARY_SUMMARY_MAX, required=True)
    requested = _delta(affection_delta)
    applied = max(-DELTA_LIMIT, min(DELTA_LIMIT, requested))
    reason = _text("delta_reason", delta_reason, DIARY_REASON_MAX)
    if requested != 0 and not reason:
        raise ValueError(
            f"affection_delta가 0이 아니면({requested}) delta_reason(점수가 바뀐 이유)이 필요합니다."
        )
    mood = _text("mood", mood, DIARY_MOOD_MAX) or None
    call_change = _text("call_user_change", call_user_change,
                        _QUESTIONS_BY_KEY["call_user"]["max_length"]) or None
    topics = _texts("topics", topics, DIARY_TOPICS_MAX, DIARY_TOPIC_MAX)
    candidates = _texts("core_candidates", core_candidates, CORE_CANDIDATES_PER_DIARY, CORE_TEXT_MAX)
    archive = _archive_text(archive)
    archive_rejected = None
    if archive and len(archive) > ARCHIVE_TEXT_MAX:
        archive_rejected = "일기는 저장했고 원문은 저장하지 않았습니다. " + _archive_too_long(archive)
        archive = None

    with _locked(paths):
        rec = _require(name, paths)
        card, char_id = rec["card"], rec["character_id"]
        char_dir = _char_dir(char_id, paths)
        diaries = _read_entries(char_dir / "diary")
        pending = _read_entries(char_dir / "pending")
        if candidates and len(pending) + len(candidates) > PENDING_MAX:
            raise ValueError(
                f"확인을 기다리는 핵심 기억 후보가 이미 {len(pending)}개라 후보 "
                f"{len(candidates)}개를 더하면 {PENDING_MAX}개를 넘습니다 — 일기는 저장하지 "
                "않았습니다. 사용자에게 먼저 확인받아 namu_character_core로 확정하거나 지운 뒤, "
                "다시 보내거나 core_candidates 없이 보내세요."
            )
        before = compute_state(card, diaries)
        now = cfg.now()
        at = now.isoformat()
        diary_id = str(ULID())
        entry = {
            "id": diary_id,
            "character_id": char_id,
            "at": at,
            "machine": cfg.NAMU_MACHINE,
            "via": via,
            "summary": summary,
            "mood": mood,
            "affection_delta": applied,
            "delta_reason": reason or None,
            "call_user_change": call_change,
            "topics": topics,
        }
        if applied != requested:
            entry["affection_delta_requested"] = requested
        _write_yaml(char_dir / "diary" / f"{diary_id}.yaml", entry)
        saved = (_write_archive_part(char_dir, char_id, diary_id, 1, archive, via)
                 if archive else None)

        added = []
        for text in candidates:
            pending_id = str(ULID())
            _write_yaml(char_dir / "pending" / f"{pending_id}.yaml", {
                "id": pending_id,
                "character_id": char_id,
                "text": text,
                "at": at,
                "diary_id": diary_id,
                "machine": cfg.NAMU_MACHINE,
                "via": via,
            })
            added.append({"id": pending_id, "text": text})
        after = compute_state(card, diaries + [entry])

    stage_change = None
    if after["stage"] != before["stage"]:
        stage_change = {"from": before["stage"], "to": after["stage"]}
    result = {
        "id": diary_id,
        "character": card["name"],
        "at": at,
        "when": _when(at, now),
        "affection_delta": applied,
        "clipped_from": requested if applied != requested else None,
        "relationship": _brief(after),
        "stage_change": stage_change,
        "pending_added": added,
        "pending_count": len(pending) + len(added),
        "archived": saved is not None,
        "archive": saved,
    }
    if archive_rejected:
        result["archive_rejected"] = archive_rejected
    return result


def core(name: str, action: str = "list", ids=None, *, via: "str | None" = None,
         paths: "cfg.DataPaths | None" = None) -> dict:
    """핵심 기억 — 확인 대기 후보를 보거나(list), 사용자가 좋다고 한 것을 확정하거나
    (confirm), 싫다고 한 것을 지운다(reject).

    확정은 대기 후보의 id로만 한다. 글을 새로 받아 core에 넣는 길은 없다(설계서 5.4).
    여러 id 중 하나라도 대기 목록에 없으면 아무것도 바꾸지 않고 거절한다 — 반만 처리된
    상태로 끝나면 무엇이 확정됐는지 사용자도 AI도 알 수 없다.
    """
    if action not in CORE_ACTIONS:
        raise ValueError(f"action은 {'/'.join(CORE_ACTIONS)} 중 하나여야 합니다: {action!r}")
    if ids is None:
        ids = []
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list):
        raise ValueError(f"ids는 후보 id 목록이어야 합니다: {ids!r}")
    ids = list(dict.fromkeys(str(i).strip() for i in ids))
    if action != "list" and not ids:
        raise ValueError(f"action={action}에는 ids(확인 대기 후보의 id)가 필요합니다.")
    for i in ids:
        if not _ULID_RE.match(i):
            raise ValueError(f"후보 id 모양이 아닙니다: {i!r}")

    done = []
    with _locked(paths):
        rec = _require(name, paths)
        char_id = rec["character_id"]
        char_dir = _char_dir(char_id, paths)
        pending = {p.get("id"): p for p in _read_entries(char_dir / "pending")}
        if action != "list":
            missing = [i for i in ids if i not in pending]
            if missing:
                waiting = ", ".join(f"{k}({v.get('text')})" for k, v in pending.items()) or "(없음)"
                raise ValueError(
                    f"확인 대기 목록에 없는 id입니다: {', '.join(missing)} — 아무것도 바꾸지 "
                    f"않았습니다. 지금 대기 중인 후보: {waiting}"
                )
            now = cfg.now().isoformat()
            for i in ids:
                p = pending.pop(i)
                if action == "confirm":
                    _write_yaml(char_dir / "core" / f"{i}.yaml", {
                        "id": i,
                        "character_id": char_id,
                        "text": p.get("text"),
                        "at": now,
                        "proposed_at": p.get("at"),
                        "diary_id": p.get("diary_id"),
                        "machine": cfg.NAMU_MACHINE,
                        "via": via,
                    })
                (char_dir / "pending" / f"{i}.yaml").unlink(missing_ok=True)
                done.append({"id": i, "text": p.get("text")})
        core_entries = _read_entries(char_dir / "core")

    out = {
        "character": rec["card"]["name"],
        "action": action,
        "pending": [{"id": k, "text": v.get("text")} for k, v in pending.items()],
        "core": [{"id": c.get("id"), "text": c.get("text")} for c in core_entries],
    }
    if action == "confirm":
        out["confirmed"] = done
    elif action == "reject":
        out["rejected"] = done
    return out


# ---------------------------------------------------------------------------
# 3단계 — 잊기(설계서 8·12장)
# ---------------------------------------------------------------------------
# 잊어도 git 이력에는 지우기 전 판이 남는다(설계서 12장 조사 결과). 이력을 다시 쓰면 그 저장소를
# 받아 둔 모든 PC와 클라우드 사본이 어긋나 기억 전체가 위험해지므로, 나무가 대신하지 않고
# 사용자에게 한계를 알린다 — 미리 보기와 지운 뒤 두 번 다 돌려준다.
HISTORY_NOTICE = (
    "나무에서는 지워져 다시 불러와지지 않습니다. 다만 기억을 동기화하는 GitHub 저장소의 지난 "
    "기록(커밋 이력)에는 지우기 전 내용이 남아 있어, 그 저장소에 들어갈 수 있는 사람은 옛 "
    "기록을 열어 볼 수 있습니다. 이력까지 없애려면 저장소 이력을 다시 쓰거나 저장소를 새로 "
    "만들어야 하며, 나무는 그 일을 대신하지 않습니다."
)


def _short(text, limit: int = FORGET_PREVIEW_CHARS) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def _forget_row(target: str, doc: dict, now: datetime, parts: "dict | None" = None) -> dict:
    row = {"id": doc.get("id"), "at": doc.get("at"), "when": _when(doc.get("at"), now)}
    if target == "diary":
        row.update(summary=_short(doc.get("summary")),
                   archive_parts=len((parts or {}).get(doc.get("id"), [])))
    elif target == "archive":
        row.update(diary_id=doc.get("diary_id"), part=doc.get("part") or 1,
                   chars=len(doc.get("text") or ""), head=_short(doc.get("text")))
    else:
        row["text"] = _short(doc.get("text"))
    return row


def _fingerprint(target: str, ids: list[str], files: list[Path], char_dir: Path) -> str:
    """확인표 — 지울(또는 고칠) 파일의 내용에서 계산한다. 서버가 따로 기억할 것이 없고,
    미리 보기와 확인 사이에 그 파일이 바뀌거나 딸린 항목이 늘면 값이 달라져 거절된다."""
    h = hashlib.sha256(f"{target}\n{','.join(sorted(ids))}\n".encode())
    for f in sorted(files):
        h.update(str(f.relative_to(char_dir)).encode() + b"\n")
        h.update(f.read_bytes() if f.is_file() else b"")
    return h.hexdigest()[:16]


def forget(name: str, target: str, ids=None, *, confirm: "str | None" = None,
           query: "str | None" = None, paths: "cfg.DataPaths | None" = None) -> dict:
    """잊기 — 일기·핵심 기억·원문을 골라 지우거나 캐릭터를 통째로 지운다. 세 번에 걸쳐 쓴다.

    1. 고르기: `ids` 없이 부르면 지울 수 있는 항목 목록(최근 순, `query`로 거르기)만 돌려준다.
       캐릭터 통째로(`target="character"`)는 이 차례가 없다.
    2. 미리 보기: `ids`를 주고 `confirm` 없이 부르면 함께 지워질 것과 확인표(`confirm`)를
       돌려준다. 아무것도 지우지 않는다.
    3. 지우기: 같은 인자에 확인표를 더해 부르면 그때 지운다. 그 사이 내용이 바뀌었으면 거절한다.

    일기를 잊으면 그 일기의 원문, 그 일기에서 나온 대기 후보와 확정된 핵심 기억도 함께
    지운다(설계서 12장 — 관련된 것을 함께). 원문 조각만 잊으면 일기와 다른 조각은 남는다.
    관계 상태는 저장하지 않으므로 일기를 지우는 것만으로 호감도와 단계가 다시 계산된다.
    """
    if target not in FORGET_TARGETS:
        raise ValueError(f"target은 {'/'.join(FORGET_TARGETS)} 중 하나여야 합니다: {target!r}")
    if ids is None:
        ids = []
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list):
        raise ValueError(f"ids는 지울 항목의 id 목록이어야 합니다: {ids!r}")
    ids = list(dict.fromkeys(str(i).strip() for i in ids))
    for i in ids:
        if not _ULID_RE.match(i):
            raise ValueError(f"id 모양이 아닙니다: {i!r}")
    if target == "character" and ids:
        raise ValueError("캐릭터를 통째로 잊을 때는 ids를 비워 두세요 — name으로 고릅니다.")

    with _locked(paths):
        rec = _require(name, paths)
        card, char_id = rec["card"], rec["character_id"]
        char_dir = _char_dir(char_id, paths)
        now = cfg.now()
        parts = _archive_parts(char_dir)

        if target != "character" and not ids:
            if confirm:
                raise ValueError("confirm을 쓰려면 미리 보기 때와 같은 ids를 함께 보내세요.")
            rows = _read_entries(char_dir / target)
            if query:
                q = " ".join(str(query).split()).lower()
                field = "summary" if target == "diary" else "text"
                rows = [r for r in rows if q in " ".join(str(r.get(field) or "").split()).lower()]
            return {
                "character": card["name"],
                "target": target,
                "step": "choose",
                "total": len(rows),
                "entries": [_forget_row(target, r, now, parts)
                            for r in reversed(rows[-FORGET_LIST_MAX:])],
                "next": "사용자와 지울 항목을 고른 뒤 그 id를 ids에 넣어 다시 부르면 미리 보기가 "
                        "나옵니다. 아직 아무것도 지우지 않았습니다.",
            }

        diaries = _read_entries(char_dir / "diary")
        delete: list[Path] = []
        will: dict = {}
        remaining = diaries
        if target == "character":
            delete = [f for f in char_dir.rglob("*") if f.is_file()]
            will = {
                "character": card["name"],
                "diary": len(diaries),
                "core": len(_read_entries(char_dir / "core")),
                "pending": len(_read_entries(char_dir / "pending")),
                "archive": len(_read_entries(char_dir / "archive")),
                "card_versions": len(list((char_dir / "card").glob("*.yaml"))),
            }
            remaining = []
        else:
            have = {d.get("id"): d for d in _read_entries(char_dir / target)}
            missing = [i for i in ids if i not in have]
            if missing:
                raise ValueError(
                    f"{target}에 없는 id입니다: {', '.join(missing)} — 아무것도 지우지 않았습니다. "
                    "ids 없이 부르면 고를 수 있는 목록이 나옵니다."
                )
            will[target] = [_forget_row(target, have[i], now, parts) for i in ids]
            delete += [char_dir / target / f"{i}.yaml" for i in ids]
            if target == "diary":
                chosen = set(ids)
                for sub in ("archive", "pending", "core"):
                    tied = [d for d in _read_entries(char_dir / sub) if d.get("diary_id") in chosen]
                    will[sub] = [_forget_row(sub, d, now, parts) for d in tied]
                    delete += [char_dir / sub / f"{d.get('id')}.yaml" for d in tied]
                remaining = [d for d in diaries if d.get("id") not in chosen]

        token = _fingerprint(target, ids, delete, char_dir)
        if not confirm:
            out = {
                "character": card["name"],
                "target": target,
                "step": "preview",
                "will_delete": will,
                "confirm": token,
                "notice": HISTORY_NOTICE,
                "next": "이 목록과 notice를 사용자에게 보여 주고 지워도 되는지 묻는다. 좋다고 하면 "
                        "같은 name·target·ids에 confirm을 더해 다시 부른다. 아직 아무것도 지우지 "
                        "않았습니다.",
            }
            if target != "character":
                out["relationship_after"] = _brief(compute_state(card, remaining))
            return out
        if confirm != token:
            raise ValueError(
                "확인표가 맞지 않습니다 — 미리 보기 뒤에 내용이 바뀌었거나 다른 항목의 확인표입니다. "
                "아무것도 지우지 않았습니다. confirm 없이 다시 불러 새 미리 보기를 받으세요."
            )
        if target == "character":
            shutil.rmtree(char_dir)
        else:
            for f in delete:
                f.unlink(missing_ok=True)

    out = {
        "character": card["name"],
        "target": target,
        "step": "done",
        "deleted": {k: (v if isinstance(v, int) else len(v)) for k, v in will.items()
                    if k != "character"},
        "notice": HISTORY_NOTICE,
    }
    if target != "character":
        out["relationship"] = _brief(compute_state(card, remaining))
    return out
