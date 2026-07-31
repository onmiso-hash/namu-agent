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
