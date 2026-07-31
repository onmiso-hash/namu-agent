#!/usr/bin/env python3
"""설계서의 칸 배치표를 `config.FIELDS` 선언에서 생성해 끼워 넣는다 (namu-65 후속 ①).

표가 코드와 문서 두 곳에 살면 반드시 갈라진다 — 그리고 갈라진 표를 읽은 AI가 잘못된
그릇에 담은 것이 이번 작업(namu-65)의 발단이었다. 그래서 문서의 표를 손으로 적지 않고
여기서 만들어 표시선(마커) 사이에 끼워 넣는다. 손으로 고치면 `test_field_docs.py`가
실패해 되돌리라고 알려준다.

    python scripts/gen_field_docs.py            # 문서를 갱신한다
    python scripts/gen_field_docs.py --check    # 갱신이 필요한지만 본다(0=최신)
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "namu-plugin"))

import record_input  # noqa: E402

TARGET = REPO_ROOT / "docs" / "memory_schema_v2.md"

BEGIN = "<!-- 자동생성 시작: config.FIELDS — 손으로 고치지 마세요 (scripts/gen_field_docs.py) -->"
END = "<!-- 자동생성 끝 -->"


def render() -> str:
    """표시선을 포함한 생성 구역 전체."""
    return f"{BEGIN}\n\n{record_input.docs_section()}\n\n{END}"


def splice(text: str, block: str) -> str:
    """표시선 사이를 새 내용으로 바꾼다. 표시선이 없으면 어디에 넣을지 알 수 없으므로
    조용히 덧붙이지 않고 멈춘다 — 문서 아무 데나 표가 두 벌 생기는 것이 더 나쁘다."""
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(
            f"{TARGET.name}에서 표시선을 찾지 못했습니다 — 아래 두 줄이 이 순서로 "
            f"있어야 합니다:\n{BEGIN}\n{END}"
        )
    return text[:start] + block + text[end + len(END):]


def main(argv) -> int:
    check_only = "--check" in argv
    current = TARGET.read_text(encoding="utf-8")
    updated = splice(current, render())

    if current == updated:
        print(f"OK: {TARGET.relative_to(REPO_ROOT)} 최신입니다.")
        return 0
    if check_only:
        print(
            f"갱신 필요: {TARGET.relative_to(REPO_ROOT)} — "
            "`python scripts/gen_field_docs.py`를 실행하세요.",
            file=sys.stderr,
        )
        return 1
    TARGET.write_text(updated, encoding="utf-8")
    print(f"갱신함: {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
