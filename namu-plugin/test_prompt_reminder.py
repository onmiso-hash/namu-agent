"""namu-62 ② — UserPromptSubmit 훅(prompt_reminder)이 상시 주의사항을 매 입력에
다시 올리는지 검증.

성질 3가지:
  1. `상시` 태그가 붙은 profile 사실만 올린다(profile 전체를 올리면 무거워서 안 읽힌다).
  2. 해당 사실이 하나도 없으면 완전한 침묵 — 아무 설정도 안 한 사용자의 매 입력에
     빈 헤더가 붙으면 안 된다.
  3. supersedes로 정정된 옛 사실은 올리지 않는다(profile.active와 같은 기준).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_HOOK_SRC = Path(__file__).parent / "hooks" / "prompt_reminder.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("prompt_reminder", _HOOK_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_profile(home: Path, docs: list[dict]) -> Path:
    import yaml

    path = home / ".namu" / "memory" / "profile.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join("---\n" + yaml.safe_dump(d, allow_unicode=True) for d in docs),
        encoding="utf-8",
    )
    return path


def _run_hook(home: Path) -> subprocess.CompletedProcess:
    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PATH": "/usr/bin:/bin",
        "NAMU_MACHINE": "test",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, str(_HOOK_SRC)],
        input=json.dumps({"prompt": "안녕", "hook_event_name": "UserPromptSubmit"}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _fact(fid: str, subject: str, statement: str, tags: list[str], supersedes=None) -> dict:
    return {
        "id": fid,
        "subject": subject,
        "statement": statement,
        "source": "테스트",
        "tags": tags,
        "supersedes": supersedes,
        "machine": "test",
        "verified_by": "human",
        "timestamp": "2026-07-27T00:00:00+00:00",
        "via": None,
    }


def test_injects_only_facts_tagged_always(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _write_profile(
        home,
        [
            _fact("A", "출력 형식", "핵심은 굵게, 전문용어는 풀어 쓴다", ["상시", "출력형식"]),
            _fact("B", "거주지", "서울에 산다", ["개인배경"]),
        ],
    )

    result = _run_hook(home)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "상시 주의" in ctx
    assert "전문용어는 풀어 쓴다" in ctx
    assert "서울에 산다" not in ctx  # 상시 태그 없는 사실은 안 올린다


def test_silent_when_no_always_facts(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _write_profile(home, [_fact("B", "거주지", "서울에 산다", ["개인배경"])])

    result = _run_hook(home)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_silent_when_no_profile_at_all(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    result = _run_hook(home)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_superseded_fact_is_not_injected(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _write_profile(
        home,
        [
            _fact("OLD", "출력 형식", "옛 규칙", ["상시"]),
            _fact("NEW", "출력 형식", "새 규칙", ["상시"], supersedes="OLD"),
        ],
    )

    result = _run_hook(home)
    ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "새 규칙" in ctx
    assert "옛 규칙" not in ctx


def test_render_caps_total_length():
    """매 입력에 붙는 글이라 상한이 있어야 한다 — 길면 정작 안 읽힌다."""
    hook = _load_hook()
    facts = [_fact(str(i), f"주제{i}", "가" * 500, ["상시"]) for i in range(10)]
    md = hook._render(facts)
    assert len(md) < hook._MAX_TOTAL_CHARS + 500
    assert "이하 생략" in md


def test_render_returns_none_for_empty():
    hook = _load_hook()
    assert hook._render([]) is None
    assert hook._render([_fact("A", "주제", "   ", ["상시"])]) is None
