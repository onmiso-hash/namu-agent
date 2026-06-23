import os
from typing import Any

from google import genai
from google.genai import types

import config as cfg
from adapters.base import AIAdapter, AdapterType, GenerateResult, Message, Role


class GeminiAPIAdapter(AIAdapter):
    """Google Gemini API 어댑터.

    GEMINI_API_KEY 환경변수 또는 config.GEMINI_API_KEY로 인증한다.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or cfg.GEMINI_DEFAULT_MODEL
        self._api_key = api_key or cfg.GEMINI_API_KEY or None
        self._client: genai.Client | None = None  # 지연 초기화 — 키 없이도 인스턴스 생성 가능

    def _get_client(self) -> genai.Client:
        if self._client is None:
            key = self._api_key or os.environ.get("GEMINI_API_KEY") or ""
            self._client = genai.Client(api_key=key)
        return self._client

    @property
    def name(self) -> str:
        return "gemini-api"

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.API

    @property
    def priority(self) -> int:
        return 5  # API 어댑터 중 가장 낮은 우선순위

    def is_available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY") or cfg.GEMINI_API_KEY)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        model: str = kwargs.pop("model", self._model)
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            **({"system_instruction": system} if system else {}),
        )
        response = self._get_client().models.generate_content(
            model=model,
            contents=prompt,
            config=config,
            **kwargs,
        )
        return self._build_result(response, model)

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        model: str = kwargs.pop("model", self._model)

        system_parts = [m.content for m in messages if m.role == Role.SYSTEM]
        effective_system = "\n\n".join(
            filter(None, system_parts + ([system] if system else []))
        ) or None

        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            **({"system_instruction": effective_system} if effective_system else {}),
        )

        # Gemini는 "user" / "model" 역할만 허용한다
        contents = [
            types.Content(
                role="model" if m.role == Role.ASSISTANT else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != Role.SYSTEM
        ]

        response = self._get_client().models.generate_content(
            model=model,
            contents=contents,
            config=config,
            **kwargs,
        )
        return self._build_result(response, model)

    @staticmethod
    def _build_result(response: Any, model: str) -> GenerateResult:
        usage = response.usage_metadata
        return GenerateResult(
            content=response.text or "",
            model=model,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )
