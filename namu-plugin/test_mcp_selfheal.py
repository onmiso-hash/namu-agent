"""agy 설치본 mcp_config.json 절대경로 self-healing 테스트."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))

from session_inject import heal_mcp_config

_HOOK_SRC = Path(__file__).parent / "hooks" / "session_inject.py"


def _write_cfg(plugin_root: Path, args_last: str) -> Path:
    plugin_root.mkdir(parents=True, exist_ok=True)
    cfg_path = plugin_root / "mcp_config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "namu-memory": {
                        "command": "uv",
                        "args": ["run", "--script", args_last],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return cfg_path


def test_relative_path_rewritten_to_absolute(tmp_path):
    plugin_root = tmp_path / "plugins" / "namu"
    cfg_path = _write_cfg(plugin_root, "namu-plugin/mcp_server.py")

    result = heal_mcp_config(plugin_root)

    assert result is True
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    args = data["mcpServers"]["namu-memory"]["args"]
    assert args[-1] == str(plugin_root / "mcp_server.py")
    assert Path(args[-1]).is_absolute()


def test_already_absolute_is_noop(tmp_path):
    plugin_root = tmp_path / "plugins" / "namu"
    abs_path = str(plugin_root / "mcp_server.py")
    cfg_path = _write_cfg(plugin_root, abs_path)
    before_content = cfg_path.read_text(encoding="utf-8")
    before_mtime = cfg_path.stat().st_mtime

    result = heal_mcp_config(plugin_root)

    assert result is False
    assert cfg_path.read_text(encoding="utf-8") == before_content
    assert cfg_path.stat().st_mtime == before_mtime


def test_dev_repo_guard_skips_rewrite(tmp_path):
    # namu-plugin/의 부모(repo root)에 .git이 있으면 개발 repo → 재작성 금지
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / "namu-plugin"
    (repo_root / ".git").mkdir(parents=True)
    cfg_path = _write_cfg(plugin_root, "namu-plugin/mcp_server.py")
    before_content = cfg_path.read_text(encoding="utf-8")

    result = heal_mcp_config(plugin_root)

    assert result is False
    assert cfg_path.read_text(encoding="utf-8") == before_content


def test_missing_mcp_config_returns_false(tmp_path):
    plugin_root = tmp_path / "plugins" / "namu"
    plugin_root.mkdir(parents=True)

    result = heal_mcp_config(plugin_root)

    assert result is False


def test_broken_json_returns_false_no_exception(tmp_path):
    plugin_root = tmp_path / "plugins" / "namu"
    plugin_root.mkdir(parents=True)
    cfg_path = plugin_root / "mcp_config.json"
    cfg_path.write_text("{not valid json", encoding="utf-8")

    result = heal_mcp_config(plugin_root)

    assert result is False


def _copy_hook_install(tmp_path: Path) -> tuple[Path, Path]:
    """가짜 설치본 트리(<tmp>/plugins/namu/hooks/session_inject.py)를 만들고 스크립트 경로를 반환."""
    plugin_root = tmp_path / "plugins" / "namu"
    hooks_dir = plugin_root / "hooks"
    hooks_dir.mkdir(parents=True)
    script_path = hooks_dir / "session_inject.py"
    shutil.copy(_HOOK_SRC, script_path)
    return plugin_root, script_path


def test_heal_cli_rewrites_relative_path(tmp_path):
    plugin_root, script_path = _copy_hook_install(tmp_path)
    cfg_path = _write_cfg(plugin_root, "namu-plugin/mcp_server.py")

    result = subprocess.run(
        [sys.executable, str(script_path), "--heal"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "교정 완료" in result.stdout
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    args = data["mcpServers"]["namu-memory"]["args"]
    assert args[-1] == str(plugin_root / "mcp_server.py")
    assert Path(args[-1]).is_absolute()


def test_heal_cli_noop_when_already_absolute(tmp_path):
    plugin_root, script_path = _copy_hook_install(tmp_path)
    abs_path = str(plugin_root / "mcp_server.py")
    cfg_path = _write_cfg(plugin_root, abs_path)
    before_content = cfg_path.read_text(encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_path), "--heal"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "무변경" in result.stdout
    assert cfg_path.read_text(encoding="utf-8") == before_content


def test_hook_mode_without_args_still_outputs_empty_json(tmp_path):
    # 회귀: --heal 분기 추가가 기존 훅 모드(인자 없음) 출력 규약을 깨지 않는지 확인
    _, script_path = _copy_hook_install(tmp_path)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "{}"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
