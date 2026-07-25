"""config.BOWLS 그릇 레지스트리 자체 테스트 + 어긋남 방지 가드(namu-57 3단계).

가드 목적: BOWLS의 그릇 이름 집합이 db.py의 `_VALID_BOWLS`, mcp_server.py의
`_VALID_RECORD_BOWLS`와 어긋나면 테스트가 즉시 깨져서 알려준다 — 그릇을 한쪽에만
추가하는 실수 방지용(namu-56 4단계에서 memo 그릇이 곧 들어올 예정이라 특히 중요).
**이 테스트를 통과시키려고 db.py/mcp_server.py의 기존 상수·분기 로직을
레지스트리에서 파생시키는 리팩터링은 하지 않는다** — 지금은 세 곳의 이름 집합이
이미 같으므로 테스트만 추가하면 통과해야 한다.

mcp_server.py는 import 시점에 모듈 레벨로 `_ensure_db()`를 호출해 실제 `~/.namu`를
건드린다(namu-33 교훈 — test_mcp_bowl.py가 서브프로세스로 격리하는 이유와 동일).
그래서 여기서는 in-process import를 피하고, 소스를 ast로 파싱해
`_VALID_RECORD_BOWLS` 대입문의 값만 실행 없이 읽어온다. db.py는 import 시점에
부작용이 없어(순수 함수 정의만) 직접 import해도 안전하다.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import db as _db

_NAMU_PLUGIN_DIR = Path(__file__).parent


def _read_module_level_tuple_constant(module_path: Path, name: str) -> tuple:
    """module_path를 import하지 않고 소스만 파싱해, 최상위 `name = (...)` 대입문의
    우변을 ast.literal_eval로 안전하게 읽어온다(임의 코드 실행 없음)."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{module_path}에서 최상위 대입문 {name}을 찾지 못했습니다")


# ---------------------------------------------------------------------------
# BOWLS 레지스트리 자체 (① 스펙 확인)
# ---------------------------------------------------------------------------

def test_bowls_contains_exactly_three_bowls_in_declared_order():
    # 순서 보증: memory_sync._gitattributes_union_lines()가 기존 3줄(learnings+tasks)이
    # 앞서 나오게 의존하는 순서라 여기서도 못 박아 회귀를 잡는다.
    assert [bowl.name for bowl in cfg.BOWLS] == ["learnings", "tasks", "profile"]


def test_bowls_field_values_match_spec():
    by_name = {bowl.name: bowl for bowl in cfg.BOWLS}

    assert by_name["learnings"].git_patterns == ("memory/learnings.yaml",)
    assert by_name["tasks"].git_patterns == ("tasks/**/log.md", "tasks/*/.project")
    assert by_name["profile"].git_patterns == ("memory/profile.yaml",)

    for bowl in cfg.BOWLS:
        assert bowl.mutable is False
        assert bowl.merge == "union"
        assert bowl.web_exposed is True

    assert by_name["learnings"].cached is True
    assert by_name["tasks"].cached is False
    assert by_name["profile"].cached is False


def test_bowl_is_frozen():
    bowl = cfg.BOWLS[0]
    with pytest.raises(Exception):
        bowl.name = "changed"


# ---------------------------------------------------------------------------
# 어긋남 방지 가드 (③)
# ---------------------------------------------------------------------------

def test_bowls_names_match_db_valid_bowls():
    bowl_names = {bowl.name for bowl in cfg.BOWLS}
    assert bowl_names == set(_db._VALID_BOWLS)


def test_bowls_names_match_mcp_server_valid_record_bowls():
    bowl_names = {bowl.name for bowl in cfg.BOWLS}
    mcp_server_path = _NAMU_PLUGIN_DIR / "mcp_server.py"
    valid_record_bowls = _read_module_level_tuple_constant(
        mcp_server_path, "_VALID_RECORD_BOWLS"
    )
    assert bowl_names == set(valid_record_bowls)
