"""config.py NAMU_HOME 폴백 ②의 cwd 조건(#33) 회귀 테스트.

배경: 폴백 ②(REPO_ROOT/memory 실재 시 REPO_ROOT)는 원래 REPO_ROOT를
Path(__file__).parent.parent(플러그인 파일 위치)로만 판정했다. 플러그인을
directory 소스(개발 repo 라이브 참조)로 설치한 머신에서는 REPO_ROOT가 항상
개발 repo를 가리켜, 타 프로젝트 cwd에서 실행해도 개발 repo로 라우팅되는
오배선이 있었다(메모리 3원 분류 #32 위반). 이제 "REPO_ROOT/memory 실재 AND
cwd가 REPO_ROOT 안쪽"일 때만 폴백 ②가 적용된다.

픽스처 함정: 진짜 개발 repo 안에서 cwd를 잡고 서브프로세스를 띄우면
find_dotenv(usecwd=True)가 repo 루트 .env(NAMU_HOME=... 명시)를 찾아
우선순위 ①로 먼저 통과해버려 폴백 ② 로직이 전혀 검증되지 않는다
(test_config_learnings_path.py는 애초에 NAMU_HOME env를 직접 주입하는
테스트라 이 문제가 없지만, 이 파일은 env를 "제거"해 폴백을 검증해야 하므로
직접 걸린다). 그래서:
  - 방향 (a)는 tmp에 config.py만 복사한 "가짜 repo"(memory/ 디렉터리 포함,
    .env 없음)를 만들어 그 안에서 실행한다 — REPO_ROOT/.env가 아예 없으므로
    find_dotenv가 아무것도 찾지 못해 폴백 경로가 진짜로 타진다.
  - 방향 (b)는 진짜 repo의 config.py를 PYTHONPATH로 끌어와, cwd만 repo 바깥
    tmp 디렉터리로 두고 실행한다. HOME도 tmp로 패치해 실 ~/.namu를 건드리지
    않는다.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).parent
_REPO_ROOT = _NAMU_PLUGIN_DIR.parent
_CONFIG_PY = _NAMU_PLUGIN_DIR / "config.py"
_TASK_RESOLVE_PY = _NAMU_PLUGIN_DIR / "task_resolve.py"

_PROBE = (
    "import config; "
    "print(config.NAMU_HOME); "
    "print(config.LEARNINGS_YAML_PATH)"
)


def _clean_env(tmp_path: Path) -> dict:
    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    env["HOME"] = str(fake_home)
    return env


def test_cwd_inside_repo_without_env_falls_back_to_repo_root(tmp_path):
    """(a) cwd가 repo 안쪽 + NAMU_HOME 미설정 → NAMU_HOME == REPO_ROOT (product_ 접두사)."""
    fake_repo = tmp_path / "fake_repo"
    fake_plugin_dir = fake_repo / "namu-plugin"
    fake_plugin_dir.mkdir(parents=True)
    shutil.copy(_CONFIG_PY, fake_plugin_dir / "config.py")
    # config.py가 tasks_dir_for()를 task_resolve.tasks_root_for()에 위임(namu-34)하므로
    # 가짜 plugin 디렉터리에도 동봉해야 import가 성립한다.
    shutil.copy(_TASK_RESOLVE_PY, fake_plugin_dir / "task_resolve.py")
    (fake_repo / "memory").mkdir()

    env = _clean_env(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(fake_plugin_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2, result.stdout
    namu_home, learnings_path = lines
    assert Path(namu_home).resolve() == fake_repo.resolve(), namu_home
    assert learnings_path.endswith("product_learnings.yaml"), learnings_path


def test_cwd_outside_repo_without_env_falls_back_to_dot_namu(tmp_path):
    """(b) cwd가 repo 바깥(tmp) + NAMU_HOME 미설정 + REPO_ROOT/memory 실재 → ~/.namu."""
    outside_dir = tmp_path / "some_other_project"
    outside_dir.mkdir()

    env = _clean_env(tmp_path)
    env["PYTHONPATH"] = str(_NAMU_PLUGIN_DIR)

    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(outside_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2, result.stdout
    namu_home, learnings_path = lines
    expected_home = Path(env["HOME"]) / ".namu"
    assert Path(namu_home).resolve() == expected_home.resolve(), namu_home
    assert learnings_path.endswith("learnings.yaml"), learnings_path
    assert "product_" not in learnings_path, learnings_path


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
