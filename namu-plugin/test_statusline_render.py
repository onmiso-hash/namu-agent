"""namu_statusline.py의 cp949 파이프 안전망 + 렌더 로그 회귀 테스트
+ tasks 이원화(namu-26) 통일 테스트.

cp949 회귀: statusline은 활성 task가 있으면 📌(비BMP 이모지)를 print하는데, 호출 측이
-X utf8 없이 부르면 Windows 파이프 stdout 기본 cp949에서 UnicodeEncodeError로
죽는다 — 한글만 있는 '진행 task 없음'은 살아남아 "task만 안 뜨는" 무음 실패가
된다(session_recall.py cp949 버그와 동일 패턴). main() 초입의
sys.stdout.reconfigure(encoding="utf-8") 안전망과, 매 렌더가
~/.namu/db/statusline.log에 남는 관측성을 subprocess 레벨에서 검증한다.

namu-35: 데이터 루트가 `Path.home()/".namu"` 고정이 되며 환경변수 NAMU_HOME은
완전 폐지됐다 — 렌더 로그 경로도 더 이상 NAMU_HOME을 참조하지 않고 항상
Path.home()/".namu"/db/statusline.log다. 이 테스트들은 HOME 자체를 tmp_path
아래 가짜 홈으로 격리해 고정 경로가 그 가짜 홈 밑으로 떨어지는지 검증하며,
실 ~/.namu는 절대 건드리지 않는다.

이원화 통일: tasks는 프로젝트 귀속 데이터이지만 저장 위치는 개인 풀
`~/.namu/tasks/<basename(ws)>/`로 통합됐다(namu-34). resolve_active_task는 stdin
JSON의 workspace.current_dir(=ws)의 폴더명을 키로 Path.home() 기준을 본다.
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
    fake_home: Path, stdin_json: dict, extra_env: dict
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("NAMU_HOME", None)
    # Path.home()(=os.path.expanduser)는 Windows에서 USERPROFILE을 HOME보다 우선
    # 참조한다 — HOME만 덮어써서는 이 플랫폼에서 가짜 홈 격리가 먹히지 않는다.
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
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
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "📌 encoding-test-task" in result.stdout


def test_render_is_appended_to_log(tmp_path):
    """매 렌더가 ~/.namu/db/statusline.log(namu-35: 고정 경로)에 출력 원문 그대로 남는다
    (관측성)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    log = (fake_home / ".namu" / "db" / "statusline.log").read_text(encoding="utf-8")
    assert result.stdout.strip() in log


def test_render_log_includes_resolved_tasks_dir(tmp_path):
    """렌더 로그 줄에 해석된 tasks_dir 경로가 포함된다(namu-34 ④, 미동기화 재발 시 판정용)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    _make_active_task(fake_home / ".namu" / "tasks" / "project", "encoding-test-task", "hp")

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    log = (fake_home / ".namu" / "db" / "statusline.log").read_text(encoding="utf-8")
    expected_tasks_dir = str(fake_home / ".namu" / "tasks" / "project")
    assert f"tasks_dir={expected_tasks_dir}" in log


def test_no_task_renders_and_logs(tmp_path):
    """task가 없으면 '진행 task 없음'을 출력하고 그것도 로그에 남는다."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "진행 task 없음" in result.stdout
    log = (fake_home / ".namu" / "db" / "statusline.log").read_text(encoding="utf-8")
    assert "진행 task 없음" in log


def test_ignores_tasks_directly_under_dot_namu_uses_ws_basename_only(tmp_path):
    """`~/.namu/tasks/`(basename 폴더 없이 바로 아래)에 활성 task가 있어도, ws
    (workspace.current_dir)의 basename 폴더 기준 개인 풀만 본다(namu-26 이원화 +
    namu-34 저장 위치 통합 — ws의 basename 경로가 아니면 무시돼야 정상).
    """
    fake_home = tmp_path / "fake_home"
    _make_active_task(fake_home / ".namu" / "tasks", "memory-root-task", "hp")

    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)  # ws의 개인 풀 tasks(<home>/.namu/tasks/project/)에는 없음

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "진행 task 없음" in result.stdout
    assert "memory-root-task" not in result.stdout


def test_task_title_starting_with_slug_shows_title_once(tmp_path):
    """task.md 제목이 관례대로 "<slug> — <설명>"이면 slug를 중복 표시하지 않고
    "📌 {제목}"만 출력한다(namu-37 ①)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    tasks_root = fake_home / ".namu" / "tasks" / "project"
    slug = "namu-37-statusline-render"
    task_dir = tasks_root / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(
        f"# {slug} — statusLine 렌더 개선\n\n## 목적\n테스트\n\n## 완료조건\n- [ ] 완료\n",
        encoding="utf-8",
    )
    (task_dir / "context.hp.md").write_text(
        f"# context @ hp — {slug}\n\n## ▶ 다음\n다음 단계 구현\n\n## 지금 어디까지\n-\n",
        encoding="utf-8",
    )
    (task_dir / "log.md").write_text(
        f"# log — {slug}\n[시작] 2026-07-08 10:00:00 hp · 시작\n", encoding="utf-8"
    )

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert f"📌 {slug} — statusLine 렌더 개선" in result.stdout
    assert f"📌 {slug} · {slug} — statusLine 렌더 개선" not in result.stdout


def test_task_title_not_starting_with_slug_keeps_slug_and_title(tmp_path):
    """task.md 제목이 slug로 시작하지 않으면 기존 "📌 {slug} · {제목}" 형식을 유지한다
    (namu-37 ①, 하위 호환)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    slug = "encoding-test-task"
    task_dir = fake_home / ".namu" / "tasks" / "project" / slug
    task_dir.mkdir(parents=True)
    # 관례를 따르지 않는 제목(slug로 시작하지 않음) — 구형 task.md 호환 케이스
    (task_dir / "task.md").write_text(
        "# 테스트 작업\n\n## 목적\n테스트\n\n## 완료조건\n- [ ] 완료\n", encoding="utf-8"
    )
    (task_dir / "context.hp.md").write_text(
        f"# context @ hp — {slug}\n\n## ▶ 다음\n다음 단계 구현\n\n## 지금 어디까지\n-\n",
        encoding="utf-8",
    )
    (task_dir / "log.md").write_text(
        f"# log — {slug}\n[시작] 2026-07-08 10:00:00 hp · 시작\n", encoding="utf-8"
    )

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "📌 encoding-test-task · 테스트 작업" in result.stdout


def test_rate_limits_both_present_render_5h_and_7d(tmp_path):
    """rate_limits.five_hour/seven_day가 둘 다 있으면 꼬리에 "· 5h n% · 7d m%"가
    붙는다(namu-37 ②)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "TEST"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "rate_limits": {
            "five_hour": {"used_percentage": 34.4},
            "seven_day": {"used_percentage": 12.1},
        },
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 34% · 7d 12%" in result.stdout


def test_rate_limits_only_five_hour_present(tmp_path):
    """five_hour만 있으면 "5h"만 출력되고 "7d"는 생략된다(namu-37 ②, 독립 부재)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "TEST"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "rate_limits": {"five_hour": {"used_percentage": 34.4}},
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 34%" in result.stdout
    assert "7d" not in result.stdout


def test_rate_limits_absent_tail_matches_legacy_output(tmp_path):
    """rate_limits 필드 자체가 없으면 꼬리는 기존과 완전히 동일하다(namu-37 ②, 하위 호환:
    비구독자·세션 첫 응답 전)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "TEST"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert result.stdout.rstrip("\n").endswith("| 6%")


def test_agy_gemini_quota_5h_and_weekly_render(tmp_path):
    """agy가 gemini 모델용 quota(remaining_fraction, 남은 비율)를 보내면 "쓴 %"로
    극성을 뒤집어 5h/7d(=weekly)에 렌더한다(namu-39). rate_limits는 agy 쪽에서
    안 보내므로(상호배타) quota만으로 채워져야 한다."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "Gemini 3.1 Pro (High)"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "quota": {
            "gemini-5h": {"remaining_fraction": 1.0},
            "gemini-weekly": {"remaining_fraction": 0.9852},
        },
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 0% · 7d 1%" in result.stdout


def test_agy_3p_quota_5h_and_weekly_render(tmp_path):
    """agy가 3rd-party(Claude/GPT) 모델용 quota를 보내면 3p-5h/3p-weekly를
    "쓴 %"로 뒤집어 렌더한다(namu-39)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "Claude Opus"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "quota": {
            "3p-5h": {"remaining_fraction": 0.5},
            "3p-weekly": {"remaining_fraction": 0.8},
        },
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 50% · 7d 20%" in result.stdout


def test_agy_gemini_model_prefers_gemini_group_over_3p(tmp_path):
    """model.display_name에 "gemini"가 포함되면 quota에 gemini/3p 그룹이 둘 다
    있어도 gemini 그룹 값이 선택된다(namu-39, 대소문자 무시)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "gemini-3-pro"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "quota": {
            "gemini-5h": {"remaining_fraction": 0.9},
            "gemini-weekly": {"remaining_fraction": 0.7},
            "3p-5h": {"remaining_fraction": 0.1},
            "3p-weekly": {"remaining_fraction": 0.2},
        },
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 10% · 7d 30%" in result.stdout


def test_agy_quota_absent_and_rate_limits_absent_tail_is_ctx_only(tmp_path):
    """quota와 rate_limits가 둘 다 없으면 꼬리는 ctx만 남는다(namu-39, 기존
    하위 호환 유지 — "| n%"로 끝남)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "TEST"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert result.stdout.rstrip("\n").endswith("| 6%")


def test_agy_quota_only_5h_present_omits_weekly(tmp_path):
    """gemini-5h만 있고 gemini-weekly가 없으면 "5h"만 나오고 "7d"는 생략된다
    (namu-39, 독립 부재)."""
    fake_home = tmp_path / "fake_home"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)

    stdin_json = {
        "model": {"display_name": "Gemini 3.1 Pro (High)"},
        "workspace": {"current_dir": str(project_dir)},
        "context_window": {"used_percentage": 6},
        "quota": {"gemini-5h": {"remaining_fraction": 0.75}},
    }
    result = _run_statusline(fake_home, stdin_json, {"PYTHONIOENCODING": "cp949"})

    assert result.returncode == 0
    assert "| 6% · 5h 25%" in result.stdout
    assert "7d" not in result.stdout


def test_namu_home_env_var_has_no_effect_on_log_path(tmp_path):
    """NAMU_HOME 환경변수(namu-35: 완전 폐지)를 설정해도 렌더 로그는 여전히
    HOME/.namu/db/statusline.log(고정 경로)에 남고, 설정값 쪽으로는 가지 않는다."""
    fake_home = tmp_path / "fake_home"
    decoy = tmp_path / "decoy_namu_home"
    decoy.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    stdin_json = {"model": {"display_name": "TEST"}, "workspace": {"current_dir": str(project_dir)}}
    result = _run_statusline(
        fake_home, stdin_json, {"PYTHONIOENCODING": "cp949", "NAMU_HOME": str(decoy)}
    )

    assert result.returncode == 0
    assert (fake_home / ".namu" / "db" / "statusline.log").exists()
    assert not (decoy / "db" / "statusline.log").exists()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
