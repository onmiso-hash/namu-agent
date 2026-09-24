# /// script
# requires-python = ">=3.12"
# dependencies = ["python-dotenv>=1.0.0", "tzdata>=2024.1", "PyYAML>=6.0"]
# ///
"""클라우드 컨테이너 entrypoint 전용 얇은 wrapper (namu-45, docs/remote_mcp_design.md §7-2).

`memory_sync.sync_setup()`을 그대로 호출해 `.namu_sync` 마커·`.gitattributes` union
라인·git remote origin을 wiring한다 — 로직을 새로 짜지 않고 기존 함수를 재사용한다
(지시서 요구사항: "새로 짜지 말고 기존 sync_setup 관련 함수 호출로 처리").

entrypoint.sh가 이미 `git clone`/`git pull`로 `~/.namu`를 원격과 맞춘 뒤 이 스크립트를
부른다. `sync_setup()`은 그 상태에서도 멱등하게 동작한다 — `.git`이 이미 있으면 init을
스킵하고, origin이 이미 clone으로 설정돼 있으면 동일 URL로 set-url(no-op)만 한다.

의존성: `import config as cfg`가 dotenv를, 경고 시각(`cfg.now()`)이 tzdata를,
memo 충돌 자동 병합(`memory_sync._resolve_memo_conflict`)이 PyYAML을 요구한다 —
yaml이 없으면 자동 병합 대신 되돌리기로 떨어져, 두 기기가 메모를 붙이기만 해도
병합이 매번 실패로 남는다. mcp SDK 등 무거운 의존성은 필요 없어 http_server.py와
별도의 얇은 PEP 723 블록을 둔다.

## 무엇을 치명으로 보나 (2026-09)

예전에는 결과 문장에 "실패"가 하나라도 있으면 exit 1이었다. 그래서 GitHub에 잠깐
못 닿기만 해도(fetch/push 실패) entrypoint가 멈추고, 재시작 정책(always)과 맞물려
2026-08-16과 같은 무한 재시작 루프가 됐다(검수 재현 repro_boot_offline.sh —
startup_sync는 원격 불통을 경고로 넘겼는데 바로 다음 단계인 이 스크립트가 죽였다).

지금은 `memory_sync.sync_setup_report()`의 구조화된 칸으로 가른다.
- `fatal`(로컬 wiring 실패: init·원격 등록·마커·커밋 등) → exit 1. 이대로 서버를
  띄우면 기록이 원격으로 갈 길 자체가 없다.
- `network`(fetch·병합·push 실패)만 있으면 → exit 0 + 경고. 경고는 startup_sync와
  같은 `~/.namu/db/startup_sync.json`에 남겨 세션 브리핑·`namu_recall`의 warnings로
  계속 뜨게 하고, 받아오기가 성공하면(sync_pull·startup_pull) 지워진다.
"""
import sys
from pathlib import Path

# namu-plugin/은 이 파일 기준 ../namu-plugin (Dockerfile: /app/deploy/, /app/namu-plugin/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "namu-plugin"))

import memory_sync  # noqa: E402
import startup_sync  # noqa: E402


def main(argv: "list[str] | None" = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 1:
        print("usage: namu_cloud_sync_setup.py <remote_url>", file=sys.stderr)
        return 2

    import config as cfg

    report = memory_sync.sync_setup_report(args[0])
    print(report["text"])
    if report["fatal"]:
        return 1
    home = cfg.NAMU_DATA_ROOT
    if report["network"]:
        reason = " | ".join(report["network"])
        startup_sync.write_status(home, "sync_setup", reason, report["notes"])
        memory_sync._append_sync_log(f"SETUP network-fail(기동 계속) {reason}", home=home)
        print(
            "[namu-cloud-sync-setup] 경고: 원격에 닿지 못했습니다 — 로컬 설정은 끝났으니 "
            "기동을 계속합니다(사유는 ~/.namu/db/startup_sync.json).",
            file=sys.stderr,
        )
    # network가 비었어도 여기서 경고를 지우지 않는다 — 원격에 main이 없어 병합을
    # 건너뛴 경우 등은 "받아오기 성공"이 아니다. 지우는 것은 실제 받아오기의 몫이다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
