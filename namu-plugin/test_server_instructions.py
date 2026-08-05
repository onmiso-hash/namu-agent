"""서버 소개문이 실제 서버와 갈라지지 않는지 (namu-65 후속 ②).

소개문은 클라이언트(AI)가 도구를 부르기 전에 읽는 유일한 안내다. 여기 적힌 도구
이름이나 그릇 설명이 실제와 어긋나면 **잘못된 그릇에 담는 사고**가 그대로 돌아온다 —
namu-65의 발단이 바로 설명과 동작의 어긋남이었다.

mcp_server.py는 import 시점에 실제 `~/.namu`를 건드리므로(모듈 레벨 `_ensure_db()`)
여기서는 import하지 않고 **소스 글자만 읽어** 등록된 도구 이름을 뽑는다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import record_input

_SERVER_SOURCE = (Path(__file__).parent / "mcp_server.py").read_text(encoding="utf-8")

# `@mcp.tool(...)` 바로 다음 줄의 `def 이름(`을 등록된 도구로 본다.
_REGISTERED = re.findall(r"@mcp\.tool\([^\n]*\)\s*\ndef\s+(\w+)\s*\(", _SERVER_SOURCE)


def test_source_scan_found_the_tools():
    # 정규식이 헛돌면 아래 대조가 통과해도 아무것도 검사하지 않은 것이 된다.
    assert len(_REGISTERED) >= 5
    assert "namu_record" in _REGISTERED


def test_instructions_list_exactly_the_registered_tools():
    named = [name for name, _ in record_input._TOOL_LINES]
    assert sorted(named) == sorted(_REGISTERED)


def test_instructions_are_wired_into_the_server():
    assert "instructions=record_input.server_instructions()" in _SERVER_SOURCE


def test_instructions_explain_every_bowl():
    text = record_input.server_instructions()
    for bowl in cfg.BOWL_NAMES:
        assert bowl in text
        assert cfg.bowl_label(bowl) in text


def test_instructions_reuse_the_tool_description():
    # 손으로 옮겨 적었는지 여부를 여기서 못 박는다 — 포함이 깨지면 두 글이 갈라진 것이다.
    text = record_input.server_instructions()
    assert record_input.tool_description() in text


# ---------------------------------------------------------------------------
# 내주는 도구만 소개하기 (2026-08-05)
#
# 웹으로 여는 두 경로(셀프호스팅 http_server / 클라우드)는 도구를 3종으로 거른다.
# 그런데 소개문은 거르지 않아 **없는 도구 4개를 있다고 소개**하고 있었다. 붙은 AI가
# 없는 이름을 부르면 실패한다. 아래 시험이 그 갭의 재발을 막는다.
# ---------------------------------------------------------------------------
_WEB_TOOLS = frozenset({"namu_recall", "namu_search", "namu_record"})


def test_subset_lists_only_the_given_tools():
    text = record_input.server_instructions(_WEB_TOOLS)
    for name in _WEB_TOOLS:
        assert f"- {name} —" in text
    for name, _ in record_input._TOOL_LINES:
        if name not in _WEB_TOOLS:
            assert f"- {name} —" not in text, f"{name}은(는) 안 내주는데 소개하고 있다"


def test_subset_says_why_the_rest_is_missing():
    # 이유를 안 적으면 AI가 "고장난 서버"로 보고 없는 이름을 계속 시도한다.
    text = record_input.server_instructions(_WEB_TOOLS)
    assert "플러그인으로 설치했을 때만" in text
    for name, _ in record_input._TOOL_LINES:
        if name not in _WEB_TOOLS:
            assert name in text  # 빠진 도구의 이름 자체는 밝힌다


def test_no_argument_keeps_every_tool():
    # stdio 경로는 거르지 않으므로 지금까지와 같아야 한다.
    text = record_input.server_instructions()
    for name, _ in record_input._TOOL_LINES:
        assert f"- {name} —" in text
    assert "플러그인으로 설치했을 때만" not in text


def test_record_rules_survive_in_the_subset():
    assert record_input.tool_description() in record_input.server_instructions(_WEB_TOOLS)


def test_http_server_feeds_its_exposed_list_into_the_instructions():
    # 거르는 목록과 소개문이 같은 인자에서 나오는지 소스로 못 박는다.
    src = Path(__file__).with_name("http_server.py").read_text(encoding="utf-8")
    assert "set_instructions(mcp_server.mcp, HTTP_EXPOSED_TOOLS)" in src
