import os
from typing import Any

import openai

import config as cfg
from adapters.base import AIAdapter, AdapterType, GenerateResult, Message, Role


class GPTAPIAdapter(AIAdapter):
    """OpenAI GPT API 어댑터.

    OPENAI_API_KEY 환경변수 또는 config.OPENAI_API_KEY로 인증한다.
    스트리밍으로 요청해 타임아웃을 방지한다.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or cfg.OPENAI_DEFAULT_MODEL
        resolved_key = api_key or cfg.OPENAI_API_KEY or None
        self._client = openai.OpenAI(api_key=resolved_key)

    @property
    def name(self) -> str:
        return "gpt-api"

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.API

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY") or cfg.OPENAI_API_KEY)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return self._call(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        # OpenAI는 system 메시지를 messages 배열 안에 포함한다
        api_messages: list[dict[str, str]] = []

        has_system = any(m.role == Role.SYSTEM for m in messages)
        if system and not has_system:
            api_messages.append({"role": "system", "content": system})

        for m in messages:
            api_messages.append({"role": m.role.value, "content": m.content})

        return self._call(
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def _call(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> GenerateResult:
        model: str = kwargs.pop("model", self._model)

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        params.update(kwargs)

        with self._client.chat.completions.stream(**params) as stream:
            completion = stream.get_final_completion()

        choice = completion.choices[0]
        content = choice.message.content or ""
        usage = completion.usage

        return GenerateResult(
            content=content,
            model=completion.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
