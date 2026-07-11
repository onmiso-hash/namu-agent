"""config.py LEARNINGS_YAML_PATH 고정 경로(namu-35) 회귀 테스트.

배경: #32 당시엔 NAMU_HOME == REPO_ROOT(개발 모드)일 때만 파일명을
`product_learnings.yaml`로 쓰고, 그 외(설치형/명시 env)는 `learnings.yaml`을 쓰는
분기가 있었다. namu-35로 "개발 모드/설치 모드" 구분 자체가 폐지되며 이 분기도
삭제됐다 — LEARNINGS_YAML_PATH는 이제 어떤 상황에서도 `~/.namu/memory/learnings.yaml`
하나로 고정이다(`product_` 접두사 파일명은 더 이상 코드에서 생성되지 않는다).

config.py는 NAMU_DATA_ROOT를 **모듈 로드 시점**에 한 번만 계산해 LEARNINGS_YAML_PATH
상수를 확정한다. 이미 import된 config 모듈을 이 프로세스 안에서 importlib.reload로
재계산하면 저장소 루트 `.env`(NAMU_MACHINE=hp 등)가 os.environ에 눌러앉아 다른
테스트를 오염시킬 위험이 있다. 그래서 여기서는 별도 서브프로세스로 config를 새로
import해 오염 없이 검증한다(test_session_recall_encoding.py의 subprocess 격리
패턴을 따름). 실 ~/.namu는 HOME을 tmp_path로 격리해 절대 건드리지 않는다(namu-33 교훈).
"""
import os
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).parent
_REPO_ROOT = _NAMU_PLUGIN_DIR.parent


def _learnings_yaml_path(fake_home: Path, extra_env: dict | None = None) -> str:
    """서브프로세스에서 config를 import해 LEARNINGS_YAML_PATH를 문자열로 얻는다."""
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
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


def test_learnings_path_is_fixed_under_fake_home(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    path = _learnings_yaml_path(fake_home)

    expected = fake_home / ".namu" / "memory" / "learnings.yaml"
    assert Path(path).resolve() == expected.resolve(), path
    assert "product_" not in path, path


def test_learnings_path_ignores_namu_home_pointing_at_repo_root(tmp_path):
    """예전 분기 조건(NAMU_HOME == REPO_ROOT)을 그대로 흉내내도 더 이상
    product_learnings.yaml로 갈라지지 않는다 — NAMU_HOME 자체가 무시된다."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    path = _learnings_yaml_path(fake_home, extra_env={"NAMU_HOME": str(_REPO_ROOT)})

    expected = fake_home / ".namu" / "memory" / "learnings.yaml"
    assert Path(path).resolve() == expected.resolve(), path
    assert path.endswith("learnings.yaml"), path
    assert "product_" not in path, path


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
