import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

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
LEARNINGS_PATH = BASE_DIR / "memory" / "learnings.md"
LEARNINGS_YAML_PATH = BASE_DIR / "memory" / "learnings.yaml"

# DB
NAMU_DB_PATH = BASE_DIR / "db" / "namu.db"

# 머신 식별자 (.env의 NAMU_MACHINE에서 주입)
NAMU_MACHINE: str = os.getenv("NAMU_MACHINE", "unknown")

# 작업 기록
TASKS_DIR = BASE_DIR / "tasks"

# GitHub 동기화 (2단계 이후)
GITHUB_SYNC_ENABLED: bool = False
GITHUB_REPO: str = ""
