"""컨테이너가 원격(GitHub)에 못 닿을 때 재시작 루프에 빠지지 않는지(2026-09 검수 C-2).

검수 재현(repro_boot_offline.sh)을 뒤집었다: 예전에는 startup_sync가 원격 불통을
경고로 넘겨도 바로 다음 단계 `deploy/namu_cloud_sync_setup.py`가 결과 문장의
"실패"를 보고 exit 1 → entrypoint exit 1 → restart: always → 2026-08-16과 같은 루프.
지금은 network 실패만 있으면 exit 0 + startup_sync.json 경고, 로컬 wiring 실패만 exit 1.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg  # noqa: E402
import memory_sync as ms  # noqa: E402
import startup_sync  # noqa: E402

_WRAPPER = Path(__file__).resolve().parent.parent / "deploy" / "namu_cloud_sync_setup.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("namu_cloud_sync_setup_under_test", _WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, encoding="utf-8"
    )


@pytest.fixture()
def home(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    h = tmp_path / "home" / ".namu"
    subprocess.run(["git", "clone", "-q", str(origin), str(h)], check=True, capture_output=True)
    _git(h, "config", "user.email", "t@e")
    _git(h, "config", "user.name", "t")
    (h / "memory").mkdir()
    (h / "memory" / "learnings.yaml").write_text("- id: a\n", encoding="utf-8")
    _git(h, "add", "-A")
    _git(h, "commit", "-qm", "init")
    _git(h, "push", "-q", "-u", "origin", "main")
    monkeypatch.setattr(cfg, "NAMU_DATA_ROOT", h)
    monkeypatch.delenv("NAMU_SYNC", raising=False)
    return {"home": h, "origin": origin, "tmp": tmp_path}


def test_online_setup_exits_zero_without_warning(home):
    wrapper = _load_wrapper()
    assert wrapper.main([str(home["origin"])]) == 0
    assert startup_sync.read_status(home["home"]) is None


def test_offline_boot_does_not_exit_nonzero_and_leaves_warning(home):
    wrapper = _load_wrapper()
    assert wrapper.main([str(home["origin"])]) == 0
    gone = home["tmp"] / "origin_gone.git"
    home["origin"].rename(gone)  # GitHub 장애/토큰 만료 흉내

    assert startup_sync.main([str(home["home"])]) == 3  # 경고 후 계속(종전과 같음)
    rc = wrapper.main([str(home["origin"])])
    assert rc == 0, "원격 불통으로 exit 1이면 entrypoint가 멈추고 재시작 루프가 된다"

    status = startup_sync.read_status(home["home"])
    assert status is not None
    assert status["step"] == "sync_setup"
    assert "fetch" in status["reason"] or "push" in status["reason"]
    # 브리핑·recall 경고로 뜬다
    assert startup_sync.warning_markdown(home["home"]) is not None
    assert startup_sync.warning_text(home["home"]) is not None

    # 원격이 돌아오고 받아오기가 성공하면 경고가 사라진다
    gone.rename(home["origin"])
    (home["home"] / ".namu_sync").touch()
    assert ms.sync_pull() is True
    assert startup_sync.read_status(home["home"]) is None


def test_local_wiring_failure_stays_fatal(home, monkeypatch):
    """로컬 wiring 실패(fatal 칸)는 종전대로 exit 1 — 기록이 원격으로 갈 길 자체가 없다."""
    wrapper = _load_wrapper()
    monkeypatch.setattr(
        wrapper.memory_sync, "sync_setup_report",
        lambda url: {"text": "실패: git init 오류", "notes": ["실패"], "fatal": ["실패"], "network": []},
    )
    assert wrapper.main([str(home["origin"])]) == 1


def test_report_classifies_network_failures_structurally(home):
    home["origin"].rename(home["tmp"] / "gone.git")
    rep = ms.sync_setup_report(str(home["origin"]))
    assert rep["fatal"] == []
    assert any("fetch" in n for n in rep["network"])
    assert any("push" in n for n in rep["network"])
    # 사람이 읽는 문자열 API는 그대로다(mcp_server.namu_sync_setup)
    assert ms.sync_setup(str(home["origin"])).startswith("namu_sync_setup 완료:")
