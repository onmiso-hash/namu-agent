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

**hooks.json에 timeout 90초를 적은 이유**: 마무리 선언을 알아본 턴에서는 이 훅이
세션 측정을 **직접**(떼어내지 않고) 하고 원격에 올린다(`_measure_session_now`). 올리기
한 번은 memory_sync의 단계별 상한을 다 더하면 add·diff·commit 5초씩, push 10초, 실패
시 복구 pull 10초와 재시도 push 10초로 최악 45초이고, 그 앞에 `uv run`이 의존성을
챙기는 시간이 붙는다. 한도를 적지 않으면 호스트 기본값에 맡기게 되는데 그 값은
호스트·판마다 달라, 올리기가 중간에 끊길 수 있다(측정값은 이미 파일에 있어 다음
올리기가 싣고 가지만, 그 사이 다른 기계에서는 이 세션이 안 보인다). 마무리 아닌
턴에서는 대화 기록 한 장을 읽고 곧바로 끝나므로 한도를 넉넉히 잡아도 기다림은 없다.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import hook_input

# 마무리 신호. "정리"는 단독으로 쓰면 오탐이 많아(코드 정리 등) 넣지 않는다.
#
# '끝내고'와 '종료하'는 2026-09-25에 뺐다. 둘 다 일을 시키는 말에 흔히 들어간다 —
# "테스트 끝내고 커밋해줘", "서버 종료하고 다시 띄워줘", "컨테이너 종료하지 마". 그런
# 말을 마치고 멈출 때마다 마무리로 오인해 `[다음]` 줄을 요구하며 막았다. 그날 남아
# 있던 대화 기록의 마무리 선언을 전부 대 보니 '끝내고'로 마무리한 것은 한 건도 없었고,
# '종료'가 든 선언 셋("이 세션 종료하자"·"이 세션 종료할게"·"이제 세션 종료할께.")은
# 모두 '세션'과 붙어 있었다. 그래서 '종료'는 세션을 가리킬 때만 받는다 — 덤으로 옛
# 패턴('종료하')이 놓치던 뒤의 둘도 잡힌다.
_CLOSING_RE = re.compile(
    r"(마무리|마치자|끝내자|끝냅|세션\s*(을\s*|은\s*)?종료|세션\s*끝|"
    r"오늘은?\s*여기까지|그만하자|wrap\s*up|접자)",
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

    물음표로 끝나는 말은 선언이 아니라 질문이다 — 실제 기록에 "그럼 이제 이 세션
    마무리 완료 된거야?", "혹시 이미 마무리하자~에 마무리 작업이 정의되어 있지
    않아?"가 있었고, 둘 다 마무리를 묻거나 이야기한 것이지 끝내자는 말이 아니었다.
    """
    text = text.strip()
    if not text or len(text) > _CLOSING_SIGNAL_MAX_LEN:
        return False
    if text.endswith(("?", "？")):
        return False
    return bool(_CLOSING_RE.search(text))


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


def _is_human_entry(entry: dict) -> bool:
    """사람이 친 말이 들어 있을 수 있는 사용자 항목인가.

    `isMeta`는 사람이 아니라 프로그램이 사용자 자리에 넣은 글이다 — 이 훅이 막을 때
    돌려보낸 "Stop hook feedback" 글도 여기에 든다. `isSidechain`은 서브에이전트에게
    보낸 지시다. 둘 다 사람의 말로 세면, 훅이 막은 직후의 자기 글을 "사람이 일을
    다시 시작한 말"로 집어 기준 시각이 틀어진다(2026-09-25 최종 검토에서 재현).
    나이테(`naite.사람_발화인가`)가 사람 발화를 가를 때와 같은 기준이다.
    """
    if entry.get("isMeta") or entry.get("isSidechain"):
        return False
    return entry.get("type") == "user" or (entry.get("message") or {}).get("role") == "user"


def _last_user_text(entries: list[dict]) -> str:
    for entry in reversed(entries):
        if _is_human_entry(entry):
            text = _entry_text(entry)
            if text.strip():
                return text
    return ""


def _log_ts(raw, cfg) -> str | None:
    """transcript 시각 하나를 log.md와 같은 형식(`YYYY-MM-DD HH:MM:SS`, 기준
    시간대)으로 바꾼다. 읽을 수 없으면 None. transcript 시각은 UTC ISO8601이라
    그대로 비교하면 9시간 어긋난다(namu-57 5단계와 같은 함정).
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = cfg.local_tz()
    if tz is not None:
        dt = dt.astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _session_start_ts(entries: list[dict], cfg) -> str | None:
    """세션 첫 항목의 시각을 log.md와 같은 형식으로 돌려준다."""
    for entry in entries:
        ts = _log_ts(entry.get("timestamp"), cfg)
        if ts is not None:
            return ts
    return None


def _previous_closing_ts(entries: list[dict], cfg) -> str | None:
    """앞선 마무리 뒤에 일이 다시 시작된 시각. 앞선 마무리가 없으면 None.

    `--resume`으로 이어 연 세션은 같은 대화 기록에 이어 적힌다. 그러면 며칠 전
    마무리 때 남긴 `[다음]` 줄도 "세션 시작 뒤"에 들어 있어, 오늘 다시 일하고
    마무리할 때 그 옛 줄이 통과 근거가 되어 버렸다 — 오늘 한 일의 `[다음]`은 하나도
    없는데 통과한다.

    **기준을 앞선 마무리 선언의 시각으로 잡으면 안 된다.** 그 선언에 답해 남긴
    `[다음]`은 선언보다 뒤에 적히므로 여전히 통과 근거가 된다 — 고치려던 구멍이
    그대로 남는다(처음 그렇게 고쳤다가 시험으로 확인했다). 그래서 앞선 마무리 **다음에
    사람이 처음 한 말**, 곧 일이 다시 시작된 때를 기준으로 삼는다. 그 뒤에 남긴 줄만
    이번 마무리의 근거다.

    예외: 앞선 마무리 뒤에 사람이 한 말이 지금의 마무리 선언뿐이면(마무리를 거듭 말한
    경우 — 실제 기록에 "세션 마무리해줘"가 2분 간격으로 두 번 있다) 앞선 선언의 시각을
    기준으로 한다. 그 사이에 한 일은 선언에 답한 것뿐이므로 그때 남긴 줄을 인정한다.

    사람 발화는 `_entry_text`로 글이 나오는 사용자 항목이다 — 도구 결과만 든 항목은
    글이 비어 저절로 빠지고, 프로그램이 넣은 글(`isMeta`)은 `_is_human_entry`가 뺀다. 마지막 사람 발화가 지금 판정 중인 마무리 선언이다.
    """
    said = [
        entry for entry in entries
        if _is_human_entry(entry) and _entry_text(entry).strip()
    ]
    earlier = said[:-1]
    for i in range(len(earlier) - 1, -1, -1):
        if not _is_closing_signal(_entry_text(earlier[i])):
            continue
        # earlier[i]가 앞선 마무리. 그 다음 사람 말이 있으면 그것이 일이 다시 시작된 때다.
        resumed = earlier[i + 1] if i + 1 < len(earlier) else earlier[i]
        return _log_ts(resumed.get("timestamp"), cfg)
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


# `[다음]` 줄은 그 task가 열려 있는 동안 세션마다 브리핑에 전문으로 실린다. 그래서
# 마무리 안내에서 길이를 함께 요구한다 — 안내가 없으면 "다음 세션이 알아야 할 것"을
# 그 줄에 통째로 적게 되고, 실제로 2026-09-10에 1,550자짜리 줄이 나와 브리핑 71줄
# 가운데 30줄을 혼자 차지했다. 상한 자체는 mcp_server.NEXT_LINE_LIMIT이 거절로 막는다.
_NEXT_LINE_LENGTH_NOTE = (
    "`[다음]` 줄에는 **다음 세션이 무엇부터 할지만 요약해서** 적으세요(300자 이내). "
    "이 줄은 세션마다 브리핑에 전문 그대로 실리므로, 길게 적으면 그만큼을 매 세션 "
    "다시 읽습니다. 그날의 경위·측정값·설계 내용은 같은 task에 `status='기록'`으로 "
    "한 건 더 남겨 그 `body` 칸에 넣으세요 — `body`는 브리핑에 실리지 않고 "
    "`namu_search`로 꺼내므로 길이 제한이 없고, 다른 PC와 웹에서도 읽힙니다. "
    "**\"경위는 그 기록에 있다\"고 가리키는 문장은 `[다음]` 줄에 직접 쓰지 마세요** — "
    "나무가 브리핑에 `상세:` 줄로 붙입니다. 직접 쓰면 매번 같은 문장이 300자를 "
    "나눠 써 정작 요약이 들어갈 자리가 줄어듭니다.\n"
)


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
            + _NEXT_LINE_LENGTH_NOTE
            + "task가 진짜로 끝났다면 `tag='완료'`(또는 '중단')로 닫으세요."
        )
    else:
        body = (
            "이번 세션에는 작업 로그에 남긴 줄이 아예 없습니다.\n"
            "진행한 일이 있으면 `namu_record(bowl='tasks', "
            f"project='{project}', task='<슬러그>', tag='다음', text='<재진입 지점>')`로 "
            "남기고, 정말 남길 것이 없는 세션이면 그렇다고 한 줄로 답한 뒤 마치세요.\n"
            + _NEXT_LINE_LENGTH_NOTE.rstrip("\n")
        )
    return head + body


def _measure_session_now(data: dict) -> None:
    """마무리 선언을 알아본 그 자리에서 세션을 재고 남기고 올린다.

    왜 여기서 하는가. 세션 종료 훅(`session_end_naite.py`)은 재고 올리는 일을
    떼어낸 일꾼에게 맡기는데, `/exit`로 끝내면 프로그램이 그 일꾼을 기다리지 않고
    끝나 **올리기가 끊긴다**. 2026-09-12 실측: `/exit`로 끝낸 세션 2건은 둘 다
    커밋(14:53:44, 16:23:56)만 남고 동기화 로그에 올리기 시도가 한 줄도 없었으며,
    프로그램이 스스로 끝난 1건만 16:31:03에 2.28초를 써서 올리기까지 마쳤다.
    마무리 시점은 세션이 살아 있어 그렇게 끊길 일이 없고, 시간 제약도 없다.

    재는 규칙과 남기는 규칙은 종료 훅의 `일하기`를 그대로 부른다 — 규칙이 두 벌이
    되면 같은 대화도 어디서 넣었느냐에 따라 숫자가 달라진다. 여기서 이미 남겼으면
    뒤이은 종료 훅은 `sessions.already_recorded`가 막아 같은 값을 두 번 쌓지 않는다
    (그 함수는 발화 수로 판정하므로, 마무리 선언 뒤 대화가 더 오가면 그때는 늘어난
    값으로 다시 남는다 — 합산하는 쪽이 session_id마다 마지막 항목만 세므로 겹치지
    않는다).

    "훅은 기록하지 않는다"는 원칙의 예외인 근거는 종료 훅과 같다 — 적는 것이 판단이
    아니라 기계가 잰 숫자와 사람이 실제로 한 말의 원문이고, 들어가는 그릇도 교훈이
    아니라 세션 측정 그릇이다. **이 훅도 교훈은 적지 않는다.**

    어떤 에러가 나도 조용히 지나간다 — 마무리를 막으면 안 된다.
    """
    transcript_path = hook_input.text(data, "transcript_path", "transcriptPath")
    session_id = hook_input.text(data, "session_id", "sessionId")
    if not transcript_path or not session_id:
        return
    try:
        import importlib.util

        # hooks 폴더는 패키지가 아니라 파일 경로로 불러온다. 모듈 이름을 명시하므로
        # 그쪽 `__main__` 가드가 걸려 main()은 돌지 않는다.
        path = Path(__file__).parent / "session_end_naite.py"
        spec = importlib.util.spec_from_file_location("session_end_naite", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.일하기({
            "transcript_path": transcript_path,
            "session_id": session_id,
            "reason": "closing_signal",
        })
    except Exception:
        pass


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        # 훅 입력은 UTF-8로 온다. 한글 윈도우는 표준입력을 cp949로 읽어, 한글이 든 대화
        # 기록 경로가 깨지면 기록을 못 열고 검사가 소리 없이 빠진다(repo_sync_check와 같다).
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        data = _read_stdin_json()

        # 이미 이 훅 때문에 한 번 이어붙인 턴이면 다시 막지 않는다(무한 루프 방지).
        # 그록은 stopHookActive, 클로드는 stop_hook_active.
        if hook_input.flag_true(data, "stop_hook_active", "stopHookActive"):
            sys.exit(0)

        transcript_path = hook_input.text(data, "transcript_path", "transcriptPath")
        session_id = hook_input.text(data, "session_id", "sessionId")
        if transcript_path:
            data["transcript_path"] = transcript_path
        if session_id:
            data["session_id"] = session_id

        entries = _transcript_entries(transcript_path)
        user_text = _last_user_text(entries)
        project_dir = hook_input.text(data, "cwd", "workspaceRoot") or os.getcwd()
        # 그록 Stop 입력에는 클로드식 대화 기록이 없다. 사람 말이 비면 그록 세션
        # 파일에서 마지막 발화와 세션 시작 시각을 읽는다.
        if not user_text:
            session_dir = hook_input.grok_session_dir(session_id, project_dir)
            if session_dir is not None:
                user_text = hook_input.grok_last_user_text(session_dir)
                created = hook_input.grok_created_at(session_dir)
                if user_text and created:
                    entries = [{
                        "timestamp": created,
                        "type": "user",
                        "message": {"role": "user", "content": user_text},
                    }]
        if not _is_closing_signal(user_text):
            sys.exit(0)

        # `[다음]` 줄 검사보다 먼저 한다 — 막는 쪽으로 판정되면 대화가 이어지는데,
        # 그때 세션이 그대로 끝나 버려도 측정값은 이미 남아 있어야 한다.
        _measure_session_now(data)

        import config as cfg  # tz 기준 통일 + 기계 도장(NAMU_MACHINE)
        import task_resolve

        project_dir = project_dir or os.getcwd()
        # 조회에는 안 쓴다(아래 참고). 안내문에서 "지금 열려 있는 폴더"를 짚어
        # 주는 용도다. 방 이름은 basename이 아니라 project_key_for로 정한다 —
        # cwd가 하위 폴더면 basename이 방 이름과 달라진다(namu-73, 특례 0).
        project = task_resolve.project_key_for(project_dir)

        since_ts = _session_start_ts(entries, cfg)
        if since_ts is None:
            sys.exit(0)  # 시각을 모르면 판정하지 않는다(오작동보다 침묵이 낫다)
        # 이어 연 긴 세션에서는 앞선 마무리 뒤 일이 다시 시작된 때부터만 본다
        # (_previous_closing_ts 참고).
        # 두 시각 모두 같은 형식의 글자라 글자 비교가 곧 시각 비교다.
        previous_closing = _previous_closing_ts(entries, cfg)
        if previous_closing is not None:
            since_ts = max(since_ts, previous_closing)

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
