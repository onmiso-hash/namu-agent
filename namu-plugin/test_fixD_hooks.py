"""검사 계열 훅·세션 주입 훅의 작은 결함들(2026-09-25 리뷰 D) 회귀 시험.

1. 한글 윈도우 콘솔(cp949)에서 🌳·⚠를 찍다 예외가 나 알림이 소리 없이 사라지던 것
   — weekly_review_check·repo_sync_check·version_drift_check. `PYTHONIOENCODING=cp949`로
   흉내 낸다(test_session_recall_encoding.py와 같은 방법).
2. version_drift_check의 캐시가 어느 폴더에서 잰 결과인지 가리지 않아, 다른 폴더의
   결과를 30분 동안 그대로 돌려주던 것.
3. repo_sync_check가 NotebookEdit의 `notebook_path`를 읽지 않아 노트북을 고칠 때만
   검사가 빠지던 것.
4. session_inject가 표지 파일을 못 남기면 JSON을 두 번 찍던 것.

모든 시험은 HOME을 임시 폴더로 바꿔 실제 ~/.namu·~/.cache를 건드리지 않는다.
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

_HOOKS = Path(__file__).parent / "hooks"


def _env(home: Path, **덧붙임) -> dict:
    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    env.update(덧붙임)
    return env


def _run(hook: str, home: Path, *args, stdin: str = "", **env) -> subprocess.CompletedProcess:
    # 자식의 표준출력 인코딩은 env의 PYTHONIOENCODING이 정한다. 여기서는 바이트로 받아
    # 자식이 무엇으로 찍었든 그대로 본다.
    return subprocess.run(
        [sys.executable, str(_HOOKS / hook), *args],
        input=stdin.encode("utf-8"),
        capture_output=True,
        env=_env(home, **env),
        timeout=60,
    )


def _git(*args, cwd=None):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def 뒤처진_저장소(tmp_path):
    """원격보다 커밋 하나 뒤처진 저장소(tmp/b)를 만든다."""
    _git("init", "-q", "--bare", str(tmp_path / "remote.git"))
    _git("clone", "-q", str(tmp_path / "remote.git"), str(tmp_path / "a"))
    _git("commit", "-q", "--allow-empty", "-m", "1", cwd=tmp_path / "a")
    _git("push", "-q", "origin", "HEAD", cwd=tmp_path / "a")
    _git("clone", "-q", str(tmp_path / "remote.git"), str(tmp_path / "b"))
    _git("commit", "-q", "--allow-empty", "-m", "2", cwd=tmp_path / "a")
    _git("push", "-q", cwd=tmp_path / "a")
    return tmp_path / "b"


# ---------------------------------------------------------------------------
# 1. cp949 콘솔
# ---------------------------------------------------------------------------

def test_주간점검_알림이_cp949_콘솔에서도_나온다(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = _run("weekly_review_check.py", home, PYTHONIOENCODING="cp949")
    assert r.returncode == 0
    글 = r.stdout.decode("utf-8")
    assert "🌳 나무 주간 점검을 할 때가 됐습니다" in 글


def test_저장소_뒤처짐_알림이_cp949_콘솔에서도_나온다(tmp_path, 뒤처진_저장소):
    home = tmp_path / "home"
    home.mkdir()
    r = _run("repo_sync_check.py", home, "session",
             PYTHONIOENCODING="cp949", CLAUDE_PROJECT_DIR=str(뒤처진_저장소))
    assert r.returncode == 0
    글 = r.stdout.decode("utf-8")
    assert "⚠ 코드 저장소가 원격보다 뒤처져 있습니다" in 글
    assert "원격에 새 커밋 1개" in 글


def test_판_어긋남_알림이_cp949_콘솔에서도_나온다(tmp_path):
    """캐시에 적힌 결과를 찍게 해 ssh·원격 없이 출력 경로만 본다."""
    home = tmp_path / "home"
    (home / ".namu" / "config").mkdir(parents=True)
    (home / ".namu" / "config" / "version_targets.json").write_text("{}", encoding="utf-8")
    base = tmp_path / "work"
    base.mkdir()
    (home / ".cache").mkdir()
    (home / ".cache" / "claude-version-drift.json").write_text(json.dumps({
        "잰_때": time.time(), "기준": str(base),
        "줄": ["- **본체 사본**이 v0.1.1에 멈춰 있는데 본체 최신은 v0.1.2입니다 — 1판 뒤처졌습니다"],
    }, ensure_ascii=False), encoding="utf-8")

    r = _run("version_drift_check.py", home, PYTHONIOENCODING="cp949",
             CLAUDE_PROJECT_DIR=str(base))
    assert r.returncode == 0
    글 = r.stdout.decode("utf-8")
    assert "⚠ 배포된 판이 저장소 최신 판보다 뒤처져 있습니다" in 글
    assert "1판 뒤처졌습니다" in 글


# ---------------------------------------------------------------------------
# 2. 판 어긋남 캐시는 폴더마다 따로다
# ---------------------------------------------------------------------------

def test_다른_폴더에서_잰_캐시는_쓰지_않는다(tmp_path):
    """A 폴더에서 잰 '어긋남 없음'이 B 폴더의 진짜 어긋남을 30분 동안 삼키던 사고."""
    home = tmp_path / "home"
    (home / ".namu" / "config").mkdir(parents=True)
    (home / ".namu" / "config" / "version_targets.json").write_text(json.dumps(
        {"빌린_본체": [{"사본": "vendor/core", "저장소": "core", "이름": "본체 사본"}]},
        ensure_ascii=False), encoding="utf-8")

    A = tmp_path / "A"
    A.mkdir()
    B = tmp_path / "B"
    (B / "vendor").mkdir(parents=True)
    _git("init", "-q", "--bare", str(tmp_path / "core.git"))
    _git("clone", "-q", str(tmp_path / "core.git"), str(B / "core"))
    for 판 in ("v0.1.1", "v0.1.2"):
        _git("commit", "-q", "--allow-empty", "-m", 판, cwd=B / "core")
        _git("tag", 판, cwd=B / "core")
    _git("push", "-q", "origin", "HEAD", "--tags", cwd=B / "core")
    _git("clone", "-q", str(tmp_path / "core.git"), str(B / "vendor" / "core"))
    _git("checkout", "-q", "v0.1.1", cwd=B / "vendor" / "core")

    먼저 = _run("version_drift_check.py", home, CLAUDE_PROJECT_DIR=str(A),
                PYTHONIOENCODING="utf-8")
    assert 먼저.stdout.decode("utf-8").strip() == ""       # A에는 볼 것이 없다

    이어서 = _run("version_drift_check.py", home, CLAUDE_PROJECT_DIR=str(B),
                  PYTHONIOENCODING="utf-8")
    글 = 이어서.stdout.decode("utf-8")
    assert "본체 사본" in 글 and "1판 뒤처졌습니다" in 글

    캐시 = json.loads((home / ".cache" / "claude-version-drift.json").read_text(encoding="utf-8"))
    assert 캐시["기준"] == str(B)


# ---------------------------------------------------------------------------
# 3. NotebookEdit
# ---------------------------------------------------------------------------

def test_노트북을_고칠_때도_저장소_뒤처짐을_묻는다(tmp_path, 뒤처진_저장소):
    home = tmp_path / "home"
    home.mkdir()
    payload = {"tool_name": "NotebookEdit",
               "tool_input": {"notebook_path": str(뒤처진_저장소 / "분석.ipynb")}}
    r = _run("repo_sync_check.py", home, "pretool",
             stdin=json.dumps(payload, ensure_ascii=False), PYTHONIOENCODING="cp949")
    assert r.returncode == 0
    나온것 = json.loads(r.stdout.decode("utf-8"))
    assert 나온것["hookSpecificOutput"]["permissionDecision"] == "ask"


# ---------------------------------------------------------------------------
# 4. session_inject — 표지를 못 남겨도 JSON은 한 덩어리
# ---------------------------------------------------------------------------

def _session_inject(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("session_inject_fixD", _HOOKS / "session_inject.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 실제 설치본·기억 저장소를 건드리지 않게 바깥으로 닿는 곳을 모두 갈아 끼운다
    monkeypatch.setattr(mod, "heal_mcp_config", lambda root: False)
    monkeypatch.setattr(mod, "_ensure_db", lambda cfg: None)
    가짜_cfg = types.SimpleNamespace(NAMU_DB_PATH=str(tmp_path / "namu.db"), NAMU_MACHINE="test")
    monkeypatch.setitem(sys.modules, "config", 가짜_cfg)
    monkeypatch.setitem(sys.modules, "memory_sync", types.SimpleNamespace(sync_pull=lambda: None))
    monkeypatch.setitem(sys.modules, "session_context", types.SimpleNamespace(
        build_context_markdown=lambda conn, machine, project_dir: "🌳 브리핑"))
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: str(tmp_path))
    return mod


def test_표지를_못_남겨도_JSON을_한_번만_찍는다(tmp_path, monkeypatch, capsys):
    mod = _session_inject(monkeypatch, tmp_path)
    # 대화 id에 없는 하위 폴더를 넣어 표지 파일 만들기가 실패하게 한다
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(
        read=lambda: json.dumps({"conversationId": "없는폴더/대화"})))
    monkeypatch.setattr(sys, "argv", ["session_inject.py"])
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **kw: None, raising=False)

    with pytest.raises(SystemExit):
        mod.main()

    나온것 = capsys.readouterr().out.strip()
    assert json.loads(나온것) == {"injectSteps": [{"ephemeralMessage": "🌳 브리핑"}]}


def test_표지를_남기면_두_번째는_빈_JSON이다(tmp_path, monkeypatch, capsys):
    mod = _session_inject(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(
        read=lambda: json.dumps({"conversationId": "c1"})))
    monkeypatch.setattr(sys, "argv", ["session_inject.py"])
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **kw: None, raising=False)

    with pytest.raises(SystemExit):
        mod.main()
    첫번째 = capsys.readouterr().out.strip()
    with pytest.raises(SystemExit):
        mod.main()
    두번째 = capsys.readouterr().out.strip()

    assert "injectSteps" in json.loads(첫번째)
    assert json.loads(두번째) == {}


# ---------------------------------------------------------------------------
# 5. namu_tasks_push 사본 두 벌이 어긋나지 않는다
# ---------------------------------------------------------------------------

_공유_시작 = "import memory_sync as ms\n"


def _공유_구간(path: Path) -> str:
    """두 사본이 같아야 하는 구간 — memory_sync 불러오기부터 끝까지.

    그 위(모듈 설명·sys.path 계산)는 '경로 계산만 다르다'고 문서가 약속한 구간이라
    비교에서 뺀다(test_two_statusline_copies_do_not_drift와 같은 방식).
    """
    text = path.read_text(encoding="utf-8")
    assert _공유_시작 in text, f"{path}에 공유 구간 시작 표시가 없다"
    return text.split(_공유_시작, 1)[1]


def test_tasks_push_사본_두_벌의_로직이_같다():
    루트 = Path(__file__).parent.parent / "scripts" / "namu_tasks_push.py"
    동봉 = Path(__file__).parent / "scripts" / "namu_tasks_push.py"
    assert _공유_구간(루트) == _공유_구간(동봉), (
        "namu_tasks_push 사본 2개의 로직부가 어긋났다 — 설치형 사용자가 실행하는 것은 "
        "동봉 사본이다. 루트 사본을 동봉 사본으로 복사하고 상단 설명·sys.path만 되돌려라."
    )
