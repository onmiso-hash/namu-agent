#!/usr/bin/env python3
"""namu_update.py — NAMU 플러그인 다중호스트 원클릭 업데이트.

이 스크립트는 claude와 agy 호스트 모두를 지원하며,
각 호스트의 플러그인을 자동으로 최신 버전으로 업데이트합니다.
- claude: marketplace 캐시 갱신 후 plugin update 실행
- agy: plugin uninstall 후 소스로부터 재설치(install) -> mcp_config.json 훅 교정(--heal)

업데이트 완료 후 자동으로 namu_setup_statusline.py를 호출하여 상태줄 경로를 갱신합니다.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# namu_setup_statusline 모듈 재사용을 위한 import (같은 scripts 디렉토리)
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import namu_setup_statusline

def _get_version(install_path: str) -> str:
    """설치 경로에서 플러그인 버전을 읽는다.

    claude(marketplace 캐시)와 agy 설치본 모두 package.json이 아니라 plugin.json을
    쓴다(claude 실측 경로: ~/.claude/plugins/cache/namu-marketplace/namu/<버전>/에
    package.json 없음, plugin.json + .claude-plugin/plugin.json만 있음). 호스트 분기
    없이 plugin.json -> .claude-plugin/plugin.json 순서로 폴백한다(agy 설치본은
    plugin.json만 존재).
    """
    if not install_path:
        return "unknown"
    p = Path(install_path)
    for candidate in (p / "plugin.json", p / ".claude-plugin" / "plugin.json"):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8")).get("version", "unknown")
            except Exception:
                pass
    return "unknown"


def _resolve_cli(name: str) -> str:
    """CLI 실행 파일 경로를 해석한다. Windows에서 subprocess.run(["claude", ...]) 등이
    .cmd 심(shim)을 못 찾는 경우가 있어 shutil.which로 절대경로를 우선 사용하고,
    찾지 못하면 기존처럼 이름 그대로 반환한다(PATH 탐색은 subprocess/OS에 위임)."""
    resolved = shutil.which(name)
    return resolved if resolved else name


def update_claude() -> tuple[str, str, str, bool]:
    install_path = namu_setup_statusline._claude_resolve_install_path()
    if not install_path:
        return "skip", "", "", False

    before_version = _get_version(install_path)
    print(f"  - [claude] 업데이트 전 버전: {before_version}")

    claude_cli = _resolve_cli("claude")
    had_failure = False

    print("  - [claude] 마켓플레이스 캐시 갱신 중...")
    r1 = subprocess.run([claude_cli, "plugin", "marketplace", "update", "namu-marketplace"], check=False)
    if r1.returncode != 0:
        had_failure = True
        print(f"  - [claude] 경고: 마켓플레이스 캐시 갱신 실패 (exit {r1.returncode})")

    print("  - [claude] 플러그인 업데이트 중...")
    r2 = subprocess.run([claude_cli, "plugin", "update", "namu@namu-marketplace"], check=False)
    if r2.returncode != 0:
        had_failure = True
        print(f"  - [claude] 경고: 플러그인 업데이트 실패 (exit {r2.returncode})")

    new_install_path = namu_setup_statusline._claude_resolve_install_path()
    after_version = _get_version(new_install_path)
    print(f"  - [claude] 업데이트 후 버전: {after_version}")

    return "updated", before_version, after_version, had_failure


def update_agy() -> tuple[str, str, str, bool]:
    install_path = namu_setup_statusline._agy_resolve_install_path()
    if not install_path:
        return "skip", "", "", False

    before_version = _get_version(install_path)
    print(f"  - [agy] 업데이트 전 버전: {before_version}")

    # agy는 GitHub 원격 저장소에서 플러그인을 가져옵니다.
    plugin_source = "https://github.com/onmiso-hash/namu-agent.git"

    agy_cli = _resolve_cli("agy")
    had_failure = False

    print("  - [agy] 기존 플러그인 제거 중...")
    r1 = subprocess.run([agy_cli, "plugin", "uninstall", "namu"], check=False)
    if r1.returncode != 0:
        had_failure = True
        print(f"  - [agy] 경고: 기존 플러그인 제거 실패 (exit {r1.returncode})")

    print(f"  - [agy] 플러그인 원격 설치 중 ({plugin_source})...")
    r2 = subprocess.run([agy_cli, "plugin", "install", plugin_source], check=False)
    if r2.returncode != 0:
        had_failure = True
        print(f"  - [agy] 경고: 플러그인 원격 설치 실패 (exit {r2.returncode})")

    new_install_path = namu_setup_statusline._agy_resolve_install_path()
    if new_install_path:
        heal_script = Path(new_install_path) / "hooks" / "session_inject.py"
        if heal_script.exists():
            print("  - [agy] mcp_config.json 절대경로 즉시 교정 (--heal) 중...")
            r3 = subprocess.run([sys.executable, str(heal_script), "--heal"], check=False)
            if r3.returncode != 0:
                had_failure = True
                print(f"  - [agy] 경고: --heal 교정 실패 (exit {r3.returncode})")

    after_version = _get_version(new_install_path)
    print(f"  - [agy] 업데이트 후 버전: {after_version}")

    return "updated", before_version, after_version, had_failure


def _summarize(label: str, status: str, before: str, after: str, had_failure: bool) -> str | None:
    """호스트별 최종 요약 한 줄. skip이면 None(호출 측에서 별도 처리)."""
    if status == "skip":
        return None
    if before != after:
        summary = f"[{label}] {before} -> {after} 업데이트됨"
    else:
        summary = f"[{label}] 버전 변화 없음(이미 최신이거나 갱신 실패) — 현재 {before}"
    if had_failure:
        summary += " (일부 명령 실패)"
    return summary


def main(argv: list[str] | None = None) -> int:
    print("NAMU 플러그인 일괄 자동 업데이트 시작 (Claude Code, Antigravity CLI)...")

    c_status, c_before, c_after, c_failed = update_claude()
    if c_status == "skip":
        print("  - [claude] 미설치 — 건너뜁니다.")

    print()

    a_status, a_before, a_after, a_failed = update_agy()
    if a_status == "skip":
        print("  - [agy] 미설치 — 건너뜁니다.")

    if c_status == "skip" and a_status == "skip":
        print("\n[오류] 업데이트할 대상이 없습니다. (Claude Code 또는 Antigravity CLI에 NAMU 플러그인이 미설치)")
        return 1

    print("\n[공통] statusLine 셋업 갱신...")
    setup_script = SCRIPT_DIR / "namu_setup_statusline.py"
    subprocess.run([sys.executable, str(setup_script)], check=False)

    print("\n[요약]")
    c_summary = _summarize("claude", c_status, c_before, c_after, c_failed)
    if c_summary:
        print(f"  - {c_summary}")
    a_summary = _summarize("agy", a_status, a_before, a_after, a_failed)
    if a_summary:
        print(f"  - {a_summary}")

    updated_hosts = []
    if c_status == "updated":
        updated_hosts.append("Claude Code")
    if a_status == "updated":
        updated_hosts.append("Antigravity CLI")

    hosts_str = " 및 ".join(updated_hosts)
    print(f"\n업데이트가 완료되었습니다. 반영하려면 {hosts_str}를 재시작하세요.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
