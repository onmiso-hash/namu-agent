#!/usr/bin/env python3
"""namu_setup_statusline — statusLine 원클릭 셋업(#36, agy 다중 호스트 확장 #39).

⚠️ 이 파일은 오직 `namu-plugin/scripts/`에만 존재한다(동봉 사본 관례와 달리 repo 루트
`scripts/`에는 짝이 없다) — `/namu:statusline-setup` 스킬이 설치형·개발형 양쪽에서
플러그인 동봉 경로(`${CLAUDE_PLUGIN_ROOT}/scripts/` 또는 이 repo의
`namu-plugin/scripts/`)를 그대로 가리켜 호출하기 때문에 별도 사본이 필요 없다.

동작 개요(호스트 공통 정책 + 호스트별 어댑터):
1. 각 호스트의 등록부에서 NAMU 플러그인 설치 경로를 찾는다.
   - claude: `~/.claude/plugins/installed_plugins.json`(v2 스키마)에서
     `<이름>@<마켓플레이스>` 키 중 이름이 `namu`인 항목을 찾아 installPath를 얻는다
     (여러 개면 scope=="user" 우선).
   - agy: `~/.gemini/config/import_manifest.json`의 `imports`에 name=="namu" 항목이
     있으면 고정 관례 경로 `~/.gemini/config/plugins/namu/`를 installPath로 쓴다
     (installPath 필드 자체는 없음).
2. installPath 아래 `scripts/namu_statusline.py`가 실물로 존재하는지 확인한다(호스트 공통).
3. OS별 커맨드를 조립한다 — Windows는 `python -X utf8 <경로>`, 그 외는 `python3 <경로>`.
   경로 구분자는 Windows에서도 슬래시(`/`)로 정규화한다(호스트 공통).
4. 호스트별 settings 파일을 읽어(없으면 `{}`) `statusLine` 키만 병합한다.
   - claude: `~/.claude/settings.json`, 스키마 `{"type":"command","command":..,"padding":0}`
   - agy: `~/.gemini/antigravity-cli/settings.json`, 스키마
     `{"type":"","command":..,"enabled":true}`
   - 기존 statusLine이 없으면 신규 설정.
   - 기존 statusLine이 NAMU 것(`namu_statusline.py` 포함)이면 자동 갱신(이미 동일하면
     변경 없음으로 조용히 종료).
   - 기존 statusLine이 타 설정이면 기본 거부(exit≠0) — `--force`가 있어야 교체한다.
5. 실제로 쓰기가 일어나는 경우에만, 쓰기 전 settings 파일을 타임스탬프 백업한다
   (해당 settings 파일 옆에 `<파일명>.bak.<timestamp>`로 생성).

main()은 설치가 감지된 호스트를 전부 자동으로 셋업한다(claude만 설치돼 있으면 claude만,
agy까지 설치돼 있으면 둘 다). 어느 호스트도 설치돼 있지 않으면 오류로 종료한다.

모든 경로는 `Path.home()` 기준으로 계산한다(테스트에서 HOME/USERPROFILE로 격리 가능해야
하므로 하드코딩 금지 — namu_statusline.py의 홈 격리 관례와 동일).
"""
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, NamedTuple, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PLUGIN_SHORT_NAME = "namu"
STATUSLINE_MARKER = "namu_statusline.py"


# ---------------------------------------------------------------------------
# 호스트 어댑터 — claude
# ---------------------------------------------------------------------------

def _claude_installed_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def _claude_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _claude_resolve_install_path() -> Optional[str]:
    """installed_plugins.json(v2 스키마)에서 namu 플러그인의 installPath를 찾는다.

    키 형식은 `<이름>@<마켓플레이스>` — 이름이 `namu`인 첫 키를 찾는다(마켓플레이스명은
    사용자마다 다를 수 있음). 값은 항목 리스트이며 여러 개면 scope=="user" 우선, 없으면
    첫 항목을 쓴다. 파일이 없거나 namu 항목이 없으면 None.
    """
    path = _claude_installed_plugins_path()
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


def _claude_build_statusline(command: str) -> dict:
    return {"type": "command", "command": command, "padding": 0}


# ---------------------------------------------------------------------------
# 호스트 어댑터 — agy(Antigravity CLI)
# ---------------------------------------------------------------------------

def _agy_import_manifest_path() -> Path:
    return Path.home() / ".gemini" / "config" / "import_manifest.json"


def _agy_settings_path() -> Path:
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def _agy_resolve_install_path() -> Optional[str]:
    """import_manifest.json의 imports에서 name=="namu" 항목 존재 여부만 확인한다.

    agy는 installPath 필드가 없으므로, imports에 namu가 있으면 고정 관례 경로
    `~/.gemini/config/plugins/namu/`(버전 하위폴더 없음)를 그대로 installPath로 쓴다.
    파일이 없거나 파싱 실패, namu 항목이 없으면 None.
    """
    path = _agy_import_manifest_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    imports = data.get("imports")
    if not isinstance(imports, list):
        return None

    found = any(
        isinstance(entry, dict) and entry.get("name") == PLUGIN_SHORT_NAME
        for entry in imports
    )
    if not found:
        return None

    return str(Path.home() / ".gemini" / "config" / "plugins" / "namu")


def _agy_build_statusline(command: str) -> dict:
    return {"type": "", "command": command, "enabled": True}


# ---------------------------------------------------------------------------
# 호스트 테이블
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Host:
    label: str  # 출력 라벨(예: "claude", "agy")
    restart_name: str  # 재시작 안내 문구에 쓰는 표시명(예: "Claude Code", "agy")
    registry_path: Callable[[], Path]  # 미설치 안내에 쓰는 등록부 경로
    resolve_install_path: Callable[[], Optional[str]]
    settings_path: Callable[[], Path]
    build_statusline: Callable[[str], dict]


HOSTS = [
    Host(
        label="claude",
        restart_name="Claude Code",
        registry_path=_claude_installed_plugins_path,
        resolve_install_path=_claude_resolve_install_path,
        settings_path=_claude_settings_path,
        build_statusline=_claude_build_statusline,
    ),
    Host(
        label="agy",
        restart_name="agy",
        registry_path=_agy_import_manifest_path,
        resolve_install_path=_agy_resolve_install_path,
        settings_path=_agy_settings_path,
        build_statusline=_agy_build_statusline,
    ),
]


# ---------------------------------------------------------------------------
# 공통 코어(호스트 무관)
# ---------------------------------------------------------------------------

def build_command(install_path: str) -> Optional[str]:
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


def load_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def backup_settings(settings_path: Path) -> Optional[Path]:
    if not settings_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = settings_path.with_name(f"{settings_path.name}.bak.{stamp}")
    backup_path.write_bytes(settings_path.read_bytes())
    return backup_path


def write_settings(settings_path: Path, settings: dict) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class HostResult(NamedTuple):
    status: str  # "skip" | "fresh" | "updated" | "noop" | "reject" | "broken"
    message: str
    ok: bool  # False면 전체 exit code를 non-zero로 만드는 실패


def setup_one(host: Host, force: bool) -> HostResult:
    """한 호스트에 대해 statusLine 셋업을 수행한다.

    installPath 해석 실패(미설치)는 오류가 아니라 skip으로 취급한다.
    """
    install_path = host.resolve_install_path()
    if install_path is None:
        return HostResult("skip", f"[{host.label}] 미설치 — 건너뜁니다.", True)

    command = build_command(install_path)
    if command is None:
        expected = Path(install_path) / "scripts" / STATUSLINE_MARKER
        return HostResult(
            "broken",
            f"[{host.label}] [오류] statusline 스크립트를 찾지 못했습니다: {expected}\n"
            f"  {host.restart_name}의 namu 플러그인이 최신이 아닐 수 있습니다 — "
            f"{host.restart_name}에서 namu 플러그인을 업데이트한 뒤 다시 실행하세요.\n"
            "  (업데이트 후에도 같은 오류면 설치가 손상된 것일 수 있으니 재설치하세요.)",
            False,
        )

    settings_path = host.settings_path()
    settings = load_settings(settings_path)
    existing = settings.get("statusLine")

    if isinstance(existing, dict) and STATUSLINE_MARKER not in (
        existing.get("command") or ""
    ):
        if not force:
            return HostResult(
                "reject",
                f"[{host.label}] [거부] 이미 다른 statusLine 설정이 있습니다:\n"
                f"  {json.dumps(existing, ensure_ascii=False)}\n"
                "NAMU statusLine으로 덮어쓰려면 --force 옵션을 붙여 다시 실행하세요.",
                False,
            )
        # --force: 교체 진행 (아래 공통 경로)

    new_statusline = host.build_statusline(command)

    if isinstance(existing, dict) and existing == new_statusline:
        return HostResult(
            "noop",
            f"[{host.label}] [변경 없음] statusLine이 이미 최신 상태입니다: {command}",
            True,
        )

    old_command = existing.get("command") if isinstance(existing, dict) else None

    backup_path = backup_settings(settings_path)

    settings["statusLine"] = new_statusline
    write_settings(settings_path, settings)

    lines = []
    if old_command:
        lines.append(f"[{host.label}] [갱신] statusLine 경로를 최신으로 교체했습니다.")
        lines.append(f"  이전: {old_command}")
        lines.append(f"  이후: {command}")
        status = "updated"
    else:
        lines.append(f"[{host.label}] [신규] statusLine을 새로 설정했습니다.")
        lines.append(f"  {command}")
        status = "fresh"

    if backup_path is not None:
        lines.append(f"  백업: {backup_path}")

    return HostResult(status, "\n".join(lines), True)


def main(argv: list[str]) -> int:
    force = "--force" in argv

    results = [(host, setup_one(host, force)) for host in HOSTS]
    attempted = [(host, result) for host, result in results if result.status != "skip"]

    if not attempted:
        registries = "\n".join(f"  - {host.label}: {host.registry_path()}" for host in HOSTS)
        print(
            "[오류] NAMU 플러그인이 설치돼 있지 않습니다 — 아래 경로 어디에서도 'namu' "
            "항목을 찾지 못했습니다.\n"
            f"{registries}\n"
            "먼저 Claude Code 또는 agy(Antigravity CLI)에 NAMU 플러그인을 설치한 뒤 "
            "다시 실행하세요."
        )
        return 1

    exit_code = 0
    changed_hosts: list[Host] = []
    for host, result in results:
        if result.status == "skip":
            continue
        print(result.message)
        if not result.ok:
            exit_code = 1
        if result.status in ("fresh", "updated"):
            changed_hosts.append(host)

    if changed_hosts:
        names = "/".join(host.restart_name for host in changed_hosts)
        print(f"{names}를 재시작하면 반영됩니다.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
