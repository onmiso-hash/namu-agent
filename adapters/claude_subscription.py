import asyncio
import shutil
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from adapters.base import AIAdapter, AdapterType, GenerateResult, Message, Role


class ClaudeSubscriptionAdapter(AIAdapter):
    """Claude 구독 계정(Claude.ai/Pro)을 통한 어댑터.

    claude-agent-sdk의 query()를 통해 로컬 claude CLI를 호출한다.
    API 키 없이 구독 계정으로 동작하며, claude CLI가 설치되고
    로그인된 상태여야 한다.
    """

    @property
    def name(self) -> str:
        return "claude-subscription"

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.SUBSCRIPTION

    def is_available(self) -> bool:
        # claude CLI 설치 여부 확인
        if shutil.which("claude") is None:
            return False
        # ~/.claude 디렉토리 존재 여부로 로그인 상태 추정
        # (CLI 최초 실행/로그인 시 생성됨)
        return (Path.home() / ".claude").is_dir()

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        options = self._build_options(system=system, **kwargs)
        return asyncio.run(self._aquery(prompt, options))

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> GenerateResult:
        # SYSTEM 메시지를 분리해 system_prompt로 합산
        system_parts = [m.content for m in messages if m.role == Role.SYSTEM]
        effective_system = (
            "\n\n".join(filter(None, system_parts + ([system] if system else [])))
            or None
        )

        # 대화 이력을 단일 프롬프트로 직렬화 (query()는 단방향)
        prompt = "\n\n".join(
            f"{m.role.value.upper()}: {m.content}"
            for m in messages
            if m.role != Role.SYSTEM
        )

        options = self._build_options(system=effective_system, **kwargs)
        return asyncio.run(self._aquery(prompt, options))

    # ------------------------------------------------------------------ #
    # 내부 메서드                                                           #
    # ------------------------------------------------------------------ #

    def _build_options(self, *, system: str | None, **kwargs: Any) -> ClaudeAgentOptions:
        opts: dict[str, Any] = {
            "tools": [],          # 순수 텍스트 응답만 (툴 사용 없음)
            "permission_mode": "dontAsk",
            "max_turns": 1,       # 단일 응답
        }
        if system:
            opts["system_prompt"] = system
        if "model" in kwargs:
            opts["model"] = kwargs.pop("model")
        # 나머지 kwargs는 ClaudeAgentOptions 필드로 그대로 전달
        opts.update(kwargs)
        return ClaudeAgentOptions(**opts)

    async def _aquery(self, prompt: str, options: ClaudeAgentOptions) -> GenerateResult:
        content_parts: list[str] = []
        model = "claude-subscription"
        input_tokens = 0
        output_tokens = 0
        error_msg: str | None = None

        gen = query(prompt=prompt, options=options)
        try:
            async for message in gen:
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            content_parts.append(block.text)
                    if message.model:
                        model = message.model
                    if message.usage:
                        input_tokens = message.usage.get("input_tokens", input_tokens)
                        output_tokens = message.usage.get("output_tokens", output_tokens)

                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = message.errors or []
                        error_msg = "; ".join(errors) or "unknown error"
                        break
        finally:
            await gen.aclose()

        if error_msg:
            raise RuntimeError(f"claude-agent-sdk 오류: {error_msg}")

        return GenerateResult(
            content="".join(content_parts),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
