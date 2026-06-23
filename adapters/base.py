from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AdapterType(str, Enum):
    LOCAL = "local"          # Ollama 등 로컬 모델 (최우선)
    SUBSCRIPTION = "subscription"  # Claude.ai, ChatGPT Plus 등
    API = "api"              # Claude API, GPT API, Gemini API 등


@dataclass
class Message:
    role: Role
    content: str


@dataclass
class GenerateResult:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class AIAdapter(ABC):
    """벤더 독립 AI 어댑터 추상 기본 클래스.

    모든 AI 어댑터(API/구독/로컬)는 이 클래스를 상속해 구현한다.
    우선순위: LOCAL(1) > SUBSCRIPTION(2) > API(3)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """어댑터 식별 이름 (예: 'claude-api', 'ollama-llama3')."""

    @property
    @abstractmethod
    def adapter_type(self) -> AdapterType:
        """어댑터 유형 (LOCAL / SUBSCRIPTION / API)."""

    @property
    def priority(self) -> int:
        """낮을수록 우선 선택된다."""
        return {
            AdapterType.LOCAL: 1,
            AdapterType.SUBSCRIPTION: 2,
            AdapterType.API: 3,
        }[self.adapter_type]

    @abstractmethod
    def is_available(self) -> bool:
        """현재 이 어댑터를 사용할 수 있는지 확인한다."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        """단일 프롬프트로 텍스트를 생성한다."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        """멀티턴 대화로 텍스트를 생성한다."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, type={self.adapter_type.value})"
