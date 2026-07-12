"""scripts/namu_setup_statusline.py 테스트(#36 statusLine 원클릭 셋업).

Windows Path.home()(=os.path.expanduser)는 HOME보다 USERPROFILE을 우선 참조한다 —
namu_statusline.py 테스트 관례와 동일하게 HOME과 USERPROFILE을 둘 다 가짜 홈으로
격리해야 이 플랫폼에서도 실제 ~/.claude를 절대 건드리지 않는다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# namu_setup_statusline.py는 오직 namu-plugin/scripts/에만 존재한다(repo 루트 scripts/에는
# 짝이 없음 — 스크립트 자체 docstring 참고). 다른 statusline 계열 테스트가 참조하는
# repo 루트 scripts/의 "원본" 관례와 다르다는 점에 주의.
_SCRIPT = Path(__file__).parent / "scripts" / "namu_setup_statusline.py"


def _installed_plugins_json(install_path: Path, scope: str = "user") -> dict:
    return {
        "version": 2,
        "plugins": {
            "namu@namu-marketplace": [
                {
                    "scope": scope,
                    "installPath": str(install_path),
                    "version": "0.1.16",
                }
            ]
        },
    }


def _make_install(tmp_path: Path, subdir: str = "install") -> Path:
    install_path = tmp_path / subdir
    (install_path / "scripts").mkdir(parents=True)
    (install_path / "scripts" / "namu_statusline.py").write_text(
        "# stub\n", encoding="utf-8"
    )
    return install_path


def _expected_command(install_path: Path) -> str:
    normalized = str(install_path / "scripts" / "namu_statusline.py").replace("\\", "/")
    if os.name == "nt":
        return f"python -X utf8 {normalized}"
    return f"python3 {normalized}"


def _run_cli(fake_home: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *(args or [])],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )


def _write_installed_plugins(fake_home: Path, data: dict) -> None:
    path = fake_home / ".claude" / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _settings_path(fake_home: Path) -> Path:
    return fake_home / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# 1. 정상 신규 설정 (settings.json 없음)
# ---------------------------------------------------------------------------

def test_fresh_setup_creates_statusline(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = _make_install(tmp_path)
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    result = _run_cli(fake_home)

    assert result.returncode == 0, result.stdout + result.stderr
    settings = json.loads(_settings_path(fake_home).read_text(encoding="utf-8"))
    assert settings["statusLine"] == {
        "type": "command",
        "command": _expected_command(install_path),
        "padding": 0,
    }


# ---------------------------------------------------------------------------
# 2. 다른 키 보존
# ---------------------------------------------------------------------------

def test_preserves_other_settings_keys(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = _make_install(tmp_path)
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    settings_path = _settings_path(fake_home)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"model": "opus", "theme": "dark"}), encoding="utf-8"
    )

    result = _run_cli(fake_home)

    assert result.returncode == 0, result.stdout + result.stderr
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["model"] == "opus"
    assert settings["theme"] == "dark"
    assert settings["statusLine"]["command"] == _expected_command(install_path)


# ---------------------------------------------------------------------------
# 3. NAMU 구버전 경로 -> 자동 갱신 + 백업
# ---------------------------------------------------------------------------

def test_updates_stale_namu_path_and_backs_up(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    old_install = _make_install(tmp_path, "old_install")
    new_install = _make_install(tmp_path, "new_install")
    _write_installed_plugins(fake_home, _installed_plugins_json(new_install))

    settings_path = _settings_path(fake_home)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    old_command = _expected_command(old_install)
    settings_path.write_text(
        json.dumps(
            {"statusLine": {"type": "command", "command": old_command, "padding": 0}}
        ),
        encoding="utf-8",
    )

    result = _run_cli(fake_home)

    assert result.returncode == 0, result.stdout + result.stderr
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == _expected_command(new_install)

    backups = list(settings_path.parent.glob("settings.json.bak.*"))
    assert len(backups) == 1
    backed_up = json.loads(backups[0].read_text(encoding="utf-8"))
    assert backed_up["statusLine"]["command"] == old_command


# ---------------------------------------------------------------------------
# 4. 타 statusLine -> 기본 거부
# ---------------------------------------------------------------------------

def test_rejects_foreign_statusline_by_default(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = _make_install(tmp_path)
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    settings_path = _settings_path(fake_home)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    foreign = {"type": "command", "command": "python3 /other/tool.py", "padding": 0}
    original_content = json.dumps({"statusLine": foreign})
    settings_path.write_text(original_content, encoding="utf-8")

    result = _run_cli(fake_home)

    assert result.returncode != 0
    assert "다른 statusLine" in result.stdout
    assert settings_path.read_text(encoding="utf-8") == original_content
    assert not list(settings_path.parent.glob("settings.json.bak.*"))


# ---------------------------------------------------------------------------
# 5. 타 statusLine + --force -> 교체 + 백업
# ---------------------------------------------------------------------------

def test_force_replaces_foreign_statusline(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = _make_install(tmp_path)
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    settings_path = _settings_path(fake_home)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    foreign = {"type": "command", "command": "python3 /other/tool.py", "padding": 0}
    settings_path.write_text(json.dumps({"statusLine": foreign}), encoding="utf-8")

    result = _run_cli(fake_home, ["--force"])

    assert result.returncode == 0, result.stdout + result.stderr
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == _expected_command(install_path)

    backups = list(settings_path.parent.glob("settings.json.bak.*"))
    assert len(backups) == 1


# ---------------------------------------------------------------------------
# 6. installed_plugins.json 없음/namu 항목 없음 -> 안내 후 exit≠0
# ---------------------------------------------------------------------------

def test_missing_installed_plugins_file_errors(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()

    result = _run_cli(fake_home)

    assert result.returncode != 0
    assert "설치돼 있지 않습니다" in result.stdout


def test_missing_namu_entry_errors(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_installed_plugins(
        fake_home,
        {"version": 2, "plugins": {"other@marketplace": [{"scope": "user", "installPath": "/x"}]}},
    )

    result = _run_cli(fake_home)

    assert result.returncode != 0
    assert "설치돼 있지 않습니다" in result.stdout


# ---------------------------------------------------------------------------
# 7. 이미 최신 경로와 동일 -> 변경 없음(백업도 안 만듦)
# ---------------------------------------------------------------------------

def test_already_up_to_date_is_noop(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = _make_install(tmp_path)
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    settings_path = _settings_path(fake_home)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    current = {
        "type": "command",
        "command": _expected_command(install_path),
        "padding": 0,
    }
    original_content = json.dumps({"statusLine": current, "model": "opus"})
    settings_path.write_text(original_content, encoding="utf-8")

    result = _run_cli(fake_home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "변경 없음" in result.stdout
    assert settings_path.read_text(encoding="utf-8") == original_content
    assert not list(settings_path.parent.glob("settings.json.bak.*"))


# ---------------------------------------------------------------------------
# 실물 statusline 스크립트 없으면 오류
# ---------------------------------------------------------------------------

def test_missing_statusline_script_in_installpath_errors(tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_path = tmp_path / "broken_install"
    install_path.mkdir()
    _write_installed_plugins(fake_home, _installed_plugins_json(install_path))

    result = _run_cli(fake_home)

    assert result.returncode != 0
    assert "찾지 못했습니다" in result.stdout


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
