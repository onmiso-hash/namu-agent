import uuid
from datetime import datetime
from typing import Any

import config as cfg
from adapters.base import AIAdapter, Message
from adapters.claude_api import ClaudeAPIAdapter
from adapters.claude_subscription import ClaudeSubscriptionAdapter
from adapters.gemini_api import GeminiAPIAdapter
from adapters.gpt_api import GPTAPIAdapter
from adapters.ollama import OllamaAdapter

_REGISTRY: dict[str, type[AIAdapter]] = {
    "ollama": OllamaAdapter,
    "claude-subscription": ClaudeSubscriptionAdapter,
    "claude-api": ClaudeAPIAdapter,
    "gpt-api": GPTAPIAdapter,
    "gemini-api": GeminiAPIAdapter,
}


class Orchestrator:
    """NAMU 오케스트레이터.

    어댑터 선택 → 승인 게이트 → 실행 → 기록 흐름을 담당한다.
    """

    def __init__(self) -> None:
        self._adapters: list[AIAdapter] = []
        self._load_adapters()

    # ------------------------------------------------------------------ #
    # 공개 인터페이스                                                       #
    # ------------------------------------------------------------------ #

    def run(
        self,
        task: str,
        *,
        system: str | None = None,
        messages: list[Message] | None = None,
        require_approval: bool = True,
        **kwargs: Any,
    ) -> str:
        """작업을 실행하고 결과 문자열을 반환한다.

        Args:
            task: 작업 설명 (messages가 없을 때 프롬프트로도 사용)
            system: 시스템 프롬프트
            messages: 멀티턴 대화 메시지 (있으면 task는 기록용으로만 쓰임)
            require_approval: True면 실행 전 사용자 승인 요청
        """
        adapter = self.select_adapter()
        if adapter is None:
            raise RuntimeError(
                "사용 가능한 어댑터가 없습니다. "
                "API 키를 확인하거나 Ollama를 실행하세요."
            )

        if require_approval and not self._approve(adapter, task):
            raise RuntimeError("사용자가 작업을 취소했습니다.")

        task_id = self._new_task_id()
        started_at = datetime.now()

        try:
            if messages:
                result = adapter.chat(messages, system=system, **kwargs)
            else:
                result = adapter.generate(task, system=system, **kwargs)
        except Exception as exc:
            self._write_task_files(task_id, task, str(exc), adapter, started_at, success=False)
            self._append_learning(task, str(exc), adapter, started_at, success=False)
            raise

        self._write_task_files(task_id, task, result.content, adapter, started_at, success=True)
        self._append_learning(task, result.content, adapter, started_at, success=True)
        return result.content

    def select_adapter(self) -> AIAdapter | None:
        """우선순위 순으로 사용 가능한 첫 번째 어댑터를 반환한다."""
        for adapter in self._adapters:
            if adapter.is_available():
                return adapter
        return None

    def list_adapters(self) -> list[AIAdapter]:
        """등록된 어댑터 목록을 반환한다."""
        return list(self._adapters)

    # ------------------------------------------------------------------ #
    # 내부 메서드                                                           #
    # ------------------------------------------------------------------ #

    def _load_adapters(self) -> None:
        for name in cfg.ENABLED_ADAPTERS:
            cls = _REGISTRY.get(name)
            if cls is None:
                continue
            self._adapters.append(cls())
        self._adapters.sort(key=lambda a: a.priority)

    def _approve(self, adapter: AIAdapter, task: str) -> bool:
        preview = task[:120] + ("..." if len(task) > 120 else "")
        print(f"\n[승인 게이트]")
        print(f"  어댑터 : {adapter}")
        print(f"  작업   : {preview}")
        try:
            answer = input("  계속할까요? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes")

    def _new_task_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{ts}_{uuid.uuid4().hex[:6]}"

    def _write_task_files(
        self,
        task_id: str,
        task: str,
        output: str,
        adapter: AIAdapter,
        started_at: datetime,
        *,
        success: bool,
    ) -> None:
        task_dir = cfg.TASKS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        finished_at = datetime.now()
        elapsed = (finished_at - started_at).total_seconds()

        (task_dir / "task.md").write_text(f"# Task\n\n{task}\n", encoding="utf-8")

        status = "SUCCESS" if success else "FAILURE"
        (task_dir / "result.md").write_text(
            f"# Result — {status}\n\n{output}\n", encoding="utf-8"
        )

        (task_dir / "log.md").write_text(
            f"# Log\n\n"
            f"- task_id : {task_id}\n"
            f"- adapter : {adapter}\n"
            f"- started : {started_at.isoformat()}\n"
            f"- finished: {finished_at.isoformat()}\n"
            f"- elapsed : {elapsed:.2f}s\n"
            f"- success : {success}\n",
            encoding="utf-8",
        )

    def _append_learning(
        self,
        task: str,
        output: str,
        adapter: AIAdapter,
        started_at: datetime,
        *,
        success: bool,
    ) -> None:
        date_str = started_at.strftime("%Y-%m-%d")
        label = "성공" if success else "실패"
        section_marker = (
            "## 성공 패턴 (Success Patterns)"
            if success
            else "## 실패 패턴 (Failure Patterns)"
        )

        task_preview = task[:200] + ("..." if len(task) > 200 else "")
        output_preview = output[:200] + ("..." if len(output) > 200 else "")

        entry = (
            f"\n### [{date_str}] {adapter.name} {label}\n\n"
            f"**작업:** {task_preview}\n\n"
            f"**결과:** {output_preview}\n\n"
            f"**판단:** 어댑터 `{adapter.name}` (priority={adapter.priority}) 자동 선택\n"
        )

        content = cfg.LEARNINGS_PATH.read_text(encoding="utf-8")

        pos = content.find(section_marker)
        if pos == -1:
            content += entry
        else:
            # 다음 ## 섹션 직전에 삽입
            next_pos = content.find("\n## ", pos + 1)
            insert_at = next_pos if next_pos != -1 else len(content)
            content = content[:insert_at] + entry + content[insert_at:]

        # append-only 원칙: 기존 내용을 삭제하지 않고 덧붙임
        cfg.LEARNINGS_PATH.write_text(content, encoding="utf-8")
