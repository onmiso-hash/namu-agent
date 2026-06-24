import argparse
import sys

from adapters.base import Message, Role
from core.orchestrator import Orchestrator

_REPL_BANNER = (
    "╔══════════════════════════════════╗\n"
    "║  NAMU Agent  —  REPL 모드        ║\n"
    "║  종료: quit / exit / Ctrl+C      ║\n"
    "╚══════════════════════════════════╝"
)


def run_single(orc: Orchestrator, task: str, *, system: str | None, approve: bool) -> None:
    try:
        result = orc.run(task, system=system, require_approval=approve)
        print(f"\n{result}")
    except RuntimeError as e:
        print(f"\n[오류] {e}", file=sys.stderr)
        sys.exit(1)


def run_repl(orc: Orchestrator, *, system: str | None, approve: bool) -> None:
    print(_REPL_BANNER)

    adapter = orc.select_adapter()
    if adapter is None:
        print("[오류] 사용 가능한 어댑터가 없습니다. API 키를 확인하세요.", file=sys.stderr)
        sys.exit(1)
    print(f"어댑터: {adapter}\n")

    history: list[Message] = []

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("종료합니다.")
            break

        history.append(Message(role=Role.USER, content=user_input))

        try:
            result = orc.run(
                user_input,
                system=system,
                messages=history,
                require_approval=approve,
            )
        except RuntimeError as e:
            print(f"[오류] {e}", file=sys.stderr)
            history.pop()  # 취소된 요청은 히스토리에서 제거
            continue

        print(f"\nAI> {result}\n")
        history.append(Message(role=Role.ASSISTANT, content=result))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="namu-agent",
        description="NAMU Agent — 벤더 독립 AI CLI",
    )
    parser.add_argument("task", nargs="?", help="실행할 작업 (생략 시 REPL 모드 진입)")
    parser.add_argument("--no-approve", action="store_true", help="승인 게이트 비활성화")
    parser.add_argument("--system", metavar="PROMPT", help="시스템 프롬프트")
    args = parser.parse_args()

    orc = Orchestrator()
    approve = not args.no_approve

    if args.task:
        run_single(orc, args.task, system=args.system, approve=approve)
    else:
        run_repl(orc, system=args.system, approve=approve)


if __name__ == "__main__":
    main()
