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

# `@mcp.tool(...)` 또는 `@tool(...)`(namu-tool-error-visibility — 안내문을 AI에게
# 전달하는 껍데기, mcp_server.py의 `tool()` 정의 참고) 바로 다음 줄의 `def 이름(`을
# 등록된 도구로 본다.
_REGISTERED = re.findall(r"@(?:mcp\.tool|tool)\([^\n]*\)\s*\ndef\s+(\w+)\s*\(", _SERVER_SOURCE)


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


# ---------------------------------------------------------------------------
# 올리기 소개가 그 연결에 실제로 있는 칸과 맞는가 (2026-08-07, 세 번째 base64 사고)
# ---------------------------------------------------------------------------
#
# stdio에는 `file_path` 칸이 있어 "디스크에 있는 파일을 올린다"가 참이다. 웹으로
# 여는 경로에 붙는 AI는 이 PC의 경로를 지어낼 수 없으므로 그 문장이 거짓이 된다.
# 거짓인 쪽에서 파일을 든 AI가 넣을 칸을 못 찾으면, 남는 길은 파일을 읽어 글자로
# 옮기는 것뿐이다 — 실제로 명령을 돌려 base64로 바꾸기 시작했고 회원은 몇 분을
# 기다리다 응답을 멈췄다. 도구에서 base64 칸을 없앤 것으로는 안 막힌다(인코딩이
# 도구의 인자가 아니라 그 앞 단계에서 일어나므로).

def _upload_line(text: str) -> str:
    return next(l for l in text.splitlines() if l.startswith("- namu_upload_file —"))


def test_stdio_still_offers_the_disk_path():
    # 터미널에서는 경로로 주는 것이 가장 빠른 길이다 — 이 안내가 사라지면 안 된다.
    assert "디스크" in _upload_line(record_input.server_instructions())


def test_the_web_upload_line_does_not_offer_a_disk_path():
    line = _upload_line(record_input.server_instructions(upload_takes_path=False))
    assert "디스크" not in line, f"없는 칸을 있다고 소개하고 있다: {line}"
    assert "namu_create_upload_ticket" in line, (
        "파일로 있는 것이 갈 곳을 안 알려 주면 AI는 파일을 읽는 쪽을 고른다"
    )


def test_the_web_paths_ask_for_the_no_path_line():
    # 소개문 함수만 고치고 부르는 쪽을 안 고치면 웹은 그대로 옛 문장을 받는다.
    src = Path(__file__).with_name("http_server.py").read_text(encoding="utf-8")
    assert "upload_takes_path=False" in src
