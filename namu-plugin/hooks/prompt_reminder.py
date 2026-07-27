#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1", "typing-extensions>=4.0"]
# ///
"""UserPromptSubmit 훅 — 상시 주의사항을 사용자 입력마다 다시 올린다(namu-62 ②).

왜 세션 시작 1회로는 부족한가: 규칙이 기억에 **있는데도** 어겨진 사고가 실제로
있었다(2026-07-26). 원인은 "몰라서"가 아니라 **답을 쓰기 직전에 대조하지 않아서**다.
세션 앞머리에 한 번 스친 규칙은 긴 세션 뒤 답을 쓰는 시점에는 화면 밖에 있다.
그래서 규칙이 필요한 바로 그 시점(=사용자가 말을 걸어 답을 쓰기 직전)에 올린다.

무엇을 올리나: `profile.yaml`에서 `상시` 태그가 붙은 사실만. 그릇을 새로 만들지
않는 이유는 이런 규칙이 이미 profile(사실·선호)의 내용이기 때문이고, 태그로 고르는
이유는 profile 전체를 매번 올리면 무거워서 아무도 안 읽기 때문이다. 등록은
`namu_record(bowl='profile', kind='fact', tags=['상시'], ...)` 한 번이면 된다.

어떤 에러가 나도 exit 0 (훅이 입력을 막으면 안 된다).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 매 입력에 붙는 글이라 상한을 둔다 — 길어지면 정작 읽히지 않는다.
_MAX_TOTAL_CHARS = 2000


def _render(facts: list[dict]) -> str | None:
    lines = []
    used = 0
    for fact in facts:
        subject = str(fact.get("subject") or "").strip()
        statement = " ".join(str(fact.get("statement") or "").split())
        if not statement:
            continue
        line = f"- **{subject}** — {statement}" if subject else f"- {statement}"
        if used + len(line) > _MAX_TOTAL_CHARS:
            lines.append("- (이하 생략 — 전체는 namu_search로 조회)")
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return None
    return "## ⚠ 상시 주의 (매 입력 재알림)\n" + "\n".join(lines)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        # stdin은 읽어서 버린다 — 안 읽으면 쓰는 쪽이 파이프에서 막힐 수 있다.
        try:
            sys.stdin.read()
        except Exception:
            pass

        import config as cfg
        import profile

        always_tag = getattr(cfg, "PROFILE_ALWAYS_TAG", "상시")
        facts = [f for f in profile.active() if always_tag in (f.get("tags") or [])]
        md = _render(facts)
        if md is None:
            sys.exit(0)

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": md,
                    }
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
