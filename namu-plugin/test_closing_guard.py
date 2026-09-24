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


def test_closing_signal_ignores_pattern_inside_a_long_pasted_message():
    """실물 오탐(2026-08-08) — 앱 안내문을 인용해 질문했을 뿐인데 마무리로 오인했다."""
    hook = _load_hook()
    pasted_question = (
        "이전 세션에서 namu cloud 에 ai 도우미 추가했거든? 그런데 API 연동시 리미트를 "
        "몇으로 설정했는지 벌써 한도가 도달했나봐.\n"
        "오늘은 여기까지입니다. 내일 다시 열립니다 — 그동안은 나무 안내서를 보시면 "
        "대부분 답이 있습니다. <--- 이런대답이 나오고 있어."
    )
    assert hook._CLOSING_RE.search(pasted_question)  # 글자 패턴 자체는 여전히 걸린다
    assert not hook._is_closing_signal(pasted_question)  # 그러나 마무리 신호로는 안 본다

    for text in ["마무리해", "오늘은 여기까지 하자", "세션 끝낼게", "이제 그만하자", "wrap up"]:
        assert hook._is_closing_signal(text), text
    for text in ["이 코드 정리해줘", "다음 작업 이어서 하자"]:
        assert not hook._is_closing_signal(text), text


# 실제 대화 기록에서 뽑은 마무리 선언(2026-08-23 ~ 09-24). 패턴을 고쳐도 이것들은 계속
# 잡혀야 한다.
_REAL_CLOSINGS = [
    "세션 마무리해... 새로운 세션에서 작업을 이어가자",
    "이 세션 마무리해",
    "이제 세션 종료할께.",
    "이세션 마무리하자",
    "지금은 여기서 마무리하자",
    "이 세션 마무리 해줘.",
    "이 세션 마무리",
    "수고했어. 이번세션 마무리하자",
    "그럼 긴급 작업은 여기까자 하고, 이제 마무리 하자.",
    "이 세션은 마무리 하기로 했으니 여기서 끝내자",
    "알겠어. 그럼 좀있다 다시 보자 이제 이 세션 끝낸다.",
    "이 세션 종료할게",
    "이 세션 종료하자",
    "세션 새로 열게 여기서 마무리하자",
]

# 일을 시키는 말이거나 마무리를 묻는 질문 — 마무리 선언이 아니다(2026-09-25 리뷰 D).
_NOT_CLOSINGS = [
    "테스트 끝내고 커밋해줘",
    "서버 종료하고 다시 띄워줘",
    "이거 끝내고 배포까지 가자",
    "컨테이너 종료하지 마",
    "프로세스 종료하고 로그 보여줘",
    "그럼 이제 이 세션 마무리 완료 된거야?",
    "혹시 이미 마무리하자~에 마무리 작업이 정의되어 있지 않아?",
]


def test_real_closing_phrases_are_still_caught():
    hook = _load_hook()
    for text in _REAL_CLOSINGS:
        assert hook._is_closing_signal(text), text


def test_work_instructions_and_questions_are_not_closing():
    """'끝내고'·'종료하'가 일 시키는 말에 흔히 들어가 멈출 때마다 막히던 오탐."""
    hook = _load_hook()
    for text in _NOT_CLOSINGS:
        assert not hook._is_closing_signal(text), text


def test_hook_stays_silent_after_a_work_instruction(tmp_path):
    """작업 지시를 마친 턴에서 막지 않는다(리뷰 D의 closing_false_block 재현)."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    transcript = _write_transcript(tmp_path, "테스트 끝내고 커밋해줘", started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_stays_silent_when_closing_phrase_is_inside_a_long_pasted_message(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[시작] 2026-07-27 09:10:00 test · 착수\n")
    pasted_question = (
        "이전 세션에서 namu cloud 에 ai 도우미 추가했거든? 그런데 API 연동시 리미트를 "
        "몇으로 설정했는지 벌써 한도가 도달했나봐.\n"
        "오늘은 여기까지입니다. 내일 다시 열립니다 — 그동안은 나무 안내서를 보시면 "
        "대부분 답이 있습니다. <--- 이런대답이 나오고 있어."
    )
    transcript = _write_transcript(tmp_path, pasted_question, started)

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


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


def test_hook_passes_immediately_when_grok_stop_hook_active(tmp_path):
    """그록은 stopHookActive(camelCase)로 재진입을 알린다."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1", "# log\n[단계] 2026-07-27 09:30:00 test · 기록\n")
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(
        home, _payload(tmp_path, home, transcript, stopHookActive=True)
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_blocks_from_grok_session_file_when_transcript_is_absent(tmp_path):
    """그록 Stop 입력에는 클로드 대화 기록이 없다. 세션 파일의 마지막 말을 본다."""
    from urllib.parse import quote

    home = tmp_path / "home"
    home.mkdir()
    project_dir = tmp_path / "proj-a"
    project_dir.mkdir()
    _make_task(home, "proj-a", "namu-1", "# log\n[단계] 2026-07-27 09:30:00 test · 구현 완료\n")

    session_id = "sess-grok-1"
    session_dir = home / "grok" / "sessions" / quote(str(project_dir), safe="") / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "summary.json").write_text(
        json.dumps({"created_at": "2026-07-27T00:00:00.638925099Z"}),
        encoding="utf-8",
    )
    rows = [
        {"type": "user", "content": [{"type": "text", "text": "작업 시작하자"}]},
        {
            "type": "user",
            "synthetic_reason": "system_reminder",
            "content": [{"type": "text", "text": "오늘은 여기까지 하자 라고 안내문이 길다"}],
        },
        {"type": "user", "content": [{"type": "text", "text": "마무리해"}]},
    ]
    (session_dir / "chat_history.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "GROK_HOME": str(home / "grok"),
        "PATH": "/usr/bin:/bin",
        "NAMU_MACHINE": "test",
        "NAMU_TZ": "Asia/Seoul",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input=json.dumps({
            "cwd": str(project_dir),
            "sessionId": session_id,
            "hook_event_name": "Stop",
        }),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["decision"] == "block"
    assert "namu-1" in out["reason"]


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


# --- 5. 일한 방과 열려 있는 폴더가 다를 때 (2026-08-23 실사고) ----------------
#
# 훅은 열려 있는 폴더의 방 하나만 조회했다. 마스터 지휘석에서 세션을 열고
# 서브에이전트를 다른 방으로 보내 일을 시키는 규정대로 했더니, 기록은 일한 방에
# 정상적으로 남았는데도 "남긴 줄이 아예 없습니다"로 막혔다. 아래 두 시험은 반드시
# 짝으로 본다 — 이 훅은 잘못 고치면 영영 막거나 영영 안 막는다.


def _payload_for(tmp_path: Path, transcript: Path, room: str, **extra) -> dict:
    """cwd를 특정 방 이름으로 지정한 payload(방 이름 = 폴더 basename)."""
    project_dir = tmp_path / room
    project_dir.mkdir(exist_ok=True)
    return {
        "cwd": str(project_dir),
        "transcript_path": str(transcript),
        "hook_event_name": "Stop",
        **extra,
    }


def test_hook_passes_when_work_was_logged_in_another_room(tmp_path):
    """통과해야 할 때 통과한다 — 지휘석에서 열었고 기록은 일한 방에 남았다."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)  # = 09:00 KST
    # 열려 있는 폴더의 방: 이번 세션에 남긴 줄이 없다
    _make_task(home, "master-post", "master-1", "# log\n[시작] 2026-07-20 10:00:00 test · 지난 세션\n")
    # 실제로 일한 방: 서브에이전트가 [완료]를 남겼다
    _make_task(
        home,
        "worker-room",
        "cloud-9",
        "# log\n[완료] 2026-07-27 09:40:00 test · 라우팅 고치고 닫음\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload_for(tmp_path, transcript, "master-post"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout


def test_hook_still_blocks_when_no_room_has_a_next_line(tmp_path):
    """막혀야 할 때 막힌다 — 방을 여럿 두고도 어디에도 [다음]류가 없다.

    범위를 넓힌 변경이 '영영 안 막는' 쪽으로 무너지지 않았는지 보는 대조군이다.
    다른 방의 [다음]은 **지난 세션** 것이라 이번 마무리를 면제하지 못한다.
    """
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "master-post", "master-1", "# log\n[단계] 2026-07-27 09:20:00 test · 확인만 함\n")
    _make_task(
        home,
        "worker-room",
        "cloud-9",
        "# log\n[다음] 2026-07-26 23:17:00 test · 어제 적어둔 지점\n"
        "[단계] 2026-07-27 09:30:00 test · 오늘 한 일\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload_for(tmp_path, transcript, "master-post"))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["decision"] == "block"
    # 어느 방의 어느 task인지 함께 지목한다 — 방이 여럿이라 슬러그만으로는 못 찾는다
    assert "worker-room/cloud-9" in out["reason"], out["reason"]
    assert "master-post/master-1" in out["reason"], out["reason"]


def test_hook_ignores_next_line_stamped_by_another_machine(tmp_path):
    """다른 기계가 남긴 줄은 이 세션의 마무리로 인정하지 않는다.

    방 전체로 넓힌 대가로 생기는 오인 경로가 이것이다 — 웹 컨테이너·미니PC가
    남긴 줄이 세션 도중 pull로 딸려 들어와 since 창 안에 앉을 수 있다.
    """
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "master-post", "master-1", "# log\n[단계] 2026-07-27 09:20:00 test · 확인만 함\n")
    _make_task(
        home,
        "worker-room",
        "cloud-9",
        "# log\n[다음] 2026-07-27 09:40:00 web · 웹에서 남긴 남의 줄\n",
    )
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload_for(tmp_path, transcript, "master-post"))
    out = json.loads(result.stdout)
    assert out["decision"] == "block"


def test_hook_counts_an_unstamped_line_rather_than_blocking_forever(tmp_path):
    """기계 도장이 없는 옛 형식 줄은 통과시킨다 — 걸러내면 영영 막히는 쪽으로 틀린다."""
    home = tmp_path / "home"
    home.mkdir()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "worker-room", "cloud-9", "# log\n[다음] 2026-07-27 09:40:00 이어서 여기부터\n")
    transcript = _write_transcript(tmp_path, "마무리해", started)

    result = _run_hook(home, _payload_for(tmp_path, transcript, "master-post"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout


# --- 이어 연 긴 세션 ---------------------------------------------------------


def _write_rows(tmp_path: Path, rows: list[tuple[datetime, str]]) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps({
        "type": "user",
        "timestamp": t.isoformat().replace("+00:00", "Z"),
        "message": {"role": "user", "content": text},
    }, ensure_ascii=False) for t, text in rows) + "\n", encoding="utf-8")
    return path


def test_resumed_session_needs_a_next_line_after_the_previous_closing(tmp_path):
    """--resume으로 이어 연 세션은 같은 대화 기록에 이어 적힌다. 며칠 전 마무리 때
    남긴 [다음]이 오늘의 마무리를 통과시키면 안 된다(리뷰 D resumed_span)."""
    home = tmp_path / "home"
    home.mkdir()
    첫날 = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)      # 09:00 KST
    _make_task(home, "proj-a", "namu-1",
               "# log\n[다음] 2026-07-25 09:40:00 test · 첫날 마무리 때 남긴 줄\n"
               "[단계] 2026-07-27 10:10:00 test · 오늘 한 일\n")
    transcript = _write_rows(tmp_path, [
        (첫날, "작업 시작하자"),
        (첫날 + timedelta(minutes=30), "마무리해"),                 # 09:30 KST
        (첫날 + timedelta(days=2, hours=1), "이어서 하자"),          # 07-27 10:00 KST
        (첫날 + timedelta(days=2, hours=1, minutes=30), "마무리해"),
    ])

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    out = json.loads(result.stdout)
    assert out["decision"] == "block"


def test_resumed_session_passes_with_a_next_line_after_the_previous_closing(tmp_path):
    """대조군 — 앞선 마무리 뒤에 새 [다음]을 남겼으면 통과한다."""
    home = tmp_path / "home"
    home.mkdir()
    첫날 = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
    _make_task(home, "proj-a", "namu-1",
               "# log\n[다음] 2026-07-25 09:40:00 test · 첫날 마무리 때 남긴 줄\n"
               "[다음] 2026-07-27 10:20:00 test · 오늘 남긴 줄\n")
    transcript = _write_rows(tmp_path, [
        (첫날, "작업 시작하자"),
        (첫날 + timedelta(minutes=30), "마무리해"),
        (첫날 + timedelta(days=2, hours=1), "이어서 하자"),
        (첫날 + timedelta(days=2, hours=1, minutes=30), "마무리해"),
    ])

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_repeated_closing_accepts_the_line_left_in_reply_to_the_first(tmp_path):
    """마무리를 2분 간격으로 거듭 말한 경우(실제 기록에 있다) — 첫 선언에 답해 남긴
    [다음]을 인정해야 한다. 그 사이에 한 일은 그 답뿐이다."""
    home = tmp_path / "home"
    home.mkdir()
    시작 = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)            # 09:00 KST
    _make_task(home, "proj-a", "namu-1",
               "# log\n[다음] 2026-07-27 09:31:00 test · 첫 선언에 답해 남긴 줄\n")
    transcript = _write_rows(tmp_path, [
        (시작, "작업 시작하자"),
        (시작 + timedelta(minutes=30), "세션 마무리해줘"),
        (시작 + timedelta(minutes=32), "세션 마무리해줘"),
    ])

    result = _run_hook(home, _payload(tmp_path, home, transcript))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_feedback_is_not_taken_as_the_user_resuming_work(tmp_path):
    """앞선 마무리를 이 훅이 막으면 "Stop hook feedback" 글이 사용자 자리(isMeta)에
    들어간다. 그것을 '일을 다시 시작한 말'로 집으면 기준이 마무리 직후로 당겨져,
    그때 남긴 옛 [다음]이 나흘 뒤의 마무리를 통과시킨다(최종 검토 재현)."""
    home = tmp_path / "home"
    home.mkdir()
    _make_task(home, "proj-a", "namu-1",
               "# log\n[다음] 2026-09-20 11:01:00 test · 막힌 뒤 남긴 줄\n"
               "[단계] 2026-09-24 10:30:00 test · 나흘 뒤 한 일\n")
    rows = [
        {"type": "user", "timestamp": "2026-09-20T01:00:00Z",
         "message": {"role": "user", "content": "작업 시작하자"}},
        {"type": "user", "timestamp": "2026-09-20T02:00:00Z",
         "message": {"role": "user", "content": "마무리하자"}},
        {"type": "user", "timestamp": "2026-09-20T02:00:05Z", "isMeta": True,
         "message": {"role": "user", "content": "Stop hook feedback:\n⛔ 마무리 전 확인"}},
        {"type": "user", "timestamp": "2026-09-24T01:00:00Z",
         "message": {"role": "user", "content": "이어서 테스트 고쳐줘"}},
        {"type": "user", "timestamp": "2026-09-24T03:00:00Z",
         "message": {"role": "user", "content": "마무리하자"}},
    ]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")

    hook = _load_hook()
    import config as cfg
    assert hook._previous_closing_ts(rows, cfg) == "2026-09-24 10:00:00"

    result = _run_hook(home, _payload(tmp_path, home, path))
    assert json.loads(result.stdout)["decision"] == "block"
