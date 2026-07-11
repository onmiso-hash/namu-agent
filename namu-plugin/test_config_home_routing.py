"""config.py 데이터 루트 고정 경로(namu-35) 회귀 테스트.

배경: namu-35로 "개발 모드/설치 모드" 구분 자체가 폐지됐다. 예전에는 NAMU_HOME
환경변수 우선 → REPO_ROOT/memory 실재+cwd 조건 폴백 → Path.home()/".namu" 순서로
분기했으나(#33 cwd 조건 도입), 이제 그 분기 자체가 사라지고 데이터 루트는
어떤 cwd·환경변수 상태에서도 `Path.home() / ".namu"` 하나로 고정이다
(`config.NAMU_DATA_ROOT`).

이 파일은 원래 폴백 ②(REPO_ROOT/memory 실재 시 REPO_ROOT로 라우팅)의 cwd 조건을
검증했으나, 그 대상 로직 자체가 삭제되며 존재 이유가 사라졌다 — "고정 경로 검증"
(어떤 cwd/env에서도 NAMU_DATA_ROOT·LEARNINGS_YAML_PATH가 흔들리지 않는지)으로
대체한다. NAMU_HOME 환경변수를 설정해도 완전히 무시됨을 확인하는 테스트도 여기 둔다.

픽스처 함정: 진짜 개발 repo 안에서 cwd를 잡고 서브프로세스를 띄우면
find_dotenv(usecwd=True)가 repo 루트 .env(NAMU_HOME=... 명시)를 찾아 os.environ에
주입한다 — 이 파일은 오히려 그 상태에서도 NAMU_DATA_ROOT가 흔들리지 않는지를
검증 대상으로 삼으므로 그대로 둔다. 단, 실 ~/.namu를 건드리지 않도록 HOME은
반드시 tmp_path로 격리한다(namu-33 교훈).
"""
import os
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).parent
_REPO_ROOT = _NAMU_PLUGIN_DIR.parent

_PROBE = (
    "import config; "
    "print(config.NAMU_DATA_ROOT); "
    "print(config.LEARNINGS_YAML_PATH)"
)


def _run_probe(cwd: Path, env: dict) -> tuple[str, str]:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2, result.stdout
    return lines[0], lines[1]


def test_fixed_path_regardless_of_cwd_inside_repo(tmp_path):
    """cwd가 개발 repo 안쪽이어도 데이터 루트는 fake HOME/.namu로 고정된다."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    env["HOME"] = str(fake_home)

    namu_data_root, learnings_path = _run_probe(_NAMU_PLUGIN_DIR, env)

    expected_root = fake_home / ".namu"
    assert Path(namu_data_root).resolve() == expected_root.resolve(), namu_data_root
    assert learnings_path.endswith("learnings.yaml"), learnings_path
    assert "product_" not in learnings_path, learnings_path


def test_fixed_path_regardless_of_cwd_outside_repo(tmp_path):
    """cwd가 repo 바깥(tmp)이어도 결과는 동일하게 fake HOME/.namu다."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    outside_dir = tmp_path / "some_other_project"
    outside_dir.mkdir()

    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    env["HOME"] = str(fake_home)
    env["PYTHONPATH"] = str(_NAMU_PLUGIN_DIR)

    namu_data_root, learnings_path = _run_probe(outside_dir, env)

    expected_root = fake_home / ".namu"
    assert Path(namu_data_root).resolve() == expected_root.resolve(), namu_data_root
    assert learnings_path.endswith("learnings.yaml"), learnings_path


def test_namu_home_env_var_is_ignored(tmp_path):
    """NAMU_HOME 환경변수를 명시적으로 설정해도(namu-35: 완전 폐지) 데이터 루트는
    여전히 HOME/.namu 고정이며, 설정된 값으로 라우팅되지 않는다."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    decoy = tmp_path / "decoy_namu_home"
    decoy.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["NAMU_HOME"] = str(decoy)

    namu_data_root, learnings_path = _run_probe(_NAMU_PLUGIN_DIR, env)

    expected_root = fake_home / ".namu"
    assert Path(namu_data_root).resolve() == expected_root.resolve(), namu_data_root
    assert Path(namu_data_root).resolve() != decoy.resolve(), namu_data_root
    assert learnings_path.endswith("learnings.yaml"), learnings_path


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
