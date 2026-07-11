"""namu_statusline.py의 cp949 파이프 안전망 + 렌더 로그 회귀 테스트
+ tasks 이원화(namu-26) 통일 테스트.

cp949 회귀: statusline은 활성 task가 있으면 📌(비BMP 이모지)를 print하는데, 호출 측이
-X utf8 없이 부르면 Windows 파이프 stdout 기본 cp949에서 UnicodeEncodeError로
죽는다 — 한글만 있는 '진행 task 없음'은 살아남아 "task만 안 뜨는" 무음 실패가
된다(session_recall.py cp949 버그와 동일 패턴). main() 초입의
sys.stdout.reconfigure(encoding="utf-8") 안전망과, 매 렌더가
NAMU_HOME/db/statusline.log에 남는 관측성을 subprocess 레벨에서 검증한다.

이원화 통일: tasks는 프로젝트 귀속 데이터이지만 저장 위치는 개인 풀
`~/.namu/tasks/<basename(ws)>/`로 통합됐다(namu-34). resolve_active_task는 stdin
JSON의 workspace.current_dir(=ws)의 폴더명을 키로 Path.home() 기준을 본다(NAMU_HOME과는
무관). 실 데이터는 NAMU_HOME뿐 아니라 HOME도 tmp_path로 격리해 절대 건드리지 않는다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "namu_statusline.py"


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


def _run_statusline(
    namu_home: Path, stdin_json: dict, extra_env: dict, fake_home: Path | None = None
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["NAMU_HOME"] = str(namu_home)
    if fake_home is not None:
        env["HOME"] = str(fake_home)
    env.update(extra_env)

    # 부모(pytest) 측 디코딩은 utf-8 명시 — 자식의 PYTHONIOENCODING과 별개.
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=json.dumps(stdin_json),
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=15,
    )


def test_cp949_pipe_still_renders_pin_emoji(tmp_path):
    """cp949 강제 파이프에서도 활성 task 렌더(📌 포함)가 죽지 않는다(안전망 효과)."""
    namu_home = tmp_path / "namu_home"
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(namu_home, stdin_json, {"PYTHONIOENCODING": "cp949"}, fake_home)

    assert result.returncode == 0
    assert "📌 encoding-test-task" in result.stdout


def test_render_is_appended_to_log(tmp_path):
    """매 렌더가 NAMU_HOME/db/statusline.log에 출력 원문 그대로 남는다(관측성).

    로그 경로는 여전히 NAMU_HOME 기준(관측성 목적, tasks 위치와는 별개 관심사).
    """
    namu_home = tmp_path / "namu_home"
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(namu_home, stdin_json, {"PYTHONIOENCODING": "cp949"}, fake_home)

    assert result.returncode == 0
    log = (namu_home / "db" / "statusline.log").read_text(encoding="utf-8")
    assert result.stdout.strip() in log


def test_render_log_includes_resolved_tasks_dir(tmp_path):
    """렌더 로그 줄에 해석된 tasks_dir 경로가 포함된다(namu-34 ④, 미동기화 재발 시 판정용)."""
    namu_home = tmp_path / "namu_home"
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(namu_home, stdin_json, {"PYTHONIOENCODING": "cp949"}, fake_home)

    assert result.returncode == 0
    log = (namu_home / "db" / "statusline.log").read_text(encoding="utf-8")
    expected_tasks_dir = str(fake_home / ".namu" / "tasks" / "project")
    assert f"tasks_dir={expected_tasks_dir}" in log


def test_no_task_renders_and_logs(tmp_path):
    """task가 없으면 '진행 task 없음'을 출력하고 그것도 로그에 남는다."""
    namu_home = tmp_path / "namu_home"
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(namu_home, stdin_json, {"PYTHONIOENCODING": "cp949"}, fake_home)

    assert result.returncode == 0
    assert "진행 task 없음" in result.stdout
    log = (namu_home / "db" / "statusline.log").read_text(encoding="utf-8")
    assert "진행 task 없음" in log


def test_ignores_namu_home_tasks_uses_ws_only(tmp_path):
    """NAMU_HOME 아래 tasks에 활성 task가 있어도, ws(workspace.current_dir) 기준
    개인 풀(~/.namu/tasks/<basename>/)의 tasks만 본다(namu-26 이원화 + namu-34 저장 위치
    통합 — 이전 동작(NAMU_HOME 우선)이면 이 테스트는 실패한다).
    """
    namu_home = tmp_path / "namu_home"
    fake_home = tmp_path / "fake_home"
    _make_active_task(namu_home / "tasks", "memory-root-task", "hp")

    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)  # ws의 개인 풀 tasks에는 활성 task 없음

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(namu_home, stdin_json, {"PYTHONIOENCODING": "cp949"}, fake_home)

    assert result.returncode == 0
    assert "진행 task 없음" in result.stdout
    assert "memory-root-task" not in result.stdout


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
