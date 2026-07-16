"""scripts/namu_update.py 테스트(#42 원클릭 업데이트 자동화).

가상 HOME 격리를 통해 각 호스트(claude, agy)의 설치 여부를 조작하고
서브프로세스 호출(update 명령)이 올바르게 일어나는지 검증한다.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 모듈 로드를 위한 경로 추가
_SCRIPT_DIR = Path(__file__).parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

import namu_update
import namu_setup_statusline

def _write_claude_installed(fake_home: Path, version: str = "0.1.0") -> None:
    path = fake_home / ".claude" / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    install_path = fake_home / "claude_install"
    install_path.mkdir()
    (install_path / "plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    data = {
        "version": 2,
        "plugins": {
            "namu@namu-marketplace": [
                {
                    "scope": "user",
                    "installPath": str(install_path),
                }
            ]
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")

def _write_agy_installed(fake_home: Path, version: str = "0.1.0") -> None:
    path = fake_home / ".gemini" / "config" / "import_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    
    install_path = fake_home / ".gemini" / "config" / "plugins" / "namu"
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (install_path / "hooks").mkdir(parents=True, exist_ok=True)
    (install_path / "hooks" / "session_inject.py").write_text("# stub", encoding="utf-8")
    
    data = {
        "imports": [{"name": "namu", "source": "local", "components": []}]
    }
    path.write_text(json.dumps(data), encoding="utf-8")

def test_update_skip_if_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    
    with patch("subprocess.run") as mock_run:
        exit_code = namu_update.main()
        
    assert exit_code == 1
    # 설치된 호스트가 없으므로 subprocess.run 은 호출되지 않아야 함
    mock_run.assert_not_called()

def test_update_claude_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    _write_claude_installed(tmp_path, "1.0.0")

    # shutil.which를 모킹해 테스트 실행 환경에 claude/agy가 실제로 PATH에 있는지와
    # 무관하게 호출 인자를 결정적으로 검증한다.
    with patch("subprocess.run") as mock_run, patch("namu_update.shutil.which", return_value=None):
        mock_run.return_value.returncode = 0
        exit_code = namu_update.main()

    assert exit_code == 0

    # claude 업데이트 관련 subprocess 호출 2번 + 마지막 setup_statusline 1번
    assert mock_run.call_count == 3
    calls = mock_run.call_args_list
    assert ["claude", "plugin", "marketplace", "update", "namu-marketplace"] == calls[0][0][0]
    assert ["claude", "plugin", "update", "namu@namu-marketplace"] == calls[1][0][0]
    assert "namu_setup_statusline.py" in calls[2][0][0][-1]

    out, _ = capsys.readouterr()
    assert "[claude] 업데이트 전 버전: 1.0.0" in out
    assert "[agy] 미설치" in out
    # 모킹 환경에서는 설치 파일이 실제로 바뀌지 않으므로 before==after -> "버전 변화 없음"
    assert "[claude] 버전 변화 없음(이미 최신이거나 갱신 실패) — 현재 1.0.0" in out

def test_update_agy_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    _write_agy_installed(tmp_path, "2.0.0")

    with patch("subprocess.run") as mock_run, patch("namu_update.shutil.which", return_value=None):
        mock_run.return_value.returncode = 0
        exit_code = namu_update.main()

    assert exit_code == 0

    # agy 업데이트 관련 subprocess 호출 (uninstall, install, heal) 3번 + 마지막 setup_statusline 1번
    assert mock_run.call_count == 4
    calls = mock_run.call_args_list
    assert ["agy", "plugin", "uninstall", "namu"] == calls[0][0][0]
    assert ["agy", "plugin", "install"] == calls[1][0][0][:3]
    assert "--heal" in calls[2][0][0]
    assert "namu_setup_statusline.py" in calls[3][0][0][-1]

    out, _ = capsys.readouterr()
    assert "[agy] 업데이트 전 버전: 2.0.0" in out
    assert "[claude] 미설치" in out
    assert "[agy] 버전 변화 없음(이미 최신이거나 갱신 실패) — 현재 2.0.0" in out

def test_update_both(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    _write_claude_installed(tmp_path, "1.0.0")
    _write_agy_installed(tmp_path, "2.0.0")

    with patch("subprocess.run") as mock_run, patch("namu_update.shutil.which", return_value=None):
        mock_run.return_value.returncode = 0
        exit_code = namu_update.main()

    assert exit_code == 0

    # 총 subprocess 호출:
    # claude(2) + agy(3) + setup_statusline(1) = 6
    assert mock_run.call_count == 6

def test_update_cli_resolved_via_which(tmp_path, monkeypatch, capsys):
    """shutil.which가 절대경로를 찾아주면 그 경로로 CLI를 호출해야 한다(Windows .cmd 대응)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    _write_claude_installed(tmp_path, "1.0.0")

    fake_claude_path = str(tmp_path / "bin" / "claude.cmd")

    def _fake_which(name):
        if name == "claude":
            return fake_claude_path
        return None

    with patch("subprocess.run") as mock_run, patch("namu_update.shutil.which", side_effect=_fake_which):
        mock_run.return_value.returncode = 0
        exit_code = namu_update.main()

    assert exit_code == 0
    calls = mock_run.call_args_list
    assert calls[0][0][0][0] == fake_claude_path
    assert calls[1][0][0][0] == fake_claude_path

def test_get_version_falls_back_to_claude_plugin_subdir(tmp_path):
    """plugin.json이 없고 .claude-plugin/plugin.json만 있는 설치본(claude 실제 마켓플레이스
    캐시 레이아웃과 유사한 경우)도 버전을 읽어야 한다."""
    install_path = tmp_path / "install"
    nested = install_path / ".claude-plugin"
    nested.mkdir(parents=True)
    (nested / "plugin.json").write_text(json.dumps({"version": "3.2.1"}), encoding="utf-8")

    assert namu_update._get_version(str(install_path)) == "3.2.1"
