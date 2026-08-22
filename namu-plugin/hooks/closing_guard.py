#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "tzdata>=2024.1", "typing-extensions>=4.0"]
# ///
"""Stop 훅 — "마무리해"로 세션을 끊을 때 `[다음]` 줄 누락을 막는다(namu-62 ①).

왜 필요한가: 마무리의 본체는 교훈 기록이 아니라 **`[다음]` 줄 갱신**이다. 교훈만
길게 적고 `[다음]`을 옛날 것으로 두면 다음 세션의 브리핑이 이미 끝난 일을 남은
일로 제시하고, 브리핑은 출처를 의심하지 않으므로 **틀린 지시를 확신을 갖고
실행한다**(2026-07-26 실제 사고). 사람의 다짐으로 막던 것을 기계가 검사한다.

동작: 사용자의 마지막 말이 마무리 신호일 때만 개입한다. 이번 세션에 **어느 방의**
어느 task든 `[다음]`(또는 task를 닫는 `[완료]`/`[중단]`) 줄이 들어갔으면 조용히
통과, 없으면 한 번 block해서 남기게 한다. `stop_hook_active`면 즉시 통과한다 —
재차 block하면 무한 루프가 된다.

**왜 열려 있는 폴더의 방만 보지 않는가**(2026-08-23 실사고): 일한 방과 세션을 연
폴더는 같지 않다. 마스터 지휘석(`project/`)에서 열고 서브에이전트를 보내 일을
시키면 기록은 일한 방(`namu-cloud-routing` 등)에 남는데, 훅이 지휘석 방만 뒤져
`줄이 아예 없습니다`로 막았다 — **규정대로 일했는데 막힌 것이다**. 반대 구멍도
같은 뿌리다: 지휘석 방에만 남기면 정작 일한 방이 비어도 통과했다. 그래서 방으로
좁히지 않고 개인 풀 전체를 합쳐 본다.

어떤 에러가 나도 exit 0 (훅이 세션을 인질로 잡으면 안 된다).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 마무리 신호. "정리"는 단독으로 쓰면 오탐이 많아(코드 정리 등) 넣지 않는다.
_CLOSING_RE = re.compile(
    r"(마무리|마치자|끝내자|끝냅|종료하|세션\s*끝|오늘은?\s*여기까지|그만하자|"
    r"wrap\s*up|끝내고|접자)",
    re.IGNORECASE,
)

# 마무리 선언은 그 말 자체가 메시지 전부일 때가 대부분이다("마무리해",
# "오늘은 여기까지 하자"). 이보다 훨씬 긴 메시지에서 패턴이 걸리면, 사용자가
# 다른 곳의 문구(예: 앱 화면에 뜬 안내문)를 그대로 붙여넣어 질문한 것일 가능성이
# 높다 — 2026-08-08 실물 오탐: AI 안내원이 띄운 "오늘은 여기까지입니다..."
# 한도 초과 안내문을 그대로 인용해 "이런 문구가 뜬다"고 물었을 뿐인데 마무리로
# 오인해 세션을 막았다.
_CLOSING_SIGNAL_MAX_LEN = 40

# 이 줄들이 있으면 "이어갈 지점을 남겼다"로 본다. [완료]/[중단]은 task 자체가
# 닫힌 것이라 다음 지점이 필요 없다.
_SATISFYING_TAGS = ("다음", "완료", "중단")


def _is_closing_signal(text: str) -> bool:
    """마무리 패턴이 있고, 그 패턴이 메시지 전체를 거의 다 차지할 때만 True.

    긴 글 속에 우연히(또는 인용문으로) 패턴 글자가 섞여 있는 경우를 걸러낸다.
    """
    text = text.strip()
    return bool(text) and len(text) <= _CLOSING_SIGNAL_MAX_LEN and bool(_CLOSING_RE.search(text))


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _transcript_entries(transcript_path: str | None) -> list[dict]:
    """transcript(JSONL)를 줄 단위로 읽는다. 깨진 줄은 건너뛴다."""
    if not transcript_path:
        return []
    entries = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        return []
    return entries


def _entry_text(entry: dict) -> str:
    """transcript 항목에서 사용자가 실제로 친 텍스트만 뽑는다.

    content는 문자열이거나 블록 리스트다. 도구 결과 블록(tool_result)은 사용자가
    한 말이 아니므로 제외한다 — 포함하면 도구 출력에 '마무리'가 들어 있다는
    이유로 오작동한다.
    """
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def _last_user_text(entries: list[dict]) -> str:
    for entry in reversed(entries):
        if entry.get("type") == "user" or (entry.get("message") or {}).get("role") == "user":
            text = _entry_text(entry)
            if text.strip():
                return text
    return ""


def _session_start_ts(entries: list[dict], cfg) -> str | None:
    """세션 첫 항목의 시각을 log.md와 같은 형식(`YYYY-MM-DD HH:MM:SS`, 기준
    시간대)으로 돌려준다. transcript 시각은 UTC ISO8601이라 그대로 비교하면
    9시간 어긋난다(namu-57 5단계와 같은 함정).
    """
    for entry in entries:
        raw = entry.get("timestamp")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = cfg.local_tz()
        if tz is not None:
            dt = dt.astimezone(tz)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return None


def _lines_since(since_ts: str, machine: str | None) -> tuple[list[str], list[str]]:
    """(이번 세션에 줄이 들어간 `방/task`, 그중 [다음]류가 들어간 `방/task`).

    journal()이 이미 "여러 log.md를 시간순으로 합치고 since로 자르는" 조회라
    파일을 직접 훑지 않는다(namu-57 1단계).

    **방 이름을 넘기지 않는다** — `project=None`이면 개인 풀의 모든 방을 합친다
    (실측 확인). 일한 방이 열려 있는 폴더와 다를 수 있기 때문이며, 근거는 이
    파일 맨 위 독스트링의 2026-08-23 사고다.

    범위를 넓힌 대신 **기계 도장으로 좁힌다**. 넓히기만 하면 남이 남긴 무관한
    줄이 이 세션의 마무리로 잘못 인정될 수 있는데, 실제로 그럴 수 있는 경로는
    다른 기계(웹 컨테이너·미니PC)가 남긴 줄이 세션 도중 pull로 딸려 들어와
    `since_ts` 창 안에 앉는 경우다. 그건 이 기계의 산출이 아니므로 뺀다.
    같은 기계에서 세션 둘이 동시에 도는 경우는 남지만, 그건 넓히기 전에도
    (같은 폴더의 두 세션이 이미 한 방을 공유했으므로) 똑같이 있던 구멍이라
    이 변경이 넓힌 것이 아니다.

    machine이 안 찍힌 줄은 **통과시킨다**(옛 형식 — namu-51은 시각만, namu-39는
    machine 생략). 지금 쓰는 모든 기록 경로는 `cfg.NAMU_MACHINE`을 반드시 찍으므로
    창 안에서 도장 없는 줄이 나올 일은 사실상 없지만, 만에 하나 나왔을 때
    걸러내면 **영영 막히는** 쪽으로 틀린다. 두 방향 중 그쪽이 훨씬 나쁘다.
    """
    import task_resolve

    touched: list[str] = []
    satisfied: list[str] = []
    for entry in task_resolve.journal(project=None, since=since_ts):
        line_machine = entry.get("machine")
        if machine and line_machine and line_machine != machine:
            continue
        slug = entry.get("task_slug") or ""
        if not slug:
            continue
        # 방이 여럿이므로 슬러그만으로는 어디에 남기라는 건지 알 수 없다.
        where = f"{entry.get('project') or '?'}/{slug}"
        if where not in touched:
            touched.append(where)
        if entry.get("tag") in _SATISFYING_TAGS and where not in satisfied:
            satisfied.append(where)
    return touched, satisfied


def _block_reason(project: str, touched: list[str]) -> str:
    head = (
        "⛔ 마무리 전 확인 — 이번 세션에서 `[다음]` 줄을 남기지 않았습니다.\n\n"
        "마무리의 본체는 교훈 기록이 아니라 `[다음]` 줄 갱신입니다. 이게 낡으면 "
        "다음 세션의 브리핑이 이미 끝난 일을 남은 일로 제시하고, 브리핑은 출처를 "
        "의심하지 않으므로 **틀린 지시를 확신을 갖고 실행합니다**(실제 사고 이력).\n\n"
    )
    if touched:
        targets = ", ".join(touched)
        body = (
            f"이번 세션에 기록이 들어간 task(`방/task`): {targets}\n"
            "지금 남기세요 — `namu_record(bowl='tasks', "
            "project='<위 목록의 방 이름>', task='<그 방의 task>', tag='다음', "
            "text='<다음 세션이 정확히 어디서부터 시작하면 되는지>')`\n"
            "**방 이름은 일한 방으로 적으세요** — 지금 열려 있는 폴더"
            f"(`{project}`)와 다를 수 있습니다.\n"
            "task가 진짜로 끝났다면 `tag='완료'`(또는 '중단')로 닫으세요."
        )
    else:
        body = (
            "이번 세션에는 작업 로그에 남긴 줄이 아예 없습니다.\n"
            "진행한 일이 있으면 `namu_record(bowl='tasks', "
            f"project='{project}', task='<슬러그>', tag='다음', text='<재진입 지점>')`로 "
            "남기고, 정말 남길 것이 없는 세션이면 그렇다고 한 줄로 답한 뒤 마치세요."
        )
    return head + body


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        data = _read_stdin_json()

        # 이미 이 훅 때문에 한 번 이어붙인 턴이면 다시 막지 않는다(무한 루프 방지).
        if data.get("stop_hook_active"):
            sys.exit(0)

        entries = _transcript_entries(data.get("transcript_path"))
        if not _is_closing_signal(_last_user_text(entries)):
            sys.exit(0)

        import config as cfg  # tz 기준 통일 + 기계 도장(NAMU_MACHINE)
        import task_resolve

        project_dir = data.get("cwd") or os.getcwd()
        # 조회에는 안 쓴다(아래 참고). 안내문에서 "지금 열려 있는 폴더"를 짚어
        # 주는 용도다. 방 이름은 basename이 아니라 project_key_for로 정한다 —
        # cwd가 하위 폴더면 basename이 방 이름과 달라진다(namu-73, 특례 0).
        project = task_resolve.project_key_for(project_dir)

        since_ts = _session_start_ts(entries, cfg)
        if since_ts is None:
            sys.exit(0)  # 시각을 모르면 판정하지 않는다(오작동보다 침묵이 낫다)

        # journal에 **방 이름을 넘기지 않는다** — 일한 방은 열려 있는 폴더와
        # 다를 수 있다(2026-08-23 사고, 맨 위 독스트링).
        #
        # 되살리지 말 것: 여기에 방을 다시 넘기게 되더라도 tasks_root_for()가 만든
        # 풀 경로(`~/.namu/tasks/<방>`)는 절대 넘기면 안 된다 — journal은 받은 값을
        # 다시 project_key_for로 해석하는데, 그 함수는 뿌리 표식(.git)을 찾아 위로
        # 거슬러 오르므로 개인 풀이 git 저장소일 때(=동기화를 켠 모든 사용자)
        # `.namu`가 방 이름으로 잡혀 `~/.namu/tasks/.namu`를 뒤진다. 그 폴더는
        # 없으니 **무엇을 기록해도 0줄**로 보이고, 이 훅은 항상 막는다(실측 재현).
        touched, satisfied = _lines_since(since_ts, cfg.NAMU_MACHINE)
        if satisfied:
            sys.exit(0)

        print(
            json.dumps(
                {"decision": "block", "reason": _block_reason(project, touched)},
                ensure_ascii=False,
            )
        )
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
