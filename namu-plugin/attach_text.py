"""글자 파일인지 가리는 판정 — 개인 주소와 나무 클라우드가 같이 쓴다.

## 왜 가리나

파일 내용을 base64로 실어 나르면 그 글자열을 **붙은 AI가 한 자씩 써야 한다.**
6KB짜리 문서 하나가 8,100자였고, 서버가 7.4초 걸리는 동안 AI가 그 글자를 뱉는 데
몇 분이 걸렸다(2026-08-07 실측). 글자 파일이면 원문 그대로 주고받으면 이 과정
자체가 없어진다.

## 왜 둘 다 봐야 하나

확장자만 믿으면 `.md` 이름을 단 바이너리가 왔을 때 깨진 글자를 저장하게 된다.
거꾸로 UTF-8 해독만 믿으면 짧은 바이너리가 우연히 해독에 성공해 글자로 잘못
분류된다. 그래서 **확장자·크기·해독 셋 다** 통과해야 글자로 본다.

이 판정이 두 벌이 되면 같은 파일을 한쪽은 원문으로, 다른 쪽은 base64로 다루는
어긋남이 생긴다 — 그래서 이 작은 모듈 하나에 모아 둔다.
"""
from __future__ import annotations

import posixpath

# 원문 그대로 주고받을 수 있는 크기의 상한. 이보다 크면 글자 파일이라도 티켓으로
# 보낸다 — AI가 100KB를 글자로 뱉는 것 자체가 이미 느리기 때문이다.
MAX_INLINE_TEXT_BYTES = 100 * 1024

TEXT_EXTENSIONS = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx",
    ".py", ".java", ".jsp", ".xml", ".sql", ".sh", ".bash",
    ".toml", ".ini", ".cfg", ".conf", ".env", ".log", ".rst",
    ".c", ".h", ".cpp", ".hpp", ".go", ".rs", ".rb", ".php",
    ".kt", ".swift", ".scala", ".pl", ".lua", ".r", ".vue", ".svelte",
    ".gitignore", ".dockerignore",
})


def has_text_extension(path: str) -> bool:
    """이름만 보고 글자 파일일 법한지. 확장자가 없는 이름은 거짓으로 본다."""
    tail = posixpath.basename(path or "")
    dot = tail.rfind(".")
    if dot <= 0:
        # 앞이 점으로 시작하는 이름(`.gitignore`)은 통째로 확장자로 본다.
        return tail.lower() in TEXT_EXTENSIONS
    return tail[dot:].lower() in TEXT_EXTENSIONS


def as_text(path: str, content: bytes) -> "str | None":
    """원문 그대로 실어 보낼 수 있으면 그 글자, 아니면 None.

    셋 다 통과해야 한다 — 확장자가 글자 목록에 있고, 상한 이하이고, UTF-8로
    해독된다. 하나라도 어긋나면 None이며, 호출부는 티켓 방식으로 안내한다.
    """
    if len(content) > MAX_INLINE_TEXT_BYTES:
        return None
    if not has_text_extension(path):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None
