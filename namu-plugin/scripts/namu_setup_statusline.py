#!/usr/bin/env python3
"""namu_setup_statusline — statusLine 원클릭 셋업(#36).

⚠️ 이 파일은 오직 `namu-plugin/scripts/`에만 존재한다(동봉 사본 관례와 달리 repo 루트
`scripts/`에는 짝이 없다) — `/namu:statusline-setup` 스킬이 설치형·개발형 양쪽에서
플러그인 동봉 경로(`${CLAUDE_PLUGIN_ROOT}/scripts/` 또는 이 repo의
`namu-plugin/scripts/`)를 그대로 가리켜 호출하기 때문에 별도 사본이 필요 없다.

동작 개요:
1. `~/.claude/plugins/installed_plugins.json`(v2 스키마)에서 `<이름>@<마켓플레이스>` 키 중
   이름이 `namu`인 항목을 찾아 installPath를 얻는다(여러 개면 scope=="user" 우선).
2. installPath 아래 `scripts/namu_statusline.py`가 실물로 존재하는지 확인한다.
3. OS별 커맨드를 조립한다 — Windows는 `python -X utf8 <경로>`, 그 외는 `python3 <경로>`.
   경로 구분자는 Windows에서도 슬래시(`/`)로 정규화한다(현 정답지 형식과 동일).
4. `~/.claude/settings.json`을 읽어(없으면 `{}`) `statusLine` 키만 병합한다.
   - 기존 statusLine이 없으면 신규 설정.
   - 기존 statusLine이 NAMU 것(`namu_statusline.py` 포함)이면 자동 갱신(이미 동일하면
     변경 없음으로 조용히 종료).
   - 기존 statusLine이 타 설정이면 기본 거부(exit≠0) — `--force`가 있어야 교체한다.
5. 실제로 쓰기가 일어나는 경우에만, 쓰기 전 settings.json을 타임스탬프 백업한다.

모든 경로는 `Path.home()` 기준으로 계산한다(테스트에서 HOME/USERPROFILE로 격리 가능해야
하므로 하드코딩 금지 — namu_statusline.py의 홈 격리 관례와 동일).
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PLUGIN_SHORT_NAME = "namu"
STATUSLINE_MARKER = "namu_statusline.py"


def _installed_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def find_install_path() -> str | None:
    """installed_plugins.json(v2 스키마)에서 namu 플러그인의 installPath를 찾는다.

    키 형식은 `<이름>@<마켓플레이스>` — 이름이 `namu`인 첫 키를 찾는다(마켓플레이스명은
    사용자마다 다를 수 있음). 값은 항목 리스트이며 여러 개면 scope=="user" 우선, 없으면
    첫 항목을 쓴다. 파일이 없거나 namu 항목이 없으면 None.
    """
    path = _installed_plugins_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    plugins = data.get("plugins") or {}
    entries = None
    for key, value in plugins.items():
        name = key.split("@", 1)[0]
        if name == PLUGIN_SHORT_NAME:
            entries = value
            break

    if not entries:
        return None

    chosen = None
    for entry in entries:
        if entry.get("scope") == "user":
            chosen = entry
            break
    if chosen is None:
        chosen = entries[0]

    return chosen.get("installPath")


def build_command(install_path: str) -> str | None:
    """installPath 아래 scripts/namu_statusline.py 실존을 확인하고 실행 커맨드를 조립한다.

    파일이 없으면 None(호출측에서 오류 안내).
    """
    statusline_path = Path(install_path) / "scripts" / STATUSLINE_MARKER
    if not statusline_path.exists():
        return None

    # Windows에서도 슬래시(/)로 정규화 — 현 정답지 형식과 동일.
    normalized = str(statusline_path).replace("\\", "/")

    if os.name == "nt":
        return f"python -X utf8 {normalized}"
    return f"python3 {normalized}"


def load_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def backup_settings() -> Path | None:
    path = _settings_path()
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"settings.json.bak.{stamp}")
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def write_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str]) -> int:
    force = "--force" in argv

    install_path = find_install_path()
    if install_path is None:
        print(
            "[오류] NAMU 플러그인이 설치돼 있지 않습니다 — "
            f"{_installed_plugins_path()}에서 'namu' 항목을 찾지 못했습니다.\n"
            "먼저 Claude Code에 NAMU 플러그인을 설치한 뒤 다시 실행하세요."
        )
        return 1

    command = build_command(install_path)
    if command is None:
        expected = Path(install_path) / "scripts" / STATUSLINE_MARKER
        print(
            f"[오류] 설치본에서 statusline 스크립트를 찾지 못했습니다: {expected}\n"
            "플러그인 설치가 손상됐을 수 있습니다 — 재설치 후 다시 시도하세요."
        )
        return 1

    settings = load_settings()
    existing = settings.get("statusLine")

    if isinstance(existing, dict) and STATUSLINE_MARKER not in (
        existing.get("command") or ""
    ):
        if not force:
            print(
                "[거부] 이미 다른 statusLine 설정이 있습니다:\n"
                f"  {json.dumps(existing, ensure_ascii=False)}\n"
                "NAMU statusLine으로 덮어쓰려면 --force 옵션을 붙여 다시 실행하세요."
            )
            return 1
        # --force: 교체 진행 (아래 공통 경로)

    new_statusline = {"type": "command", "command": command, "padding": 0}

    if isinstance(existing, dict) and existing == new_statusline:
        print(f"[변경 없음] statusLine이 이미 최신 상태입니다: {command}")
        return 0

    old_command = existing.get("command") if isinstance(existing, dict) else None

    backup_path = backup_settings()

    settings["statusLine"] = new_statusline
    write_settings(settings)

    if old_command:
        print("[갱신] statusLine 경로를 최신으로 교체했습니다.")
        print(f"  이전: {old_command}")
        print(f"  이후: {command}")
    else:
        print("[신규] statusLine을 새로 설정했습니다.")
        print(f"  {command}")

    if backup_path is not None:
        print(f"백업: {backup_path}")

    print("Claude Code를 재시작하면 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
