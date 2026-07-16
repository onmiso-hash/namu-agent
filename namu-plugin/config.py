import os
import platform
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

# DB
NAMU_DB_PATH = NAMU_DATA_ROOT / "db" / "namu.db"

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
