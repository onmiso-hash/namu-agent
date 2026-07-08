"""session_recall.py(CC SessionStart 훅)의 Windows cp949 무음 실패 회귀 테스트.

훅은 🌳📌 등 이모지가 섞인 JSON을 print하는데, Windows에서 stdout이 파이프일 때
기본 인코딩이 cp949라 UnicodeEncodeError -> main()의 broad except가 삼켜
세션 자동주입이 조용히 실패했다(#session_recall cp949 버그).
main() 초입에서 sys.stdout.reconfigure(encoding="utf-8")로 고쳤는지 subprocess
레벨에서 검증한다. 실 데이터(D:\\Project\\namu-agent의 memory/db)는 절대 건드리지
않도록 NAMU_HOME을 tmp_path로 격리한다.
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


def _make_namu_home(tmp_path: Path, machine: str) -> Path:
    """tmp_path에 최소 NAMU_HOME(tasks/ + memory/learnings.yaml)을 만든다."""
    namu_home = tmp_path / "namu_home"
    tasks_root = namu_home / "tasks"
    tasks_root.mkdir(parents=True)
    _make_active_task(tasks_root, "encoding-test-task", machine)

    memory_dir = namu_home / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "learnings.yaml").write_text("", encoding="utf-8")

    return namu_home


def _run_hook(namu_home: Path, machine: str, extra_env: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["NAMU_HOME"] = str(namu_home)
    env["NAMU_MACHINE"] = machine
    env.update(extra_env)

    # 부모(pytest) 프로세스 측 로케일이 cp949일 수 있어(한글 Windows 기본값),
    # subprocess.run의 text 디코딩은 명시적으로 utf-8을 지정한다.
    # 이는 자식 프로세스의 stdout 인코딩(수정 후 utf-8)과 별개이며,
    # 여기서 env로 넘긴 PYTHONIOENCODING은 자식 프로세스에만 적용된다.
    return subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input="{}",
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )


def test_cp949_env_still_produces_json_output(tmp_path):
    """cp949 강제 환경에서도 stdout이 비어있지 않고 유효 JSON이며 🌳가 포함된다(수정 효과)."""
    machine = "hp"
    namu_home = _make_namu_home(tmp_path, machine)

    result = _run_hook(namu_home, machine, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert result.stdout.strip() != ""

    data = json.loads(result.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "🌳" in ctx


def test_output_is_valid_session_start_json(tmp_path):
    """출력이 유효 JSON이고 hookSpecificOutput.hookEventName == 'SessionStart'."""
    machine = "hp"
    namu_home = _make_namu_home(tmp_path, machine)

    result = _run_hook(namu_home, machine, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
