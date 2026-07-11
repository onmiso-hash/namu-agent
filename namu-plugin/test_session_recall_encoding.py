"""session_recall.py(CC SessionStart 훅)의 Windows cp949 무음 실패 회귀 테스트
+ tasks 이원화(namu-26) 통일 테스트.

cp949 회귀: 훅은 🌳📌 등 이모지가 섞인 JSON을 print하는데, Windows에서 stdout이
파이프일 때 기본 인코딩이 cp949라 UnicodeEncodeError -> main()의 broad except가
삼켜 세션 자동주입이 조용히 실패했다(#session_recall cp949 버그).
main() 초입에서 sys.stdout.reconfigure(encoding="utf-8")로 고쳤는지 subprocess
레벨에서 검증한다.

이원화 통일: tasks는 프로젝트 귀속 데이터이지만 저장 위치는 개인 풀
`~/.namu/tasks/<basename(cwd)>/`로 통합됐다(namu-34). 훅은 stdin JSON의 `cwd`
필드로 현재 프로젝트 경로를 얻어 그 basename을 키로 개인 풀에서 찾는다
(statusLine과 동일 규칙).

namu-35: 데이터 루트(교훈·db)는 `Path.home()/".namu"` 고정이고 환경변수 NAMU_HOME은
완전 폐지됐다 — 이 테스트는 HOME 자체를 tmp_path 아래 가짜 홈으로 격리해 훅
서브프로세스가 그 가짜 홈 밑의 ~/.namu를 보게 하며, 실 데이터는 절대 건드리지 않는다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_HOOK_SRC = Path(__file__).parent / "hooks" / "session_recall.py"


def _make_active_task(tasks_root: Path, slug: str, machine: str) -> None:
    task_dir = tasks_root / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(
        f"# {slug} — 테스트 작업\n\n## 목적\n테스트\n\n## 완료조건\n- [ ] 완료\n",
        encoding="utf-8",
    )
    (task_dir / f"context.{machine}.md").write_text(
        f"# context @ {machine} — {slug}\n\n## ▶ 다음\n다음 단계 구현\n\n## 지금 어디까지\n-\n",
        encoding="utf-8",
    )
    (task_dir / "log.md").write_text(
        f"# log — {slug}\n[시작] 2026-07-08 10:00:00 {machine} · 시작\n",
        encoding="utf-8",
    )


def _make_dot_namu_memory(fake_home: Path) -> None:
    """fake_home/.namu에 최소 데이터(memory/learnings.yaml만)를 만든다.

    tasks는 이제 데이터 루트가 아니라 프로젝트(cwd)에 속하므로 여기 두지 않는다.
    """
    memory_dir = fake_home / ".namu" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "learnings.yaml").write_text("", encoding="utf-8")


def _run_hook(
    fake_home: Path,
    machine: str,
    stdin_data: dict,
    extra_env: dict,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    env["HOME"] = str(fake_home)
    env["NAMU_MACHINE"] = machine
    env.update(extra_env)

    # 부모(pytest) 프로세스 측 로케일이 cp949일 수 있어(한글 Windows 기본값),
    # subprocess.run의 text 디코딩은 명시적으로 utf-8을 지정한다.
    # 이는 자식 프로세스의 stdout 인코딩(수정 후 utf-8)과 별개이며,
    # 여기서 env로 넘긴 PYTHONIOENCODING은 자식 프로세스에만 적용된다.
    return subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input=json.dumps(stdin_data),
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )


def test_cp949_env_still_produces_json_output(tmp_path):
    """cp949 강제 환경에서도 stdout이 비어있지 않고 유효 JSON이며 🌳가 포함된다(수정 효과)."""
    machine = "hp"
    fake_home = tmp_path / "fake_home"
    _make_dot_namu_memory(fake_home)
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", machine)

    result = _run_hook(
        fake_home, machine, {"cwd": str(project_dir)}, {"PYTHONIOENCODING": "cp949"}
    )

    assert result.returncode == 0
    assert result.stdout.strip() != ""

    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "🌳" in ctx


def test_output_is_valid_session_start_json(tmp_path):
    """출력이 유효 JSON이고 hookSpecificOutput.hookEventName == 'SessionStart'."""
    machine = "hp"
    fake_home = tmp_path / "fake_home"
    _make_dot_namu_memory(fake_home)
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", machine)

    result = _run_hook(
        fake_home, machine, {"cwd": str(project_dir)}, {"PYTHONIOENCODING": "cp949"}
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_reads_project_dir_from_stdin_cwd_ignores_dot_namu_tasks(tmp_path):
    """stdin의 cwd로 지정된 프로젝트의 개인 풀 tasks만 보인다 — `~/.namu/tasks/`
    바로 아래(basename 폴더 없이)의 task는 무시된다(namu-26 이원화 + namu-34 저장
    위치 통합: 브리핑도 statusLine과 동일하게 ws 기준 개인 풀 tasks만 봐야 함).
    """
    machine = "hp"
    fake_home = tmp_path / "fake_home"
    _make_dot_namu_memory(fake_home)
    # ~/.namu/tasks/ 바로 아래(구 동작이면 잡혔을 위치)에 task를 심어둔다 — 새 동작에서는 안 보여야 함.
    _make_active_task(fake_home / ".namu" / "tasks", "memory-root-task", machine)

    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "project-task", machine)

    result = _run_hook(
        fake_home, machine, {"cwd": str(project_dir)}, {"PYTHONIOENCODING": "utf-8"}
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "project-task" in ctx
    assert "memory-root-task" not in ctx


def test_missing_stdin_cwd_falls_back_to_process_cwd(tmp_path):
    """stdin JSON에 cwd가 없으면 os.getcwd() 폴백 — subprocess의 cwd로 지정한 프로젝트를 본다."""
    machine = "hp"
    fake_home = tmp_path / "fake_home"
    _make_dot_namu_memory(fake_home)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "fallback-task", machine)

    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    env["HOME"] = str(fake_home)
    env["NAMU_MACHINE"] = machine

    result = subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input="{}",
        capture_output=True,
        encoding="utf-8",
        env=env,
        cwd=str(project_dir),
        timeout=15,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "fallback-task" in ctx


def test_namu_home_env_var_has_no_effect(tmp_path):
    """NAMU_HOME 환경변수(namu-35: 완전 폐지)를 설정해도 데이터 루트는 여전히
    HOME/.namu 고정이다 — decoy 위치의 교훈은 무시되고 브리핑은 정상 동작한다."""
    machine = "hp"
    fake_home = tmp_path / "fake_home"
    _make_dot_namu_memory(fake_home)
    decoy = tmp_path / "decoy_namu_home"
    decoy.mkdir()

    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "project-task", machine)

    result = _run_hook(
        fake_home,
        machine,
        {"cwd": str(project_dir)},
        {"PYTHONIOENCODING": "utf-8", "NAMU_HOME": str(decoy)},
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "project-task" in ctx
    assert not (decoy / "memory").exists()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
