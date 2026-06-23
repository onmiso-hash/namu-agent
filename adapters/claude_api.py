import os
from typing import Any

import anthropic

import config as cfg
from adapters.base import AIAdapter, AdapterType, GenerateResult, Message, Role


class ClaudeAPIAdapter(AIAdapter):
    """Anthropic Claude API 어댑터.

    ANTHROPIC_API_KEY 환경변수 또는 config.CLAUDE_API_KEY로 인증한다.
    adaptive thinking을 기본으로 사용하며, 스트리밍으로 요청한다.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or cfg.CLAUDE_DEFAULT_MODEL
        resolved_key = api_key or cfg.CLAUDE_API_KEY or None
        self._client = anthropic.Anthropic(api_key=resolved_key)

    @property
    def name(self) -> str:
        return "claude-api"

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.API

    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or cfg.CLAUDE_API_KEY)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        return self._call(
            messages=[{"role": "user", "content": prompt}],
            system=system,
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
        # Role.SYSTEM 메시지는 API의 system 파라미터로 분리한다
        system_parts = [m.content for m in messages if m.role == Role.SYSTEM]
        api_messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role != Role.SYSTEM
        ]
        effective_system = "\n\n".join(
            filter(None, system_parts + ([system] if system else []))
        ) or None

        return self._call(
            messages=api_messages,
            system=effective_system,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def _call(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> GenerateResult:
        thinking: dict[str, Any] = kwargs.pop("thinking", {"type": "adaptive"})
        model: str = kwargs.pop("model", self._model)

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": thinking,
        }
        if system:
            params["system"] = system

        # adaptive/extended thinking은 temperature=1 필수
        if thinking.get("type") in ("adaptive", "enabled"):
            params["temperature"] = 1.0
        else:
            params["temperature"] = temperature

        params.update(kwargs)

        with self._client.messages.stream(**params) as stream:
            response = stream.get_final_message()

        content = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        return GenerateResult(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
