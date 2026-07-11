"""config.py LEARNINGS_YAML_PATH 파일명 분기(#32) 회귀 테스트.

메모리 3원 분류: NAMU_HOME == REPO_ROOT(개발 모드)일 때만 파일명을
`product_learnings.yaml`로 쓰고, 그 외(설치형/명시 env)는 기존 `learnings.yaml`
그대로 유지한다.

config.py는 NAMU_HOME/REPO_ROOT 비교 결과를 **모듈 로드 시점**에 한 번만 계산해
LEARNINGS_YAML_PATH 상수를 확정한다. 이미 import된 config 모듈을 이 프로세스
안에서 importlib.reload로 재계산하면 저장소 루트 `.env`(NAMU_MACHINE=hp 등)가
os.environ에 눌러앉아 다른 테스트(test_config_machine.py 등)를 오염시킬 위험이
있다(그 파일의 주석 참고). 그래서 여기서는 별도 서브프로세스로 config를 새로
import해 오염 없이 검증한다(test_session_recall_encoding.py의 subprocess 격리
패턴을 따름).
"""
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).parent
_REPO_ROOT = _NAMU_PLUGIN_DIR.parent


def _learnings_yaml_path(namu_home: Path, extra_env: dict | None = None) -> str:
    """서브프로세스에서 config를 import해 LEARNINGS_YAML_PATH를 문자열로 얻는다."""
    import os

    env = os.environ.copy()
    env["NAMU_HOME"] = str(namu_home)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.LEARNINGS_YAML_PATH)"],
        cwd=str(_NAMU_PLUGIN_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return result.stdout.strip()


def test_dev_mode_namu_home_equals_repo_root_uses_product_prefix():
    path = _learnings_yaml_path(_REPO_ROOT)
    assert path.endswith("product_learnings.yaml"), path


def test_non_dev_namu_home_keeps_plain_learnings_filename(tmp_path):
    other_home = tmp_path / "not_repo_root"
    other_home.mkdir()
    path = _learnings_yaml_path(other_home)
    assert path.endswith("learnings.yaml"), path
    assert "product_" not in path, path


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
