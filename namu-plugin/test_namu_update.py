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
    monkeypatch.delenv("GROK_HOME", raising=False)
    
    with patch("subprocess.run") as mock_run:
        exit_code = namu_update.main()
        
    assert exit_code == 1
    # 설치된 호스트가 없으므로 subprocess.run 은 호출되지 않아야 함
    mock_run.assert_not_called()

def test_update_claude_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("GROK_HOME", raising=False)

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
    monkeypatch.delenv("GROK_HOME", raising=False)

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

def _write_grok_installed(fake_home: Path, version: str = "0.1.0") -> None:
    install_path = fake_home / "grok_install"
    install_path.mkdir()
    (install_path / "plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    registry = fake_home / ".grok" / "installed-plugins" / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({
        "version": 1,
        "repos": {
            "namu-local": {
                "path": str(install_path),
                "plugins": {"namu": {"version": version}},
            }
        },
    }), encoding="utf-8")


def test_update_grok_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("GROK_HOME", raising=False)
    _write_grok_installed(tmp_path, "4.0.0")

    with patch("subprocess.run") as mock_run, patch("namu_update.shutil.which", return_value=None):
        mock_run.return_value.returncode = 0
        exit_code = namu_update.main()

    assert exit_code == 0
    calls = mock_run.call_args_list
    assert ["grok", "plugin", "update", "namu"] == calls[0][0][0]
    assert "namu_setup_statusline.py" in calls[1][0][0][-1]
    out, _ = capsys.readouterr()
    assert "[grok] 업데이트 전 버전: 4.0.0" in out
    assert "[claude] 미설치" in out
    assert "[agy] 미설치" in out


def test_update_both(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("GROK_HOME", raising=False)

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
    monkeypatch.delenv("GROK_HOME", raising=False)
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


def test_update_agy_restores_old_version_when_install_fails(tmp_path, monkeypatch, capsys):
    """agy는 지우고 나서 설치한다(install이 비파괴 병합이라). 설치가 실패하면 떠 둔
    옛 판을 폴더 소스로 다시 설치해야 한다 — 안 그러면 플러그인이 없는 채로 끝난다."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("GROK_HOME", raising=False)
    _write_agy_installed(tmp_path, "2.0.0")

    본것 = {}

    def 흉내(args, check=False):
        결과 = MagicMock()
        결과.returncode = 0
        if args[:3] == ["agy", "plugin", "install"]:
            if args[3].startswith("https://"):
                결과.returncode = 1           # 원격 설치 실패
            else:
                # 되돌리는 설치 — 그 순간 떠 둔 폴더에 옛 판이 온전히 있어야 한다
                본것["복구_소스"] = Path(args[3])
                본것["복구_판"] = json.loads(
                    (Path(args[3]) / "plugin.json").read_text(encoding="utf-8"))["version"]
        return 결과

    with patch("subprocess.run", side_effect=흉내) as mock_run, \
            patch("namu_update.shutil.which", return_value=None):
        namu_update.update_agy()

    명령들 = [c[0][0] for c in mock_run.call_args_list]
    assert 명령들[0] == ["agy", "plugin", "uninstall", "namu"]
    assert 명령들[1][:3] == ["agy", "plugin", "install"]
    assert 명령들[2][:3] == ["agy", "plugin", "install"]
    assert 본것["복구_판"] == "2.0.0"
    assert not 본것["복구_소스"].exists(), "되돌린 뒤에는 떠 둔 사본을 치워야 한다"
    out, _ = capsys.readouterr()
    assert "옛 판으로 되돌렸습니다" in out


def test_update_agy_keeps_backup_when_restore_also_fails(tmp_path, monkeypatch, capsys):
    """되돌리기까지 실패하면 떠 둔 사본이 유일한 사본이다 — 지우지 않고 자리를 알린다."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("GROK_HOME", raising=False)
    _write_agy_installed(tmp_path, "2.0.0")

    def 흉내(args, check=False):
        결과 = MagicMock()
        결과.returncode = 1 if args[:3] == ["agy", "plugin", "install"] else 0
        return 결과

    with patch("subprocess.run", side_effect=흉내) as mock_run, \
            patch("namu_update.shutil.which", return_value=None):
        namu_update.update_agy()

    복구_소스 = Path(mock_run.call_args_list[2][0][0][3])
    try:
        assert (복구_소스 / "plugin.json").exists()
        out, _ = capsys.readouterr()
        assert str(복구_소스) in out
    finally:
        import shutil
        shutil.rmtree(복구_소스.parent, ignore_errors=True)
