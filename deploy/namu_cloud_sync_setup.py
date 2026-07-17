# /// script
# requires-python = ">=3.12"
# dependencies = ["python-dotenv>=1.0.0"]
# ///
"""클라우드 컨테이너 entrypoint 전용 얇은 wrapper (namu-45, docs/remote_mcp_design.md §7-2).

`memory_sync.sync_setup()`을 그대로 호출해 `.namu_sync` 마커·`.gitattributes` union
라인·git remote origin을 wiring한다 — 로직을 새로 짜지 않고 기존 함수를 재사용한다
(지시서 요구사항: "새로 짜지 말고 기존 sync_setup 관련 함수 호출로 처리").

entrypoint.sh가 이미 `git clone`/`git pull`로 `~/.namu`를 원격과 맞춘 뒤 이 스크립트를
부른다. `sync_setup()`은 그 상태에서도 멱등하게 동작한다 — `.git`이 이미 있으면 init을
스킵하고, origin이 이미 clone으로 설정돼 있으면 동일 URL로 set-url(no-op)만 한다.

이 파일 자체는 python-dotenv 하나만 의존한다 — `memory_sync.py`가 stdlib만 쓰지만
`import config as cfg`가 dotenv를 요구하기 때문(config.py 헤더 참조). mcp SDK 등
무거운 의존성은 필요 없어 http_server.py와 별도의 얇은 PEP 723 블록을 둔다.
"""
import sys
from pathlib import Path

# namu-plugin/은 이 파일 기준 ../namu-plugin (Dockerfile: /app/deploy/, /app/namu-plugin/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "namu-plugin"))

import memory_sync  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: namu_cloud_sync_setup.py <remote_url>", file=sys.stderr)
        return 2

    remote_url = sys.argv[1]
    result = memory_sync.sync_setup(remote_url)
    print(result)
    # sync_setup()은 사람이 읽는 노트 문자열을 반환한다(무음 실패 금지 설계) — 그중
    # "실패"가 섞여 있으면 entrypoint가 비정상 종료를 판단할 수 있게 exit code로 알린다.
    if "실패" in result:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
