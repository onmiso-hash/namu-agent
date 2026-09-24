"""훅 stdin에서 클로드·그록이 함께 보내는 칸을 고른다.

그록은 같은 값을 camelCase로 넣고(`sessionId`, `stopHookActive`), 클로드는
snake_case로 넣는다(`session_id`, `stop_hook_active`). 어느 쪽이 왔든 같은
함수로 읽는다. 그록 세션 파일(`chat_history.jsonl`)은 클로드 대화 기록과
형식이 달라서, 마무리 검사가 사람 발화를 찾을 때만 이쪽을 본다.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote


def text(data: dict, *keys: str) -> str:
    """있는 칸 중 첫 비어 있지 않은 문자열."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def flag_true(data: dict, *keys: str) -> bool:
    """그 칸이 진짜 참일 때만 참. 없으면 거짓(없는 것을 참으로 읽지 않는다)."""
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if value is True or value == "true":
            return True
    return False


def grok_data_root() -> Path:
    """그록 데이터 뿌리. `GROK_HOME`이 있으면 그 경로, 없으면 `~/.grok`."""
    override = os.environ.get("GROK_HOME")
    if override:
        return Path(override)
    return Path.home() / ".grok"


def _normalize_iso(raw: str) -> str:
    """소수 초가 6자리를 넘으면 자른다. 그록 summary의 나노초를 fromisoformat이 거절한다."""
    return re.sub(r"(\.\d{6})\d+", r"\1", raw)


def grok_session_dir(session_id: str, cwd: str) -> Path | None:
    """세션 id와 작업 폴더로 `~/.grok/sessions/.../<id>`를 찾는다. 없으면 None."""
    if not session_id:
        return None
    root = grok_data_root() / "sessions"
    if not root.is_dir():
        return None
    if cwd:
        encoded = quote(cwd, safe="")
        direct = root / encoded / session_id
        if direct.is_dir():
            return direct
    matches = [path for path in root.glob(f"*/{session_id}") if path.is_dir()]
    if len(matches) == 1:
        return matches[0]
    return None


def grok_last_user_text(session_dir: Path) -> str:
    """chat_history.jsonl에서 사람이 친 마지막 말. 합성 쪽지(system_reminder)는 뺀다."""
    path = session_dir / "chat_history.jsonl"
    if not path.is_file():
        return ""
    last = ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("type") != "user" or row.get("synthetic_reason"):
            continue
        content = row.get("content")
        parts: list[str] = []
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
        joined = "\n".join(parts).strip()
        if joined:
            last = joined
    return last


def grok_created_at(session_dir: Path) -> str:
    """summary.json의 세션 생성 시각. 없으면 빈 문자열."""
    path = session_dir / "summary.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    raw = data.get("created_at")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return _normalize_iso(raw.strip())
