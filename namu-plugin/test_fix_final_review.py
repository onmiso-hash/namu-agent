"""최종 검토(2026-09-25)에서 나온 이음새 결함 두 가지.

① 서버가 드라이브 뿌리(`/`)에서 뜨면 `tasks_root_for`가 빈 방 이름을 거절하면서
   `namu_recall` 전체가 실패했다 — 리뷰 A·B 수정이 맞물린 자리.
② 메모 쓰기가 깨진 파일을 빈 목록으로 읽어 "새 한 장"으로 덮어쓸 수 있었다.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg  # noqa: E402
import memo  # noqa: E402

_PLUGIN = Path(__file__).parent

_PROBE = """
import sys
sys.path.insert(0, {plugin!r})
import mcp_server
assert mcp_server._cwd_project() is None
assert mcp_server._default_search_project(None) is None
out = mcp_server.namu_recall()
assert isinstance(out, dict), out
try:
    mcp_server._resolve_record_project(None, None)
except ValueError as exc:
    assert "project를 명시" in str(exc), exc
else:
    raise AssertionError("뿌리 폴더에서 기록 방이 정해져 버렸다")
print("OK")
"""


def test_recall_survives_server_started_at_filesystem_root(tmp_path):
    home = tmp_path / "home"
    (home / ".namu" / "memory").mkdir(parents=True)
    (home / ".namu" / "memory" / "learnings.yaml").write_text("", encoding="utf-8")
    env = dict(os.environ, HOME=str(home))
    env.pop("NAMU_HOME", None)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(plugin=str(_PLUGIN))],
        cwd="/", env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def _paths(tmp_path: Path) -> "cfg.DataPaths":
    return cfg.DataPaths(
        learnings_yaml=tmp_path / "l.yaml", profile_yaml=tmp_path / "p.yaml",
        db_path=tmp_path / "n.db", memo_yaml=tmp_path / "memo.yaml",
    )


@pytest.mark.parametrize("broken", [
    "<<<<<<< HEAD\n- id: A\n=======\n- id: B\n>>>>>>> theirs\n",  # 병합 도중의 충돌 표시
    "id: A\nsummary: 목록이 아닌 한 장\n",                         # 목록이 아닌 문서
])
def test_memo_write_refuses_unreadable_file_instead_of_overwriting(tmp_path, broken):
    paths = _paths(tmp_path)
    paths.memo_yaml.write_text(broken, encoding="utf-8")
    with pytest.raises(ValueError, match="쓰지 않았습니다"):
        memo.add(summary="새 메모", body="본문", paths=paths)
    with pytest.raises(ValueError, match="쓰지 않았습니다"):
        memo.remove("A", paths=paths)
    # 파일은 한 글자도 바뀌지 않았다 — 붙여 둔 메모를 잃지 않는다.
    assert paths.memo_yaml.read_text(encoding="utf-8") == broken


def test_memo_write_on_missing_or_empty_file_still_works(tmp_path):
    paths = _paths(tmp_path)
    memo.add(summary="첫 메모", body="본문", paths=paths)
    assert [e["summary"] for e in memo.load_all(paths)] == ["첫 메모"]
    paths.memo_yaml.write_text("", encoding="utf-8")
    memo.add(summary="빈 파일 뒤", body="본문", paths=paths)
    assert [e["summary"] for e in memo.load_all(paths)] == ["빈 파일 뒤"]
