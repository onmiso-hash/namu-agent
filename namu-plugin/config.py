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
# 미설정 시 repo 루트(REPO_ROOT)로 폴백 — repo 직접 실행 하위호환.
# 플러그인 모드에서는 BASE_DIR이 캐시 경로이므로 반드시 NAMU_HOME을 셸 환경변수로 지정해야 함.
NAMU_HOME = Path(os.environ.get("NAMU_HOME", REPO_ROOT))

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
