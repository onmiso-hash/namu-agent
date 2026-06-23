from typing import Any

import openai

import config as cfg
from adapters.base import AIAdapter, AdapterType, GenerateResult, Message, Role


class OllamaAdapter(AIAdapter):
    """Ollama 로컬 모델 어댑터.

    Ollama의 OpenAI 호환 엔드포인트(/v1)를 사용한다.
    API 키가 필요 없으므로 더미 값을 전달한다.
    """

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self._model = model or cfg.OLLAMA_DEFAULT_MODEL
        self._host = (host or cfg.OLLAMA_HOST).rstrip("/")
        self._client = openai.OpenAI(
            base_url=f"{self._host}/v1",
            api_key="ollama",  # Ollama는 인증 불필요, openai SDK 요구사항
        )

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.LOCAL

    def is_available(self) -> bool:
        try:
            models = self._client.models.list()
            # 지정 모델이 실제로 pull 되어 있는지 확인
            return any(m.id == self._model for m in models.data)
        except Exception:
            return False

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
