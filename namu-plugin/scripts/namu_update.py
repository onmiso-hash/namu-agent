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

def _get_version(install_path: str, is_claude: bool) -> str:
    if not install_path:
        return "unknown"
    p = Path(install_path)
    if is_claude:
        meta = p / "package.json"
    else:
        meta = p / "plugin.json"
        
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8")).get("version", "unknown")
        except Exception:
            pass
    return "unknown"

def update_claude() -> tuple[str, str, str]:
    install_path = namu_setup_statusline._claude_resolve_install_path()
    if not install_path:
        return "skip", "", ""
        
    before_version = _get_version(install_path, True)
    print(f"  - [claude] 업데이트 전 버전: {before_version}")
    
    print("  - [claude] 마켓플레이스 캐시 갱신 중...")
    subprocess.run(["claude", "plugin", "marketplace", "update", "namu-marketplace"], check=False)
    
    print("  - [claude] 플러그인 업데이트 중...")
    subprocess.run(["claude", "plugin", "update", "namu@namu-marketplace"], check=False)
    
    new_install_path = namu_setup_statusline._claude_resolve_install_path()
    after_version = _get_version(new_install_path, True)
    print(f"  - [claude] 업데이트 후 버전: {after_version}")
    
    return "updated", before_version, after_version

def update_agy() -> tuple[str, str, str]:
    install_path = namu_setup_statusline._agy_resolve_install_path()
    if not install_path:
        return "skip", "", ""
        
    before_version = _get_version(install_path, False)
    print(f"  - [agy] 업데이트 전 버전: {before_version}")
    
    # agy는 GitHub 원격 저장소에서 플러그인을 가져옵니다.
    plugin_source = "https://github.com/onmiso-hash/namu-agent.git"
    
    print("  - [agy] 기존 플러그인 제거 중...")
    subprocess.run(["agy", "plugin", "uninstall", "namu"], check=False)
    
    print(f"  - [agy] 플러그인 원격 설치 중 ({plugin_source})...")
    subprocess.run(["agy", "plugin", "install", plugin_source], check=False)
    
    new_install_path = namu_setup_statusline._agy_resolve_install_path()
    if new_install_path:
        heal_script = Path(new_install_path) / "hooks" / "session_inject.py"
        if heal_script.exists():
            print("  - [agy] mcp_config.json 절대경로 즉시 교정 (--heal) 중...")
            subprocess.run([sys.executable, str(heal_script), "--heal"], check=False)
            
    after_version = _get_version(new_install_path, False)
    print(f"  - [agy] 업데이트 후 버전: {after_version}")
    
    return "updated", before_version, after_version

def main(argv: list[str] | None = None) -> int:
    print("NAMU 플러그인 일괄 자동 업데이트 시작 (Claude Code, Antigravity CLI)...")
    
    c_status, c_before, c_after = update_claude()
    if c_status == "skip":
        print("  - [claude] 미설치 — 건너뜁니다.")
        
    print()
        
    a_status, a_before, a_after = update_agy()
    if a_status == "skip":
        print("  - [agy] 미설치 — 건너뜁니다.")
        
    if c_status == "skip" and a_status == "skip":
        print("\n[오류] 업데이트할 대상이 없습니다. (Claude Code 또는 Antigravity CLI에 NAMU 플러그인이 미설치)")
        return 1
        
    print("\n[공통] statusLine 셋업 갱신...")
    setup_script = SCRIPT_DIR / "namu_setup_statusline.py"
    subprocess.run([sys.executable, str(setup_script)], check=False)
    
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
