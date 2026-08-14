"""기록 입력 검증 — config.FIELDS 선언에서 파생한다 (namu-65 구현 2단계).

**왜 별도 모듈인가.** 검증 규칙이 mcp_server.py의 분기문 안에 흩어져 있던 것이
사고의 구조적 원인이었다(learnings 경로가 `text`를 말없이 버렸다). 규칙을 한곳에
모으고 그릇별 차이는 `config.FIELDS` 표에서만 읽으면, 같은 결함이 옆 그릇에서
재발할 수 없다. 더불어 mcp_server.py는 import 시점에 실제 `~/.namu`를 건드리므로
(모듈 레벨 `_ensure_db()`) 그 안에 두면 테스트가 서브프로세스 격리를 강요당한다 —
여기는 순수 함수뿐이라 바로 import해 검사할 수 있다.

**설계 원칙 4** — 그릇이 받지 않는 칸이 오면 조용히 버리지도, 아무거나 받지도 않고
**거절하고 갈 곳을 알려준다.** 거절 메시지는 무엇이 잘못됐고 어떻게 고치는지를
한 문장으로 말한다(완료조건 8).
"""
from collections.abc import Iterable
from dataclasses import dataclass, field as _dc_field

import config as cfg

# 옛 `kind` 칸 → 그릇. kind는 없앤 칸이지만(설계서 4장) 옛 호출을 깨뜨리지 않기 위해
# 해석만은 종전 그대로 유지한다 — 거절은 기록 유실이 아니어도, 이미 돌고 있는 호출을
# 깨뜨리는 것은 이 작업의 목표가 아니다. mcp_server.py에도 같은 표가 있으나 3단계에서
# 그쪽을 지우고 이 모듈로 일원화한다.
_KIND_TO_BOWL = {"lesson": "learnings", "note": "learnings", "fact": "profile"}

# 참/거짓 칸의 거짓값은 "안 준 것"과 같게 본다. 도구 함수의 기본값(create=False)이
# 호출자가 명시한 값과 구분되지 않기 때문인데, 이걸 값으로 취급하면 쪽지에
# `create=False`가 딸려 들어온 것만으로 "쪽지는 create를 받지 않습니다"라는 엉뚱한
# 거절이 난다. 거짓은 아무 일도 하지 않으므로 무시해도 잃는 정보가 없다.
_FALSE_MEANS_ABSENT = ("create",)


@dataclass(frozen=True)
class RecordInput:
    """검증·이관을 마친 기록 입력.

    values는 **새 이름 기준**이고, 그 그릇이 받는 칸만 들어 있다.
    notices는 옛 이름을 어디로 옮겼는지 등 호출자에게 돌려줄 안내문이다 —
    옮겨놓고 알리지 않으면 그것도 조용한 유실이다(설계서 4장 끝문단).
    """

    bowl: str
    values: dict
    notices: list = _dc_field(default_factory=list)


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _bowl_list_ko(names) -> str:
    """그릇 이름들을 사람이 읽는 형태로: "교훈(learnings)·작업일지(tasks)"."""
    return "·".join(f"{cfg.bowl_label(n)}({n})" for n in names)


_COUNT_KO = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱"}


def _bowl_count_ko() -> str:
    """"네"/"다섯" — 그릇 개수를 세는 우리말. 레지스트리에서 파생시킨다.

    손으로 적으면 그릇이 늘 때 안내문만 옛 개수로 남는다(첨부 기록 그릇을 더할 때
    실제로 "네 그릇"이 여섯 곳에 박혀 있었다). 표기 없는 개수는 숫자로 떨어뜨린다.
    """
    n = len(cfg.BOWL_NAMES)
    return _COUNT_KO.get(n, str(n) + "개")


def _all_bowls_ko() -> str:
    return _bowl_list_ko(cfg.BOWL_NAMES)


def resolve_bowl(given: dict) -> tuple[str, list]:
    """어느 그릇인지 확정한다. 확정할 수 없으면 ValueError.

    그릇 생략은 허용하지 않는다(2026-07-31 사용자 결정). 옛 코드는 안 적으면 조용히
    교훈으로 보냈는데, 잘못 담겨도 아무도 모르는 그 경로가 바로 이 작업이 없애려는
    결함이다. 다만 옛 `kind`로 부르는 호출은 종전 해석을 유지해 깨지지 않게 한다.
    """
    notices: list = []
    bowl = given.get("bowl")
    kind = given.get("kind")

    if bowl is not None and bowl not in cfg.BOWL_NAMES:
        raise ValueError(
            f"'{bowl}'라는 그릇은 없습니다 — {_bowl_count_ko()} 그릇 중 하나를 "
            f"고르세요: {_all_bowls_ko()}."
        )

    if bowl is None:
        if kind is not None:
            inferred = _KIND_TO_BOWL.get(kind)
            if inferred is None:
                raise ValueError(
                    f"kind='{kind}'는 해석할 수 없습니다 — kind는 없앤 칸이니 "
                    f"bowl에 그릇을 직접 적으세요: {_all_bowls_ko()}."
                )
            notices.append(
                f"kind는 없앤 칸이라 이번에는 {cfg.bowl_label(inferred)}({inferred}) "
                f"그릇으로 해석했습니다 — 다음부터 bowl='{inferred}'로 적으세요."
            )
            return inferred, notices

        hint = cfg.suggest_bowl(given.keys())
        guidance = (
            f" 넣으신 칸을 보면 {cfg.bowl_label(hint)}({hint}) 같습니다."
            if hint
            else ""
        )
        raise ValueError(
            "bowl(어느 그릇에 담을지)을 적어야 합니다 — 안 적으면 기록이 엉뚱한 곳에 "
            f"쌓여도 아무도 모릅니다.{guidance} 고를 수 있는 그릇: {_all_bowls_ko()}."
        )

    if kind is not None:
        if bowl in ("tasks", "memo"):
            # 이 두 그릇은 lesson/note/fact 어디에도 속하지 않아 옛 코드도 kind를
            # 보지 않았다. 도구 기본값으로 kind가 딸려 들어오는 호출이 실제로 있어서,
            # 여기서 모순으로 보면 멀쩡한 호출이 거절된다.
            notices.append("kind는 없앤 칸이라 무시했습니다 — 그릇은 bowl로만 정합니다.")
            return bowl, notices
        inferred = _KIND_TO_BOWL.get(kind)
        if inferred is not None and inferred != bowl:
            raise ValueError(
                f"bowl='{bowl}'과 kind='{kind}'가 어긋납니다 — kind는 없앤 칸이니 "
                f"kind를 빼고 bowl만 적으세요(kind='{kind}'는 옛 {inferred} 그릇을 뜻합니다)."
            )
        notices.append("kind는 없앤 칸이라 무시했습니다 — 그릇은 bowl로만 정합니다.")

    return bowl, notices


def _apply_aliases(bowl: str, given: dict, notices: list) -> dict:
    """옛 이름을 새 이름으로 옮긴다. 모르는 이름은 버리지 않고 거절한다."""
    values: dict = {}
    for name, value in given.items():
        if name == "kind":  # resolve_bowl에서 이미 처리·안내됨
            continue
        if name in cfg.FIELD_NAMES:
            values[name] = value
            continue

        alias = cfg.resolve_field_alias(name, bowl)
        if alias is None:
            # 다른 그릇에서만 쓰던 옛 이름일 수 있다(예: 쪽지에 'tag'). "그런 칸 없음"으로
            # 끝내면 어디로 가야 하는지 알 수 없으므로 그 그릇을 짚어준다.
            other = tuple(
                b
                for entry in cfg.FIELD_ALIASES
                if entry.old == name
                for b in entry.bowls
            )
            if other:
                raise ValueError(
                    f"'{name}'은 {_bowl_list_ko(sorted(set(other)))} 그릇에서 쓰던 옛 "
                    f"이름이라 {cfg.bowl_label(bowl)}({bowl})에는 쓸 수 없습니다."
                )
            raise ValueError(
                f"'{name}'이라는 칸은 없습니다 — "
                f"{cfg.bowl_label(bowl)}({bowl}) 그릇이 받는 칸은 "
                f"{', '.join(sorted(cfg.allowed_fields(bowl)))}입니다."
            )
        if alias.new is None:
            notices.append(f"'{name}'은 없앤 칸이라 무시했습니다{_note_suffix(alias)}.")
            continue
        if alias.new in given:
            raise ValueError(
                f"'{name}'(옛 이름)과 '{alias.new}'(새 이름)를 함께 주셨습니다 — "
                f"'{alias.new}' 하나만 적으세요."
            )
        if alias.new in values:
            raise ValueError(
                f"'{name}'은 '{alias.new}'로 옮겨지는데 그 칸이 이미 채워져 있습니다 — "
                f"'{alias.new}' 하나만 적으세요."
            )
        values[alias.new] = value
        notices.append(
            f"'{name}'은 이제 '{alias.new}'입니다 — 그 칸으로 옮겨 저장했습니다"
            f"{_note_suffix(alias)}."
        )
    return values


def _note_suffix(alias) -> str:
    return f"({alias.note})" if alias.note else ""


def _reject_foreign_fields(bowl: str, values: dict) -> None:
    """그 그릇이 받지 않는 칸은 거절하고 갈 곳을 알려준다(설계 원칙 4)."""
    allowed = cfg.allowed_fields(bowl)
    for name in values:
        if name in allowed:
            continue
        elsewhere = tuple(b for b in cfg.bowls_accepting(name) if b != bowl)
        if elsewhere:
            raise ValueError(
                f"{cfg.bowl_label(bowl)}({bowl}) 그릇은 '{name}' 칸을 받지 않습니다 — "
                f"이 내용은 {_bowl_list_ko(elsewhere)} 그릇에서 쓰는 칸입니다."
            )
        raise ValueError(
            f"'{name}' 칸을 받는 그릇이 없습니다 — 내용을 body(원문·경위)에 넣으세요."
        )


def _first_sentence(desc: str) -> str:
    """설명의 첫 문장. 거절 메시지와 문서 표가 같은 한 줄을 쓰게 하는 단일 기준이다 —
    두 곳에서 따로 자르면 같은 칸이 화면마다 다르게 소개된다."""
    return desc.split(".")[0].strip()


def _check_required(bowl: str, values: dict) -> None:
    """필수 칸이 비면 거절한다. `생략` 한 단어는 채운 것으로 본다."""
    for name in sorted(cfg.required_fields(bowl)):
        if not _is_blank(values.get(name)):
            continue
        field = cfg.field_by_name(name)
        raise ValueError(
            f"{cfg.bowl_label(bowl)}({bowl}) 기록에는 '{name}'이 필요합니다 — "
            f"{_first_sentence(field.desc)}. 적을 게 정말 없으면 "
            f"'{cfg.OMITTED}' 한 단어를 넣으세요(예: {field.example})."
        )


# `생략`으로 비울 수 없는 자리. 쪽지는 붙여둔 원문 자체가 본체라, body를 생략하면
# 남는 게 없다 — "쪽지는 body가 비면 안 된다"(2026-07-31 확정).
_NO_OMIT = (("memo", "body"),)


def _check_omitted(bowl: str, values: dict) -> None:
    for bowl_name, field_name in _NO_OMIT:
        if bowl_name != bowl:
            continue
        if cfg.is_omitted(values.get(field_name)):
            raise ValueError(
                f"{cfg.bowl_label(bowl)}({bowl})의 '{field_name}'은 "
                f"'{cfg.OMITTED}'으로 둘 수 없습니다 — 붙여둘 원문이 본체입니다."
            )


def _check_values(bowl: str, values: dict) -> None:
    """정해진 값이 있는 칸은 그 밖의 값을 거절한다."""
    for name, value in values.items():
        allowed = cfg.allowed_values(name, bowl)
        if not allowed or value is None:
            continue
        if value not in allowed:
            raise ValueError(
                f"'{name}'에는 {', '.join(allowed)} 중 하나를 적으세요 — "
                f"'{value}'는 쓸 수 없습니다."
            )


def tool_description() -> str:
    """`namu_record` 도구 설명문을 **표에서 만들어** 돌려준다(완료조건 2).

    손으로 쓰면 표와 어긋난다 — 어긋난 설명문은 AI를 잘못 부르게 만들고, 그 결과가
    이번 사고(잘못된 그릇에 담아 유실)다. 칸마다 ①어느 그릇이 받는지 ②어디서 필수인지
    ③예시 한 줄을 적는다. 나중에 MCP 서버 소개문(instructions)도 이 함수를 쓰면
    도구 설명과 소개문이 갈라지지 않는다.
    """
    lines = [
        "기억 한 건을 남긴다(append-only). "
        + _bowl_count_ko()
        + " 그릇 중 하나를 골라 담는다: "
        + _all_bowls_ko()
        + ".",
        "",
        "모든 그릇이 3층을 갖는다 — summary(무엇을) · reason(왜) · body(그때 무슨 일이). "
        f"셋 다 필수이고, 적을 게 없으면 '{cfg.OMITTED}' 한 단어를 넣는다.",
        "그릇이 받지 않는 칸을 주면 저장하지 않고 거절하며 어느 그릇으로 가야 하는지 알린다.",
        "",
        "칸 목록:",
    ]
    for field in cfg.FIELDS:
        bowls = "·".join(cfg.bowl_label(b) for b in field.bowls)
        if field.required_in:
            need = "필수: " + "·".join(cfg.bowl_label(b) for b in field.required_in)
        else:
            need = "선택"
        lines.append(f"- {field.name} ({bowls} / {need}) — {field.desc} 예) {field.example}")
    lines.append("")
    lines.append(
        "옛 이름(task·subject·statement·source·outcome·tag·text·task_type·"
        "verified_by·kind·title·purpose)으로 불러도 새 이름으로 옮겨 저장하고 "
        "어디로 옮겼는지 반환문에 알린다. 새로 쓸 때는 위 칸 이름만 쓴다."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 서버 소개문 (namu-65 후속 ②)
# ---------------------------------------------------------------------------
#
# MCP 서버는 `FastMCP(instructions=...)`로 자기소개를 한 문단 넘길 수 있는데, 지금까지
# 비어 있어서 클라이언트(AI)는 도구 설명만 보고 그릇의 성격을 짐작해야 했다. 소개문을
# 손으로 쓰면 도구 설명과 갈라지고, **갈라진 설명을 읽은 AI가 잘못된 그릇에 담는 것**이
# namu-65의 발단이므로 여기서도 같은 선언(`config.FIELDS`)에서 만든다.

# 서버가 노출하는 도구 이름. 이름이 바뀌거나 늘면 `test_server_instructions.py`가
# mcp_server.py의 실제 등록 목록과 대조해 실패한다.
_TOOL_LINES = (
    ("namu_recall", "세션을 시작할 때 한 번 부른다 — 붙여둔 쪽지·최근 활동·"
                    "열린 작업·관련 교훈을 한꺼번에 돌려준다."),
    ("namu_search", "지난 기억을 낱말로 찾는다."),
    ("namu_record", "기억 한 건을 남긴다(아래 규칙)."),
    ("namu_memo_remove", "다 쓴 쪽지를 뗀다 — 모든 그릇 중 유일하게 지워지는 그릇이다."),
    ("namu_task_pin", "다음에 이어서 할 작업에 책갈피를 꽂는다 — 브리핑 맨 위에 📌로 선다. "
                      "작업일지에는 아무것도 적지 않는다(순서는 표시의 문제)."),
    ("namu_task_move", "작업 폴더 하나를 다른 프로젝트 방으로 옮긴다 — 이미 있는 방으로만 "
                       "옮길 수 있고, 옮기기로 새 방이 생기지는 않는다. 책갈피도 같이 "
                       "따라온다."),
    ("namu_task_unpin", "이 기기의 책갈피를 뺀다(작업을 닫으면 자동으로 빠진다)."),
    ("namu_sync_setup", "개인 원격 저장소와 자동 동기화를 켠다(처음 한 번)."),
    ("namu_upload_file", "디스크에 있는 파일이나 글자 원문 하나를 회원 저장소에 "
                         "올리고 첨부 기록을 남긴다 — 파일 몸통은 각 PC로 안 "
                         "내려오므로 설명(3층)이 나중에 그 파일을 찾는 유일한 "
                         "단서다. 글자가 아니거나 큰 파일은 올리기 링크를 쓴다."),
    ("namu_list_files", "올린 파일 목록 — 이름·크기와 올릴 때 적은 설명. 크기는 "
                        "첨부 기록에서 읽지 저장소에 묻지 않는다."),
    ("namu_download_file", "올린 파일 하나를 다시 받는다. 받은 일은 기록하지 않는다."),
    ("namu_delete_file", "올린 파일 하나를 저장소에서 뺀다 — 왜 뺐는지는 기록에 "
                         "남는다. **완전 삭제가 아니다**: git은 이력을 남기므로 "
                         "지우기 전 시점에는 그 파일이 그대로 있다."),
    ("namu_create_upload_ticket", "파일을 올릴 일회용 링크를 만든다 — 바이너리나 "
                                  "100KB가 넘는 파일은 이쪽을 쓴다. 파일 몸통이 "
                                  "AI의 출력을 거치지 않아 크기와 무관하게 빠르다."),
    ("namu_create_download_ticket", "올린 파일을 내려받을 링크를 만든다 — 회원에게 "
                                    "파일을 건네는 방법이다. 몸통이 AI를 거치지 않는다."),
    ("namu_check_ticket", "올리기 링크로 파일이 도착했는지 본다 — 회원이 '올렸어'라고 "
                          "했을 때 확인하는 용도."),
)

# 웹으로 열었을 때의 `namu_upload_file` 소개 — 위 줄을 대신한다.
#
# 왜 갈라 두나 (2026-08-07, 세 번째 base64 사고):
# 위 줄은 "디스크에 있는 파일을 올린다"고 말하는데, 그 말은 stdio(터미널)에서만
# 참이다 — 그쪽 도구에는 `file_path` 칸이 있다. 웹으로 여는 두 경로(개인 주소·
# 나무 클라우드)의 도구에는 그 칸이 없다.
#
# 그런데 웹에 붙은 AI는 파일을 **파일로** 들고 있는 경우가 많다(회원이 대화에
# 첨부하면 그 AI의 작업공간에 파일로 놓인다). 그 AI가 "이 도구는 디스크의 파일을
# 올린다"는 소개를 읽고 넣을 칸을 찾으면, 칸이 없으므로 남는 길은 파일을 직접
# 읽어 글자로 옮기는 것뿐이다 — 실제로 명령을 돌려 base64로 바꾸기 시작했고
# (2026-08-07 21:04 화면), 회원은 몇 분을 기다리다 응답을 멈췄다.
#
# 어제 올리기 도구에서 base64 칸을 없앤 것으로는 이 자리가 안 막힌다. 인코딩은
# 우리 도구의 인자가 아니라 그 앞 단계, AI의 작업공간에서 일어나기 때문이다.
# 막는 방법은 금지 문구를 더 붙이는 것이 아니라 **소개가 사실과 맞게 하는 것**이다
# — 이 연결에 파일 경로 칸이 없다는 것과, 파일로 있는 것이 갈 곳(올리기 링크)을
# 알려 주면 읽을 이유 자체가 없어진다.
# 링크 도구 줄도 같이 바꾼다. 위 줄만 고치고 이 줄을 두면 둘이 어긋난다 — 기본
# 문장은 "바이너리나 100KB가 넘는 파일은 이쪽"이라, 6KB짜리 `.md`를 파일로 든 AI가
# 그 줄을 읽고 "내 것은 작고 글자니까 링크는 아니다"로 읽는다. 그 갈림길에 남는 길이
# 다시 "파일을 읽어 글자로 옮기기"다. 웹에서 기준은 크기·종류가 아니라 **이미 파일로
# 있는가**이므로, 그렇게 적는다.
_WEB_TOOL_LINES = {
    "namu_upload_file": (
        "이 대화에서 만든 글을 파일로 저장하고 첨부 기록을 남긴다 — 이 연결에는 파일 "
        "경로 칸이 없다. 이미 파일로 있는 것(회원이 대화에 첨부한 파일 포함)은 "
        "namu_create_upload_ticket으로 링크를 만들어 그 파일을 그대로 보낸다. 파일 "
        "몸통은 각 PC로 안 내려오므로 설명(3층)이 나중에 그 파일을 찾는 유일한 단서다."
    ),
    "namu_create_upload_ticket": (
        "파일을 올릴 일회용 링크를 만든다 — 이미 파일로 있는 것은 크기·종류와 상관없이 "
        "이쪽이다. 파일 몸통이 AI의 출력을 거치지 않으므로 파일을 열어 읽을 필요가 없고, "
        "크기와 무관하게 빠르다."
    ),
}


def server_instructions(
    exposed: "Iterable[str] | None" = None,
    *,
    upload_takes_path: bool = True,
) -> str:
    """MCP 서버 소개문. 그릇 설명과 기록 규칙을 도구 설명문과 같은 표에서 만든다.

    `exposed`에 **실제로 내주는 도구 이름**을 넘기면 그만큼만 소개한다. 생략하면
    전부(stdio 경로 — 도구를 거르지 않으므로 지금까지와 같다).

    왜 인자를 받나: 웹으로 여는 경로는 도구를 걸러 3종만 내주는데(셀프호스팅의
    `http_server.HTTP_EXPOSED_TOOLS`, 클라우드는 자기 쪽에서 3종만 정의) 소개문은
    거르지 않아 **없는 도구 4개를 있다고 소개**하고 있었다(2026-08-05 실측:
    소개 7종 / 노출 3종). 붙은 AI가 없는 도구를 부르면 실패한다. 거르는 목록과
    소개문을 같은 인자에서 만들면 둘이 다시 갈라지지 않는다.

    `upload_takes_path`는 그 연결의 `namu_upload_file`에 **파일 경로 칸이 있는지**다
    (stdio는 있고, 웹으로 여는 두 경로는 없다). 없는 쪽에 "디스크의 파일을 올린다"고
    소개하면 파일을 든 AI가 넣을 칸을 못 찾아 파일을 읽어 글자로 옮기기 시작한다 —
    `_WEB_TOOL_LINES` 위의 설명 참고.
    """
    bowl_field = cfg.field_by_name("bowl")
    tool_lines = tuple(
        (n, d if upload_takes_path else _WEB_TOOL_LINES.get(n, d))
        for n, d in _TOOL_LINES
    )
    shown = [(n, d) for n, d in tool_lines if exposed is None or n in set(exposed)]
    hidden = [n for n, _ in _TOOL_LINES if exposed is not None and n not in set(exposed)]
    lines = [
        f"NAMU 기억 서버 — 대화가 끝나도 남는 기억을 {_bowl_count_ko()} 그릇에 "
        "나눠 담고 다시 꺼낸다.",
        "",
        # 그릇의 성격은 `bowl` 칸 설명이 이미 그릇을 다 짚고 있다 — 소개문에 따로
        # 쓰면 그게 곧 갈라질 두 번째 설명이 된다.
        f"그릇 고르기 — {bowl_field.desc}",
        "",
        "도구:",
    ]
    lines += [f"- {name} — {desc}" for name, desc in shown]
    if hidden:
        # 없는 도구를 왜 못 쓰는지 한 줄로 알려 준다. 이유를 안 적으면 AI가
        # "이 서버는 고장났나" 하고 없는 이름을 계속 시도한다.
        lines += [
            "",
            "이 연결에서는 위 도구만 쓸 수 있다. 나머지("
            + " · ".join(hidden)
            + ")는 나무를 플러그인으로 설치했을 때만 온다 — 없는 이름을 부르지 말 것.",
        ]
    lines += ["", "── 기록 규칙(namu_record) ──", "", tool_description()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 문서용 표 (namu-65 후속 ①) — 손으로 옮겨 적지 않는다
# ---------------------------------------------------------------------------
#
# 설계서 4장에는 칸 표가 손으로 적혀 있었다. 표가 코드(`config.FIELDS`)와 문서 두
# 곳에 살면 반드시 갈라지고, **갈라진 표를 읽은 AI가 잘못된 그릇에 담는 것**이 이번
# 작업의 발단이었다. 그래서 문서에 싣는 표도 도구 설명문과 같은 선언에서 만든다.
# `scripts/gen_field_docs.py`가 이 함수의 결과를 문서에 끼워 넣고, 문서를 손으로
# 고치면 `test_field_docs.py`가 실패한다.

_MARK_REQUIRED = "필수"
_MARK_OPTIONAL = "선택"
_MARK_ABSENT = "—"


def _cell(text: str) -> str:
    """표 칸 안에서 깨지는 글자를 막는다(세로줄은 칸 구분자, 줄바꿈은 행 구분자)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _mark(field, bowl: str) -> str:
    if bowl in field.required_in:
        return _MARK_REQUIRED
    if bowl in field.bowls:
        return _MARK_OPTIONAL
    return _MARK_ABSENT


def field_table_markdown() -> str:
    """칸 × 그릇 배치표(마크다운). 열 순서는 `cfg.BOWL_NAMES`를 그대로 따른다."""
    header = ["칸"] + [cfg.bowl_label(b) for b in cfg.BOWL_NAMES] + ["뜻"]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for field in cfg.FIELDS:
        row = (
            [f"`{field.name}`"]
            + [_mark(field, b) for b in cfg.BOWL_NAMES]
            + [_cell(_first_sentence(field.desc))]
        )
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def field_detail_markdown() -> str:
    """칸별 상세(설명 전문·예시·닫힌 값). 표의 '뜻'은 첫 문장뿐이라 나머지를 여기 편다."""
    lines = []
    for field in cfg.FIELDS:
        lines.append(f"- **`{field.name}`** — {field.desc}")
        lines.append(f"  - 예) `{field.example}`")
        # 값 목록이 같은 그릇은 한 줄로 묶는다 — bowl처럼 모든 그릇이 같은 값을 받는 칸을
        # 그릇마다 되풀이하면 같은 줄이 네 번 나와 정작 다른 칸(status)의 차이가 묻힌다.
        grouped: dict = {}
        for bowl in cfg.BOWL_NAMES:
            allowed = cfg.allowed_values(field.name, bowl)
            if allowed:
                grouped.setdefault(allowed, []).append(bowl)
        for allowed, bowls in grouped.items():
            where = (
                "쓸 수 있는 값"
                if len(bowls) == len(field.bowls)
                else "·".join(cfg.bowl_label(b) for b in bowls) + "에서 쓸 수 있는 값"
            )
            lines.append(f"  - {where}: " + " · ".join(f"`{v}`" for v in allowed))
    return "\n".join(lines)


def alias_table_markdown() -> str:
    """옛 이름 → 새 이름 대응표. `cfg.FIELD_ALIASES` 선언 순서를 유지한다."""
    lines = [
        "| 옛 이름 | 새 이름 | 어느 그릇에서 | 비고 |",
        "|---|---|---|---|",
    ]
    for alias in cfg.FIELD_ALIASES:
        new = f"`{alias.new}`" if alias.new else "(없앰)"
        where = _bowl_list_ko(alias.bowls) if alias.bowls else "모든 그릇"
        lines.append(
            f"| `{alias.old}` | {new} | {_cell(where)} | {_cell(alias.note)} |"
        )
    return "\n".join(lines)


def docs_section() -> str:
    """설계서 4장에 끼워 넣는 생성 구역 전체."""
    omitted = cfg.OMITTED
    return "\n\n".join([
        f"칸은 {len(cfg.FIELDS)}개, 그릇은 {len(cfg.BOWL_NAMES)}개다. "
        f"**필수**는 비면 거절하는 자리이고(적을 게 없으면 `{omitted}` 한 단어), "
        f"**{_MARK_ABSENT}**는 그 그릇이 받지 않는 칸이라 주면 거절당한다.",
        field_table_markdown(),
        "### 칸별 설명",
        field_detail_markdown(),
        "### 옛 이름 → 새 이름",
        alias_table_markdown(),
        "옛 이름으로 호출해도 **새 이름으로 옮겨 저장하고, 어디로 옮겼는지 반환문에 "
        "알린다.** 말없이 버리는 경로는 코드에 없다.",
    ])


def normalize(provided: dict) -> RecordInput:
    """기록 입력을 검증하고 새 이름으로 맞춰 돌려준다.

    provided: 호출자가 실제로 준 값들(안 준 칸은 None이거나 없어야 한다).
    반환: 그릇·새 이름 값들·안내문.
    잘못된 입력은 전부 ValueError로 거절한다 — **조용히 버리는 경로는 없다.**
    """
    given = {
        name: value
        for name, value in provided.items()
        if not (_is_blank(value) or (name in _FALSE_MEANS_ABSENT and not value))
    }

    bowl, notices = resolve_bowl(given)

    # 작업을 새로 만드는 호출에서 옛 `text`는 "다음 세션이 시작할 지점"이었다
    # (namu-62 ③). 새 이름으로는 body가 그 자리이므로, 일반 규칙(작업일지의 text는
    # 줄에 적히는 한 줄=summary)보다 이쪽이 우선한다 — 여기서 summary로 보내면 제목
    # (title)과 자리를 다투고, 정작 착수 지점은 사라진다.
    if bowl == "tasks" and given.get("create") and "text" in given and "body" not in given:
        given = dict(given)
        given["body"] = given.pop("text")
        notices.append(
            "'text'는 이제 'body'입니다 — 새 작업의 착수 지점으로 옮겨 저장했습니다."
        )

    values = _apply_aliases(bowl, given, notices)
    values["bowl"] = bowl

    # 새 작업의 제목(summary)을 안 주면 작업 이름을 그대로 쓴다 — 옛 `title` 기본값과
    # 같은 동작이다. 이건 '조용히 버리기'가 아니라 '빠진 값을 뻔한 값으로 채우기'라,
    # 거절해서 한 번 더 부르게 할 이유가 없다.
    if bowl == "tasks" and values.get("create") and not values.get("summary"):
        values["summary"] = values.get("topic")

    # 새 작업을 만들 때 status는 함께 적히는 착수 지점(body) 줄의 꼬리표다. 착수 지점이
    # 없는데 꼬리표만 주면 붙일 줄이 없으므로 조용히 버리지 않고 거절한다(namu-62 ③의
    # 규칙을 새 이름으로 옮긴 것 — 그때 이 값들이 말없이 사라져 빈 작업이 남았다).
    if (
        bowl == "tasks"
        and values.get("create")
        and values.get("status")
        and cfg.is_omitted(values.get("body"))
    ):
        raise ValueError(
            f"status={values['status']!r}만 주고 착수 지점(body)이 비었습니다 — "
            "새 작업의 꼬리표는 함께 적을 착수 지점에 붙는 것이라, body에 "
            "다음 세션이 시작할 지점을 적거나 status를 빼세요."
        )

    _reject_foreign_fields(bowl, values)
    _check_required(bowl, values)
    _check_omitted(bowl, values)
    _check_values(bowl, values)

    return RecordInput(bowl=bowl, values=values, notices=notices)
