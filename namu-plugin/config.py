import os
import platform
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path

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
    ),
    Bowl(
        name="tasks",
        git_patterns=("tasks/**/log.md", "tasks/*/.project"),
        mutable=False,
        merge="union",
        cached=False,
        web_exposed=True,
    ),
    Bowl(
        name="profile",
        git_patterns=("memory/profile.yaml",),
        mutable=False,
        merge="union",
        cached=False,
        web_exposed=True,
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
    ),
)


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


def now() -> datetime:
    """기록용 현재 시각. 기준 시간대(NAMU_TZ)로 맞춘 aware datetime.

    시간대 이름은 NAMU_MACHINE과 같이 모듈 로드 시점 상수(NAMU_TZ)지만, tzinfo 해석은
    호출 시점에 한다 — 테스트가 `monkeypatch.setattr(cfg, "NAMU_TZ", ...)`로 갈아끼울
    수 있고, tz 데이터가 없는 환경에서 import 자체가 실패하지도 않는다.
    """
    tz = _resolve_tzinfo(NAMU_TZ)
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
