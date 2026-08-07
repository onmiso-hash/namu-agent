"""올리기 도구에 base64 칸이 **없어야 한다**는 것을 못박는다.

## 왜 시험으로까지 막나

2026-08-07, 이 칸을 필수에서 선택으로만 낮추고 설명에 "글자 파일은 원문을 넣고
base64로 바꾸지 마세요"라고 굵게 적었다. 그런데 웹에서 `.md` 파일 하나를 올리자
붙은 AI가 **그래도 base64로 바꾸기 시작했고**, 회원은 몇 분을 기다리다 응답을
멈췄다.

같은 결함을 이 도구에서 이미 겪었다(`body`를 필수로 뒀다가 재시도 폭주). 거기서
얻은 것이 **"설명이 아니라 칸의 모양이 결정한다"**였다. 칸이 있으면 쓰인다.

그래서 다음에 누군가 "하위 호환을 위해 하나쯤 남겨 두자"고 되돌리지 못하도록
여기서 막는다. 큰 파일은 올리기 링크(`namu_create_upload_ticket`)로 간다.

받기 쪽 `force_base64`는 다른 이야기라 여기서 막지 않는다 — 기본값이 꺼짐이고
AI가 명시적으로 켜야만 동작하므로 저절로 골라지지 않는다.
"""
import os
import subprocess
import sys
from pathlib import Path

_NAMU_PLUGIN_DIR = Path(__file__).resolve().parent

_PROBE = """
import sys
sys.path.insert(0, {plugin_dir!r})
import mcp_server
import inspect
params = list(inspect.signature(mcp_server.namu_upload_file).parameters)
print('PARAMS', ','.join(params))
"""


def _upload_params(tmp_path) -> list:
    """`~/.namu`를 건드리지 않도록 별도 프로세스에서 도구의 칸 목록만 읽어 온다."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.pop("NAMU_HOME", None)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(plugin_dir=str(_NAMU_PLUGIN_DIR))],
        cwd=str(_NAMU_PLUGIN_DIR), env=env, capture_output=True, text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    line = [x for x in result.stdout.splitlines() if x.startswith("PARAMS")][0]
    return line.split(" ", 1)[1].split(",")


def test_the_upload_tool_has_no_base64_field(tmp_path):
    params = _upload_params(tmp_path)

    assert "content_base64" not in params, (
        "올리기 도구에 base64 칸이 되살아났다 — 칸이 있으면 붙은 AI가 그것을 쓰고, "
        "회원 화면은 몇 분째 멈춘 것처럼 보인다(2026-08-07 실사용). 큰 파일은 "
        "namu_create_upload_ticket으로 보낸다."
    )


def test_the_upload_tool_still_takes_a_path_and_plain_text(tmp_path):
    params = _upload_params(tmp_path)

    # 디스크 경로가 가장 좋은 길이다 — 파일이 AI의 출력을 한 글자도 거치지 않는다.
    assert "file_path" in params
    assert "content_text" in params


def test_the_upload_path_never_decodes_base64():
    """칸 이름만 지우고 몸통에서 몰래 되살리는 것까지 막는다."""
    src = (_NAMU_PLUGIN_DIR / "mcp_server.py").read_text(encoding="utf-8")
    body = src.partition("def namu_upload_file(")[2].partition("\n@mcp.tool()")[0]

    assert body, "namu_upload_file을 찾지 못했다 — 이 시험이 헛돌고 있다"
    assert "b64decode" not in body
