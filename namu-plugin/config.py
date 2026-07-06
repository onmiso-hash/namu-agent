import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

BASE_DIR = Path(__file__).parent
REPO_ROOT = BASE_DIR.parent
# 1. 사용자가 실행한 현재 작업 폴더(cwd) 기준의 .env를 찾아 최우선 로드 (플러그인 모드 지원)
load_dotenv(find_dotenv(usecwd=True))
# 2. 없으면 플러그인 자체 경로의 .env 로드 (하위 호환)
load_dotenv(BASE_DIR / ".env")

# NAMU_HOME: 데이터(learnings/tasks/db)가 놓이는 루트.
# 우선순위:
#   1. NAMU_HOME 환경변수 (.env 경유 포함) — 명시적 지정, 항상 최우선.
#   2. REPO_ROOT/memory 가 실재하면 REPO_ROOT — repo를 클론해 직접 실행하는 하위호환 경로.
#   3. 그 외엔 Path.home() / ".namu" — 플러그인 설치형 기본값(분리 모드).
#      플러그인 캐시 폴더에는 memory/ 가 복사되지 않으므로, env 미설정 사용자가
#      캐시 안에 데이터를 쓰는 "유령 경로" 사고(#13·#16)를 이 폴백이 방지한다.
if "NAMU_HOME" in os.environ:
    NAMU_HOME = Path(os.environ["NAMU_HOME"])
elif (REPO_ROOT / "memory").is_dir():
    NAMU_HOME = REPO_ROOT
else:
    NAMU_HOME = Path.home() / ".namu"

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
LEARNINGS_PATH = NAMU_HOME / "memory" / "learnings.md"
LEARNINGS_YAML_PATH = NAMU_HOME / "memory" / "learnings.yaml"

# DB
NAMU_DB_PATH = NAMU_HOME / "db" / "namu.db"

# 머신 식별자 (.env의 NAMU_MACHINE에서 주입)
NAMU_MACHINE: str = os.getenv("NAMU_MACHINE", "unknown")

# 작업 기록
TASKS_DIR = NAMU_HOME / "tasks"

# GitHub 동기화 (2단계 이후)
GITHUB_SYNC_ENABLED: bool = False
GITHUB_REPO: str = ""
