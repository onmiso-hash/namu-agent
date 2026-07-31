import os
import platform
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from types import MappingProxyType

from dotenv import load_dotenv, find_dotenv

import task_resolve

BASE_DIR = Path(__file__).parent
# 1. 사용자가 실행한 현재 작업 폴더(cwd) 기준의 .env를 찾아 최우선 로드 (플러그인 모드 지원)
load_dotenv(find_dotenv(usecwd=True))
# 2. 없으면 플러그인 자체 경로의 .env 로드 (하위 호환)
load_dotenv(BASE_DIR / ".env")

# NAMU_DATA_ROOT: 데이터(learnings/db)가 놓이는 루트.
# namu-35: "개발 모드/설치 모드" 구분 자체를 폐지 — 어디서 실행하든(개발 repo 안에서든
# 밖에서든) 무조건 Path.home() / ".namu" 고정이다. 환경변수(NAMU_HOME)로 우회할 길도
# 없다(사용자 확정 결정) — 변수명을 NAMU_DATA_ROOT로 바꾼 것도 "환경변수가 아니라
# 고정 상수"임을 이름으로 드러내기 위함이다.
# "유령 경로" 사고(#13·#16 — 플러그인 캐시 폴더 안에 데이터가 흩어지는 문제) 방지책은
# 더 이상 폴백 순서가 아니라 이 고정 경로 자체다 — 분기할 여지가 없으니 오배선(#33)도
# 구조적으로 성립하지 않는다.
NAMU_DATA_ROOT = Path.home() / ".namu"

# DB
DB_PATH = BASE_DIR / "db" / "namu.sqlite"

# 어댑터 우선순위 (낮을수록 먼저 선택)
# AdapterType.priority 속성으로 자동 결정되므로 여기선 활성화 여부만 관리
ENABLED_ADAPTERS: list[str] = [
    # "ollama",              # 로컬 모델 (priority 1 — 최우선)
    "claude-subscription",   # 구독 계정 (priority 2)
    "claude-api",            # Claude API (priority 3)
    # "gpt-api",             # GPT API   (priority 3)
    "gemini-api",            # Gemini API (priority 5 — 최저)
]

# Claude API
CLAUDE_API_KEY: str = ""       # 환경변수 ANTHROPIC_API_KEY 권장
CLAUDE_DEFAULT_MODEL: str = "claude-sonnet-4-6"

# OpenAI API
OPENAI_API_KEY: str = ""       # 환경변수 OPENAI_API_KEY 권장
OPENAI_DEFAULT_MODEL: str = "gpt-4o"

# Gemini API
GEMINI_API_KEY: str = ""       # 환경변수 GEMINI_API_KEY 권장
GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash"

# Ollama
OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL: str = "llama3"

# 학습 기억
LEARNINGS_PATH = NAMU_DATA_ROOT / "memory" / "learnings.md"
# namu-35: "개발 모드/설치 모드" 구분(#32의 "제품지식"/"개인전역지식" 파일명 분기)을
# 폐지 — 메모리 풀이 ~/.namu 하나로 통합됐으므로 파일명은 항상 learnings.yaml이다.
LEARNINGS_YAML_PATH = NAMU_DATA_ROOT / "memory" / "learnings.yaml"

# 프로필(사실·선호) — 2그릇 메모리(namu-49) 중 profile 그릇. SQLite 캐시 없이
# 통째 로딩하는 작은 append-only yaml이다. learnings.yaml과 같은 memory/ 폴더에
# 함께 두되 파일은 분리한다(성격이 다른 지식: 사실 vs 교훈/대화기록).
PROFILE_YAML_PATH = NAMU_DATA_ROOT / "memory" / "profile.yaml"

# 이 태그가 붙은 profile 사실은 세션 시작 1회가 아니라 **사용자 입력마다** 다시
# 올라온다(namu-62 ②, hooks/prompt_reminder.py). 규칙을 몰라서가 아니라 답을 쓰기
# 직전에 대조하지 않아 어긴 사고가 실제로 있었기 때문에, 필요한 시점에 화면 안에
# 있게 하는 장치다. profile 전체를 올리지 않는 이유는 무거우면 안 읽히기 때문.
PROFILE_ALWAYS_TAG = "상시"

# 메모(스틱노트) — namu-56. 앞의 두 그릇과 결정적으로 다른 점은 **append-only가
# 아니라는 것**이다: 떼면 파일에서 그 항목이 사라진다(tombstone 없음). 이력이 남아야
# 하는 기억(learnings/profile/tasks)과 쓰고 버리는 기억을 규칙으로 가른 결과이며,
# 그래서 SQLite 인덱싱도 하지 않는다 — 지식베이스(learnings) 오염 0이 이 그릇의
# 존재 이유다("영화 시간표"를 저장할 데가 없어 learnings에 밀려들어오던 문제).
MEMO_YAML_PATH = NAMU_DATA_ROOT / "memory" / "memo.yaml"

# DB
NAMU_DB_PATH = NAMU_DATA_ROOT / "db" / "namu.db"


@dataclass(frozen=True)
class DataPaths:
    """메모리 코어가 실제로 읽고 쓰는 3경로를 담는 값 객체 (namu-53 이음새).

    root 하나만 담고 property로 파생하는 형태가 아니라 3경로를 직접 담는다 —
    `data_paths_for()`(root 미지정)가 재계산 없이 기존 모듈 상수를 그대로 반환해야
    하기 때문이다(테스트가 `cfg.NAMU_DB_PATH` 등을 monkeypatch하는 것과 호환).
    """

    learnings_yaml: Path
    profile_yaml: Path
    db_path: Path
    # namu-56 memo 그릇. 기본값을 둬서 기존 호출부(3개 인자)가 그대로 동작한다 —
    # None이면 모듈 상수(MEMO_YAML_PATH)를 쓴다는 뜻이고, 해석은 memo.py가 한다.
    memo_yaml: Path | None = None


def data_paths_for(root: "Path | str | None" = None) -> DataPaths:
    """데이터 루트를 받아 DataPaths를 만든다.

    root가 None이면(개인/stdio 기본 동작) 기존 모듈 상수 3개를 그대로 담아 반환한다
    — NAMU_DATA_ROOT로 재계산하지 않는다. 재계산하면 테스트의
    cfg.NAMU_DB_PATH/cfg.LEARNINGS_YAML_PATH/cfg.PROFILE_YAML_PATH monkeypatch가
    무시되고, 전역 동작 불변성(namu-53 요구사항)도 깨진다.

    root가 주어지면(멀티테넌트 라우팅 등 외부 이음새) `root/memory/learnings.yaml`
    등으로 파생한 경로를 담아 반환한다.
    """
    if root is None:
        return DataPaths(
            learnings_yaml=LEARNINGS_YAML_PATH,
            profile_yaml=PROFILE_YAML_PATH,
            db_path=NAMU_DB_PATH,
            memo_yaml=MEMO_YAML_PATH,
        )
    root = Path(root)
    return DataPaths(
        learnings_yaml=root / "memory" / "learnings.yaml",
        profile_yaml=root / "memory" / "profile.yaml",
        db_path=root / "db" / "namu.db",
        memo_yaml=root / "memory" / "memo.yaml",
    )


@dataclass(frozen=True)
class Bowl:
    """~/.namu에 쌓이는 "그릇"(append-only 파일군) 하나를 기술하는 레지스트리 항목
    (namu-57 3단계). git 병합 정책(.gitattributes union 라인)을 손으로 따라 적지 않고
    여기서 파생시키기 위한 단일 진실원이다 — memory_sync.py의
    `_GITATTRIBUTES_UNION_LINES` 하드코딩 3줄이 profile 그릇 추가를 누락해 실제 git
    충돌 위험을 만든 사고가 계기.

    git_patterns: `~/.namu` 기준 **상대** 경로 패턴(git이 `.gitattributes`에서 읽는
    형식)이다. 절대경로 상수(LEARNINGS_YAML_PATH 등)를 참조하지 않고 문자열로 직접
    적는다 — 이유 둘. (a) `.gitattributes` 자체가 저장소 상대 패턴만 받아들인다.
    (b) LEARNINGS_YAML_PATH 등은 테스트가 monkeypatch로 갈아끼우는 대상이라, 레지스트리가
    그걸 참조하면 "경로를 바꿔도 레지스트리 값은 그대로"라는 테스트 격리가 깨진다.
    레지스트리는 경로 상수와 완전히 독립적으로 유지한다.

    mutable/cached/web_exposed는 이번 3단계(union 라인 파생)에서 직접 쓰이지 않는
    필드도 있다 — 장식이 아니라 다음 단계(namu-56, 4단계) 예약이다. 4단계에서
    `mutable=True, merge="file"`인 memo 그릇이 추가되는데, memory_sync.py의 union 라인
    파생 함수가 `merge=="union" and not mutable`로 필터링하므로 "mutable이면 파일
    전체가 계속 바뀌는 그릇이라 줄 단위 union 병합 라인을 만들지 않는다"는 규칙이
    이 필드 하나로 실제 동작한다(지금은 3그릇 모두 mutable=False라 필터가 전부 통과할
    뿐, 게이트 로직 자체는 이미 살아있다).
    """

    name: str
    git_patterns: tuple[str, ...]
    mutable: bool
    merge: str  # "union"(줄 단위 병합) | "file"(파일 단위 — 병합 전략 불필요)
    cached: bool  # SQLite(NAMU_DB_PATH)에 인덱싱되는가
    web_exposed: bool  # 웹 MCP 도구(namu_record 등)로 노출되는가
    # 사람이 읽는 이름(namu-65). 거절 메시지가 "bowl='profile'로 보내세요"가 아니라
    # "개인 사실 그릇으로 보내세요"라고 말할 수 있어야 하고, 그 번역표가 메시지를
    # 만드는 쪽마다 흩어지면 그릇 이름과 어긋난다 — 레지스트리에 함께 둔다.
    label: str = ""


# 그릇 레지스트리. 순서는 learnings → tasks → profile을 유지한다 — 기존
# `.gitattributes`(namu-34 ③-c 때 만들어진 3줄: learnings 1 + tasks 2)를 가진 설치본이
# 이 순서대로 파생되는 union 라인과 그대로 일치해, 새로 추가되는 줄이 profile 1줄뿐이
# 되게 하기 위함(불필요한 파일 변경 최소화). memo 그릇(namu-56, 4단계) 등 새 그릇은
# 이 끝에 추가한다 — 순서를 바꾸면 기존 설치본의 .gitattributes가 통째로 재작성된다.
BOWLS: tuple[Bowl, ...] = (
    Bowl(
        name="learnings",
        git_patterns=("memory/learnings.yaml",),
        mutable=False,
        merge="union",
        cached=True,
        web_exposed=True,
        label="교훈",
    ),
    Bowl(
        name="tasks",
        git_patterns=("tasks/**/log.md", "tasks/*/.project"),
        mutable=False,
        merge="union",
        cached=False,
        web_exposed=True,
        label="작업일지",
    ),
    Bowl(
        name="profile",
        git_patterns=("memory/profile.yaml",),
        mutable=False,
        merge="union",
        cached=False,
        web_exposed=True,
        label="개인 사실",
    ),
    # memo(namu-56) — 유일한 mutable 그릇. merge="union"이 아니라 "file"인 이유가
    # 핵심이다: 줄 단위 union 병합을 걸면 한쪽 PC에서 뗀 메모가 다른 PC의 파일에
    # 남아 있다가 병합 때 **되살아난다**(union은 삭제를 표현할 수 없다). mutable
    # 게이트가 union 라인 파생에서 이 그릇을 자동으로 빼주므로 memory_sync는
    # 손댈 필요가 없다 — 3단계에서 이 자리를 예약해 둔 그대로다.
    Bowl(
        name="memo",
        git_patterns=("memory/memo.yaml",),
        mutable=True,
        merge="file",
        cached=False,
        web_exposed=True,
        label="쪽지",
    ),
)


BOWL_NAMES: tuple[str, ...] = tuple(bowl.name for bowl in BOWLS)


def bowl_label(name: str) -> str:
    """그릇 이름 → 사람이 읽는 이름("learnings" → "교훈"). 모르는 이름은 그대로."""
    for bowl in BOWLS:
        if bowl.name == name:
            return bowl.label or bowl.name
    return name


# ---------------------------------------------------------------------------
# 그릇별 허용 칸 선언 (namu-65 구현 1단계 — docs/memory_schema_v2.md 7장)
# ---------------------------------------------------------------------------
#
# 왜 선언으로 두나: 한 칸이 "요약"과 "상세" 두 일을 겸하도록 설계된 탓에 교훈 157건
# 중 149건이 원 의도(reason 100자 이하)를 벗어났고, `text`처럼 그릇이 받지 않는 칸은
# **말없이 버려져** 웹에서 저장한 조사 원문이 통째로 사라지는 사고가 났다. 어느 칸이
# 어느 그릇에서 유효한지가 mcp_server의 분기문 안에만 흩어져 있었기 때문이다.
# 이 표 하나에서 ①입력 검증(2단계) ②거절·안내 메시지 ③도구 설명문 ④저장 계층의
# 칸 목록(3단계)을 전부 파생시켜, 같은 결함이 옆 그릇에서 재발하지 못하게 한다.
#
# 이 블록 자체는 **선언일 뿐 아무 동작도 바꾸지 않는다** — 파생시키는 쪽은 2단계부터다.

# 3층 중 적을 게 없는 칸에 넣는 한 단어(설계 원칙 3). 빈 문자열을 허용하면 "안 적은
# 것"과 "적을 게 없다고 판단한 것"이 구분되지 않아, 화면에서 감출지 경고할지 정할 수
# 없다. 화면에서는 이 값이 든 줄을 감춘다.
OMITTED = "생략"


def is_omitted(value: "str | None") -> bool:
    """`생략` 한 단어인가(앞뒤 공백 무시). 화면에서 감출지 판단하는 단일 기준."""
    return (value or "").strip() == OMITTED


@dataclass(frozen=True)
class Field:
    """`namu_record`가 받는 입력 칸 하나의 선언(namu-65).

    bowls/required_in에 그릇 이름을 적는 것이 곧 그 그릇의 스키마 결정이다.
    - `bowls`에 없는 그릇으로 이 칸이 오면 **조용히 버리지 않고 거절**하고,
      `bowls_accepting()`이 알려주는 갈 곳을 메시지에 적는다(설계 원칙 4).
    - `required_in`의 그릇에서 이 칸이 비면 거절한다. `생략` 한 단어는 채운 것으로 본다.

    desc/example은 장식이 아니라 산출물이다 — 완료조건 2가 "항목마다 개별 설명(어느
    그릇에서 필수인지·쓰면 안 되는지·예시 한 줄)"을 요구하며, 도구 설명문을 손으로
    쓰면 표와 어긋난다. 설명문은 이 값들에서 만든다.

    values: **그릇마다 다르다.** 같은 `status`라도 교훈은 success/failure/partial로
    닫혀 있지만 작업일지 꼬리표는 실제로 30가지가 쓰이고 있어(`[결정]` 91회, `[분담]`
    60회 등) 닫으면 기존 사용을 깬다. 그래서 "필드 하나에 값 목록 하나"가 아니라
    그릇별 매핑이며, 항목이 없는 그릇은 자유 입력이다.
    """

    name: str
    bowls: tuple[str, ...]        # 이 칸을 받는 그릇 (여기 없으면 거절)
    required_in: tuple[str, ...]  # 비면 거절하는 그릇
    desc: str                     # 개별 설명 — 도구 설명문·거절 메시지 공용
    example: str                  # 예시 한 줄 (완료조건 2 ③)
    values: "Mapping[str, tuple[str, ...]]" = MappingProxyType({})  # 그릇별 닫힌 허용값


_ALL_BOWLS = ("learnings", "profile", "tasks", "memo")

# 3층(summary/reason/body)은 네 그릇 전부에서 필수다 — 예외 없음(설계 원칙 2).
# 적을 게 없으면 `생략`을 넣는다. reason을 필수에서 빼자는 재검토는 이미 닫힌
# 논점이다: 기존 작업일지 450줄에 reason이 없던 것은 **칸 자체가 없었기 때문**이지
# 불필요해서가 아니다.
FIELDS: tuple[Field, ...] = (
    # ── 내용 3층 ────────────────────────────────────────────────────────────
    Field(
        name="summary",
        bowls=_ALL_BOWLS,
        required_in=_ALL_BOWLS,
        desc="한 줄 요약(무엇을?). 브리핑·목록 화면에 그대로 실리는 유일한 칸이라, "
             "일을 한 AI가 저장 시점에 한 번 쓰고 고정한다 — 나중 세션이 볼 때마다 "
             "새로 지어내던 요약이 매번 달라지던 문제를 여기서 끊는다.",
        example="브리핑 가독성 수정은 데이터 구조 결함을 화면에서 걸레질한 것이었다",
    ),
    Field(
        name="reason",
        bowls=_ALL_BOWLS,
        required_in=_ALL_BOWLS,
        desc="왜 그런가 / 어떻게 알았나 / 왜 남기나(짧은 문단). 결론만 남기면 다음 "
             "세션이 판단 근거를 알 수 없어 같은 논의를 되풀이한다.",
        example="한 칸이 요약과 상세를 겸해 157건 중 149건이 원 의도를 벗어났기 때문",
    ),
    Field(
        name="body",
        bowls=_ALL_BOWLS,
        required_in=_ALL_BOWLS,
        desc="그때 무슨 일이 있었나 — 원문·경위 전부(길이 제한 없음). 쪽지에서는 "
             "붙여둔 원문 자체가 여기 들어간다. 이 칸이 없어서 웹에서 저장한 조사 "
             "원문이 통째로 사라졌다.",
        example="(조사 자료 전문·재현 절차·측정값 등 원문 그대로)",
    ),
    # ── 분류 ────────────────────────────────────────────────────────────────
    Field(
        name="bowl",
        # 2026-07-31 사용자 결정 — **생략 불가**. 옛 동작은 그릇을 안 적으면 조용히
        # 교훈으로 보냈는데(kind 기본값 'lesson'), 이번에 kind를 없애면 그 자리에
        # "말없이 교훈행"만 남는다. 그건 이 작업이 없애려는 결함과 같은 종류다:
        # 잘못 담겨도 아무도 모르고, 교훈 창고가 지저분해진 뒤에야 드러난다(쪽지
        # 그릇이 생긴 이유 자체가 일회성 메모의 learnings 유입이었다).
        # 그릇 선택에도 설계 원칙 4를 그대로 적용한다 — 거절하고 갈 곳을 알려준다
        # (`suggest_bowl()`이 준 칸을 보고 후보를 짚어준다).
        # 옛 이름(kind='fact' 등)으로 부르는 호출은 종전 해석을 유지하므로 안 깨진다.
        bowls=_ALL_BOWLS,
        required_in=_ALL_BOWLS,
        desc="어느 그릇에 담을지. 생략할 수 없다 — 안 적으면 거절하고 네 그릇을 "
             "안내한다. 교훈(learnings)은 다시 쓸 배움, 개인 사실(profile)은 사용자에 "
             "대한 사실, 작업일지(tasks)는 진행 기록, 쪽지(memo)는 쓰고 버릴 메모다.",
        example="memo",
        values=MappingProxyType({bowl: _ALL_BOWLS for bowl in _ALL_BOWLS}),
    ),
    Field(
        name="topic",
        bowls=("learnings", "profile", "tasks"),
        required_in=("learnings", "profile", "tasks"),
        desc="주제·작업 이름. 교훈은 어느 작업에서 얻었는지, 개인 사실은 무엇에 대한 "
             "사실인지(옛 subject), 작업일지는 어느 작업의 log.md에 붙일지를 정한다 "
             "— 작업일지에서는 이미 있는 작업의 이름이나 그 앞부분이어야 한다. "
             "쪽지는 받지 않는다(쓰고 버리는 그릇이라 분류할 이유가 없다).",
        example="namu-65-memory-schema-unify",
    ),
    Field(
        name="status",
        bowls=("learnings", "tasks"),
        required_in=(),
        desc="상태. 교훈은 success/failure/partial 셋 중 하나이며, 비면 교훈이 아니라 "
             "단순 기록으로 취급한다(옛 kind를 대신하는 판정 기준). 작업일지는 줄 앞에 "
             "붙는 꼬리표이고 기본값은 '기록'이다. 개인 사실·쪽지는 받지 않는다. "
             "주의: 작업일지의 '완료'/'중단'은 **작업 전체가 닫힌다**는 뜻이라 진행 "
             "메모에 쓰면 열린 작업 목록에서 사라진다(실제 사고 2회). 반대로 "
             "'종료'·'마무리' 같은 비슷한 말은 **닫지 못하므로 거절한다** — 닫는 말은 "
             "이 둘뿐이다(namu-66).",
        example="failure",
        values=MappingProxyType({"learnings": ("success", "failure", "partial")}),
        # tasks는 일부러 닫지 않는다 — 실제 로그에 30가지 꼬리표가 쓰이고 있어
        # 5가지로 닫으면 기존 사용을 깬다. 권장값: 시작·기록·다음·완료·중단.
    ),
    Field(
        name="category",
        bowls=("learnings",),
        required_in=(),
        desc="갈래. 생략하면 other. 교훈 전용이다(옛 task_type).",
        example="code",
        values=MappingProxyType({"learnings": ("code", "doc", "analysis", "other")}),
    ),
    Field(
        name="tags",
        bowls=("learnings", "profile", "memo"),
        required_in=(),
        desc="꼬리표 목록. 개인 사실에 '상시'를 붙이면 세션 시작 1회가 아니라 "
             "사용자 입력마다 다시 올라온다. 작업일지는 받지 않는다 — 거기서 꼬리표에 "
             "해당하는 것은 status다.",
        example="['상시', '출력규칙']",
    ),
    # ── 대상·부가 ───────────────────────────────────────────────────────────
    Field(
        name="project",
        bowls=("tasks",),
        required_in=(),
        desc="프로젝트 폴더 이름. 작업일지 전용이다. 로컬에서는 생략하면 현재 폴더로 "
             "보지만, 웹에는 현재 폴더라는 것이 없으므로 반드시 적어야 한다.",
        example="namu-agent",
    ),
    Field(
        name="confidence",
        bowls=("learnings", "profile"),
        required_in=(),
        desc="이 내용을 사람이 확인했는지, AI 판단인지(옛 verified_by). 나중에 신뢰도로 "
             "거르기 위한 칸이라 짐작을 human으로 적으면 안 된다.",
        example="human",
        values=MappingProxyType({
            "learnings": ("human", "ai", "unverified"),
            "profile": ("human", "ai", "unverified"),
        }),
    ),
    Field(
        name="supersedes",
        bowls=("profile",),
        required_in=(),
        desc="정정할 옛 기록의 id. 개인 사실은 고쳐 쓰지 않고(append-only) 새 항목이 "
             "옛 항목을 가리키는 방식으로 정정한다.",
        example="01KYKFDR8Q2N7V0C6W3M5Y1XT",
    ),
    Field(
        name="create",
        bowls=("tasks",),
        required_in=(),
        desc="참이면 새 작업 폴더를 만든다. 거짓(기본)일 때 없는 작업 이름을 주면 "
             "만들지 않고 후보를 들어 거절한다.",
        example="True",
    ),
    Field(
        name="done_when",
        bowls=("tasks",),
        required_in=(),
        desc="완료조건 목록. 작업을 새로 만들 때(create) 체크리스트로 적힌다.",
        example="['입력 항목이 13개로 정리된다', '기존 테스트 386개 통과']",
    ),
)

FIELD_NAMES: tuple[str, ...] = tuple(field.name for field in FIELDS)
_FIELDS_BY_NAME: "Mapping[str, Field]" = MappingProxyType(
    {field.name: field for field in FIELDS}
)


def field_by_name(name: str) -> "Field | None":
    return _FIELDS_BY_NAME.get(name)


def fields_for(bowl: str) -> tuple[Field, ...]:
    """그 그릇이 받는 칸 선언 전부(선언 순서 유지 — 도구 설명문이 이 순서로 나온다)."""
    return tuple(field for field in FIELDS if bowl in field.bowls)


def allowed_fields(bowl: str) -> frozenset[str]:
    """그 그릇이 받는 칸 이름. 여기 없는 칸이 오면 버리지 말고 거절한다."""
    return frozenset(field.name for field in FIELDS if bowl in field.bowls)


def required_fields(bowl: str) -> frozenset[str]:
    """그 그릇에서 비면 거절하는 칸 이름(`생략` 한 단어는 채운 것으로 본다)."""
    return frozenset(field.name for field in FIELDS if bowl in field.required_in)


def bowls_accepting(field_name: str) -> tuple[str, ...]:
    """그 칸을 받는 그릇 이름들. 거절 메시지에 "어디로 가야 하는지"를 적기 위한 것이라,
    모르는 칸 이름이면 빈 튜플을 준다(=갈 곳이 없다는 뜻)."""
    field = _FIELDS_BY_NAME.get(field_name)
    return field.bowls if field else ()


def allowed_values(field_name: str, bowl: str) -> tuple[str, ...]:
    """그 그릇에서 그 칸이 받는 닫힌 값 목록. 빈 튜플이면 자유 입력이다."""
    field = _FIELDS_BY_NAME.get(field_name)
    if field is None:
        return ()
    return tuple(field.values.get(bowl, ()))


@dataclass(frozen=True)
class FieldAlias:
    """옛 이름 → 새 이름 대응(namu-65 설계서 4장).

    옛 이름으로 호출해도 **거절하지 않고 새 이름으로 옮겨 저장한 뒤, 어디로 옮겼는지
    반환문에 알린다.** 말없이 버리는 경로를 코드에서 없애는 것이 이번 작업의 핵심이고,
    옛 이름을 조용히 무시하는 것도 같은 종류의 유실이다.

    bowls가 비어 있으면 모든 그릇에 적용된다. `text`처럼 그릇마다 갈 곳이 다른 이름이
    있어서 그릇을 함께 적는다 — 이 이름 하나가 이번 사고의 원인이었다.
    """

    old: str
    new: "str | None"  # None = 없앤 칸(대체 없음)
    bowls: tuple[str, ...] = ()
    note: str = ""


FIELD_ALIASES: tuple[FieldAlias, ...] = (
    FieldAlias("task", "topic", note="교훈의 작업 이름"),
    FieldAlias("subject", "topic", note="개인 사실의 주제"),
    FieldAlias("statement", "summary",
               note="한 줄은 summary, 상세가 있으면 body로 나눠 넣는다"),
    FieldAlias("source", "reason", note="'어떻게 아는가'라 2층(reason)이 맞다"),
    FieldAlias("outcome", "status"),
    FieldAlias("tag", "status", bowls=("tasks",), note="작업일지 꼬리표"),
    # 이번 사고의 원인이 된 이름. 작업일지에서는 줄에 적히는 한 줄이라 summary지만,
    # 나머지 그릇에서는 통째로 버려지던 원문이므로 body로 살린다.
    FieldAlias("text", "summary", bowls=("tasks",), note="작업일지의 한 줄"),
    FieldAlias("text", "body", bowls=("learnings", "profile", "memo"),
               note="옛 경로에서 말없이 버려지던 원문 — body로 살린다"),
    FieldAlias("task_type", "category"),
    FieldAlias("verified_by", "confidence"),
    FieldAlias("kind", None,
               note="없앴다 — status가 있으면 교훈, 없으면 단순 기록으로 본다"),
    FieldAlias("title", "summary", bowls=("tasks",), note="작업을 새로 만들 때"),
    FieldAlias("purpose", "reason", bowls=("tasks",), note="작업을 새로 만들 때"),
)


def resolve_field_alias(old: str, bowl: str) -> "FieldAlias | None":
    """옛 이름 + 그릇 → 대응 선언. 그릇을 지정한 항목을 먼저 본다(text처럼 그릇마다
    갈 곳이 다른 이름이 있으므로, 전체 적용 항목이 앞서 잡히면 안 된다)."""
    for alias in FIELD_ALIASES:
        if alias.old == old and bowl in alias.bowls:
            return alias
    for alias in FIELD_ALIASES:
        if alias.old == old and not alias.bowls:
            return alias
    return None


def suggest_bowl(field_names: "Iterable[str]") -> "str | None":
    """준 칸 이름만 보고 그릇 하나를 추정한다. 확실하지 않으면 None(추측 금지).

    그릇을 안 적어 거절할 때 "네 개 중 고르세요"로 끝내지 않고 후보를 짚어주기 위한
    것이다(설계 원칙 4). 근거는 **그 칸을 받는 그릇이 하나뿐인 경우**뿐이다 — 예를
    들어 project/create/done_when은 작업일지만, supersedes는 개인 사실만, category는
    교훈만 받는다. 근거가 갈리면 조용히 하나를 고르지 않고 None을 준다: 빗나간 추천은
    없느니만 못하고, 애초에 이 작업이 없애려는 것이 '조용한 짐작'이다.

    옛 이름도 근거로 본다(tag·title·purpose는 작업일지 전용). 다만 갈 곳이 그릇마다
    다른 이름(`text`)은 근거에서 뺀다 — 그 이름 하나가 이번 사고의 원인이었다.
    """
    votes: set[str] = set()
    for name in field_names:
        field = _FIELDS_BY_NAME.get(name)
        if field is not None:
            if len(field.bowls) == 1:
                votes.add(field.bowls[0])
            continue
        scoped = {
            bowl
            for alias in FIELD_ALIASES
            if alias.old == name
            for bowl in alias.bowls
        }
        if len(scoped) == 1:
            votes.add(next(iter(scoped)))
    return next(iter(votes)) if len(votes) == 1 else None


# 머신 식별자 (.env의 NAMU_MACHINE에서 주입)
# 해석 규칙:
#   1. NAMU_MACHINE 환경변수가 있고 공백 제거 후 비지 않으면 그 값(strip만, 대소문자 유지)
#   2. 없거나 빈 값이면 platform.node()(호스트명)를 소문자화+strip한 값
#   3. 그것도 비면 "unknown"
def _resolve_machine(env_value: str | None) -> str:
    if env_value is not None and env_value.strip():
        return env_value.strip()
    hostname = platform.node().strip().lower()
    if hostname:
        return hostname
    return "unknown"


NAMU_MACHINE: str = _resolve_machine(os.getenv("NAMU_MACHINE"))


# 기록 시각의 기준 시간대 (namu-57 5단계)
#
# tasks 로그(log.md)의 시각은 시간대 표기 없는 벽시계 문자열(`2026-07-25 18:31:51`)이라,
# 각 호스트가 제 현지시각을 적으면 **같은 파일 안에서 시각끼리 비교가 불가능해진다**.
# 실제로 웹 커넥터(미니PC 도커 컨테이너, TZ=UTC)가 기록을 시작하자 그 줄만 9시간 과거로
# 적혀, 브리핑의 "최근 활동" 정렬에서 최신 기록이 묻히고 task의 `last_ts`가 거꾸로 갔다
# (namu-57 웹 실측에서 실측 재현). 기존 로그 40여 개는 전부 한국시각으로 적혀 있으므로,
# 모든 호스트가 같은 기준 시간대로 적게 하면 옛 기록과 새 기록이 그대로 비교 가능해진다.
#
# 학습/사실 그릇(db.py)은 처음부터 UTC aware ISO(`+00:00`)라 이 문제가 없다 — 여기서
# 고치는 대상은 "사람이 읽는 벽시계 문자열"을 쓰는 tasks 로그뿐이다.
NAMU_TZ: str = (os.getenv("NAMU_TZ") or "").strip() or "Asia/Seoul"


def _resolve_tzinfo(name: str) -> tzinfo | None:
    """`name`(IANA 시간대)을 tzinfo로. 실패하면 None(=호스트 현지시각 폴백).

    zoneinfo는 OS의 tz 데이터베이스를 쓰므로 Windows나 slim 컨테이너에서는
    없을 수 있다(그래서 `tzdata`를 의존성에 넣었다). 그럼에도 못 찾는 환경이면
    **기록 자체를 실패시키지 않고** 종전처럼 현지시각으로 적는다 — 시각이 어긋나는
    것보다 기록이 유실되는 쪽이 훨씬 나쁘고, 폴백해도 결과는 고치기 전과 같다.
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        return None


def local_tz() -> tzinfo | None:
    """기준 시간대(NAMU_TZ)의 tzinfo. tz 데이터가 없으면 None(=현지시각 폴백).

    기록하는 쪽(now)뿐 아니라 **읽는 쪽**도 같은 해석 경로를 써야 한다 — 예를 들어
    훅이 다른 시간대(UTC)로 적힌 값을 log.md의 벽시계 문자열과 비교하려면 먼저 이
    시간대로 옮겨야 한다(namu-57 5단계와 같은 함정).
    """
    return _resolve_tzinfo(NAMU_TZ)


def now() -> datetime:
    """기록용 현재 시각. 기준 시간대(NAMU_TZ)로 맞춘 aware datetime.

    시간대 이름은 NAMU_MACHINE과 같이 모듈 로드 시점 상수(NAMU_TZ)지만, tzinfo 해석은
    호출 시점에 한다 — 테스트가 `monkeypatch.setattr(cfg, "NAMU_TZ", ...)`로 갈아끼울
    수 있고, tz 데이터가 없는 환경에서 import 자체가 실패하지도 않는다.
    """
    tz = local_tz()
    return datetime.now(tz) if tz is not None else datetime.now()

# 작업 기록(tasks) — 메모리(NAMU_DATA_ROOT)와 저장소를 분리한다.
# tasks는 여전히 "프로젝트 귀속" 데이터지만, 저장 위치는 개인 풀
# `~/.namu/tasks/<basename(project_dir)>/`로 통합한다(namu-34) — 공개 repo에 작업
# 기록이 노출되는 것을 막고 PC 간 공유를 개인 전역 동기화에 편승시키기 위해서다.
# NAMU_DATA_ROOT는 이제 학습 기억(LEARNINGS_*/NAMU_DB_PATH) 전용으로만 남는다.
# 규칙은 task_resolve.py(stdlib)에 단일 구현돼 있고, 여기서는 위임만 한다
# (규칙 이중 구현 금지 — statusline 등 plain python3 소비자와 동일 결과를 보장).
#
# 모듈 로드 시점 상수로 고정하면 cwd가 import 시점에 박혀버리므로, 고정 상수 대신
# 호출자가 프로젝트 경로를 넘기는 헬퍼로 둔다. project_dir 생략 시 os.getcwd() 사용.
def tasks_dir_for(project_dir: str | os.PathLike | None = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return task_resolve.tasks_root_for(base)

# GitHub 동기화 (2단계 이후)
GITHUB_SYNC_ENABLED: bool = False
GITHUB_REPO: str = ""


# 원격 MCP HTTP 서버 설정 (namu-44, docs/remote_mcp_design.md v4)
# 호출 시점에 환경변수를 읽는다 — 모듈 로드 시점 상수로 고정하면(NAMU_MACHINE처럼)
# 테스트에서 monkeypatch.setenv로 격리하기 어렵고, http_server 기동 시점에만 필요한
# 값이라 지연 평가해도 손해가 없다.
def http_settings() -> dict:
    """NAMU_HTTP_* 환경변수를 읽어 원격 HTTP 서버 설정 dict로 반환한다.

    Returns:
      token: 헤더 인증용 토큰 (NAMU_HTTP_TOKEN, strip, 기본 "")
      path_secret: 시크릿 경로 세그먼트 (NAMU_HTTP_PATH_SECRET, strip, 기본 "")
      host: 바인드 호스트 (NAMU_HTTP_HOST, 기본 "127.0.0.1")
      port: 바인드 포트 (NAMU_HTTP_PORT, int, 기본 8765)
      pull_interval: 디바운스 pull 간격(초) (NAMU_HTTP_PULL_INTERVAL, float, 기본 60.0)
      allow_noauth: 무인증 기동 허용 (NAMU_HTTP_ALLOW_NOAUTH == "1")
      allowed_hosts: 원격(터널) Host 헤더 허용 목록 (NAMU_HTTP_ALLOWED_HOSTS, 쉼표 구분,
        각 항목 strip, 빈 항목 제거, 미설정/빈 값이면 [])

    path_secret는 URL 경로 세그먼트(`/mcp/<secret>`)로 그대로 쓰이므로 `/`를 포함하면
    경로 구조가 깨진다 — ValueError로 즉시 드러낸다(조용한 오배선 방지).
    """
    path_secret = os.environ.get("NAMU_HTTP_PATH_SECRET", "").strip()
    if "/" in path_secret:
        raise ValueError(
            "NAMU_HTTP_PATH_SECRET에 '/'를 포함할 수 없습니다 (URL 경로 세그먼트로 쓰임)"
        )

    port_raw = os.environ.get("NAMU_HTTP_PORT", "8765").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(
            f"NAMU_HTTP_PORT 값이 정수가 아닙니다: {port_raw!r}"
        ) from exc

    interval_raw = os.environ.get("NAMU_HTTP_PULL_INTERVAL", "60.0").strip()
    try:
        pull_interval = float(interval_raw)
    except ValueError as exc:
        raise ValueError(
            f"NAMU_HTTP_PULL_INTERVAL 값이 숫자가 아닙니다: {interval_raw!r}"
        ) from exc

    allowed_hosts_raw = os.environ.get("NAMU_HTTP_ALLOWED_HOSTS", "")
    allowed_hosts = [
        item.strip() for item in allowed_hosts_raw.split(",") if item.strip()
    ]

    return {
        "token": os.environ.get("NAMU_HTTP_TOKEN", "").strip(),
        "path_secret": path_secret,
        "host": os.environ.get("NAMU_HTTP_HOST", "127.0.0.1").strip(),
        "port": port,
        "pull_interval": pull_interval,
        "allow_noauth": os.environ.get("NAMU_HTTP_ALLOW_NOAUTH", "") == "1",
        "allowed_hosts": allowed_hosts,
    }
