"""namu-62 ① — Stop 훅(closing_guard)이 '마무리' 시점의 [다음] 누락을 막는지 검증.

핵심 성질 4가지:
  1. 마무리 신호가 아니면 절대 개입하지 않는다(매 턴 끝마다 도는 훅이라 오작동이
     곧 사용성 파괴다).
  2. 마무리 신호인데 이번 세션의 [다음] 줄이 없으면 block한다.
  3. 이번 세션에 [다음](또는 task를 닫는 [완료]/[중단])이 있으면 통과한다.
  4. stop_hook_active면 무조건 통과한다 — 아니면 무한 루프가 된다.

세션 경계 판정이 이 훅의 급소라, "지난 세션에 적힌 [다음]"으로는 통과하지 않아야
한다(3의 대조군). transcript 시각은 UTC라 log.md의 기준 시간대 문자열과 그대로
비교하면 9시간 어긋나므로, 그 변환도 함께 본다.
"""
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_HOOK_SRC = Path(__file__).parent / "hooks" / "closing_guard.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("closing_guard", _HOOK_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_transcript(tmp_path: Path, user_text: str, started_utc: datetime) -> Path:
    """세션 시작 시각과 마지막 사용자 발화만 담은 최소 transcript(JSONL)."""
    path = tmp_path / "transcript.jsonl"
    rows = [
        {
            "type": "user",
            "timestamp": started_utc.isoformat().replace("+00:00", "Z"),
            "message": {"role": "user", "content": "작업 시작하자"},
        },
        {
            "type": "user",
            "timestamp": (started_utc + timedelta(minutes=30))
            .isoformat()
            .replace("+00:00", "Z"),
            "message": {"role": "user", "content": [{"type": "text", "text": user_text}]},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return path


def _make_task(home: Path, project: str, slug: str, log_body: str) -> Path:
    task_dir = home / ".namu" / "tasks" / project / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    (task_dir / "log.md").write_text(log_body, encoding="utf-8")
    return task_dir


def _run_hook(home: Path, payload: dict) -> subprocess.CompletedProcess:
    """실제 훅을 서브프로세스로 실행(HOME 격리 — 실제 ~/.namu를 건드리지 않는다)."""
    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PATH": "/usr/bin:/bin",
        "NAMU_MACHINE": "test",
        "NAMU_TZ": "Asia/Seoul",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _payload(tmp_path: Path, home: Path, transcript: Path, **extra) -> dict:
    project_dir = tmp_path / "proj-a"
    project_dir.mkdir(exist_ok=True)
    return {
        "cwd": str(project_dir),
        "transcript_path": str(transcript),
        "hook_event_name": "Stop",
        **extra,
    }


# --- 1. 마무리 신호 판별 -----------------------------------------------------


def test_closing_regex_matches_wrapup_and_ignores_ordinary_talk():
    hook = _load_hook()
    for text in ["마무리해", "오늘은 여기까지 하자", "세션 끝낼게", "이제 그만하자", "wrap up"]:
        assert hook._CLOSING_RE.search(text), text
    for text in ["이 코드 정리해줘", "다음 작업 이어서 하자", "테스트 돌려봐", "커밋해줘"]:
        assert not hook._CLOSING_RE.search(text), text


def test_hook_stays_silent_when_not_closing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[시작] 2026-07-27 09:10:00 test · 착수\n")
    transcript = _write_transcript(tmp_path, "이 코드 정리해줘", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- 2. 누락 시 block --------------------------------------------------------


def test_hook_blocks_when_closing_without_next_line(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)  # = 09:00 KST
    # 이번 세션에 기록은 남겼지만 [다음]이 없다
    _make_task(home, "proj-a", "namu-1", "# log\n[단계] 2026-07-27 09:30:00 test · 구현 완료\n")
    transcript = _write_transcript(tmp_path, "마무리하고 끝내자", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["decision"] == "block"
    assert "[다음]" in out["reason"]
    assert "namu-1" in out["reason"]  # 어느 task에 남기면 되는지 지목


def test_hook_block_reason_differs_when_nothing_recorded(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[시작] 2026-07-20 10:00:00 test · 지난 세션\n")
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    out = json.loads(result.stdout)
    assert out["decision"] == "block"
    assert "남긴 줄이 아예 없습니다" in out["reason"]


# --- 3. 남겼으면 통과 --------------------------------------------------------


def test_hook_passes_when_next_line_written_this_session(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)  # = 09:00 KST
    _make_task(
        home,
        "proj-a",
        "namu-1",
        "# log\n[다음] 2026-07-27 09:40:00 test · 여기서부터 이어서\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_passes_when_personal_pool_is_a_git_repo(tmp_path):
    """개인 풀(`~/.namu`)이 git 저장소여도 이번 세션 기록을 찾아야 한다.

    실물 사고(2026-08-03): 훅이 journal에 방 이름이 아니라 풀 경로
    `~/.namu/tasks/<방>`을 넘기고 있었다. journal은 받은 값을 project_key_for로
    다시 해석하는데, 그 함수는 `.git`을 찾아 위로 거슬러 오르므로 동기화를 켠
    사용자(=풀이 git 저장소)에게는 `.namu`가 방 이름으로 잡혀
    `~/.namu/tasks/.namu`를 뒤졌다. 그 폴더는 없으니 **무엇을 기록해도 0줄**이 되어
    훅이 항상 막았다. 기존 테스트는 임시 HOME에 `.git`이 없어 이 경로를 못 밟았다.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".namu").mkdir()
    (home / ".namu" / ".git").mkdir()  # 동기화를 켠 상태
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)  # = 09:00 KST
    _make_task(
        home,
        "proj-a",
        "namu-1",
        "# log\n[다음] 2026-07-27 09:40:00 test · 여기서부터 이어서\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_blocks_when_next_line_is_from_a_previous_session(tmp_path):
    """대조군 — 지난 세션의 [다음]은 이번 마무리를 면제하지 않는다(사고의 정확한 모양)."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)  # = 09:00 KST
    _make_task(
        home,
        "proj-a",
        "namu-1",
        "# log\n[다음] 2026-07-26 23:17:00 test · 어제 적어둔 지점\n"
        "[단계] 2026-07-27 09:30:00 test · 오늘 한 일\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    out = json.loads(result.stdout)
    assert out["decision"] == "block"


def test_hook_passes_when_task_closed_this_session(tmp_path):
    """[완료]/[중단]으로 task를 닫았으면 다음 지점이 필요 없다."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[완료] 2026-07-27 09:50:00 test · 종료\n")
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.stdout.strip() == ""


# --- 4. 무한 루프 방지 -------------------------------------------------------


def test_hook_passes_immediately_when_stop_hook_active(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[단계] 2026-07-27 09:30:00 test · 기록\n")
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(
        home, _payload(tmp_path, home, transcript, stop_hook_active=True)
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_survives_garbage_input(tmp_path):
    """훅은 무슨 일이 있어도 세션을 막지 않는다(exit 0)."""
    home = tmp_path / "home"
    home.mkdir()
    result = _run_hook(home, {"cwd": str(tmp_path), "transcript_path": "/nonexistent.jsonl"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_tool_result_blocks_do_not_trigger_closing(tmp_path):
    """도구 출력에 '마무리'가 들어 있다고 마무리로 오인하면 안 된다."""
    hook = _load_hook()
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": "마무리 단계 로그 출력"}],
        },
    }
    assert hook._entry_text(entry) == ""
