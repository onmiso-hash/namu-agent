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
            f"'{bowl}'라는 그릇은 없습니다 — 네 그릇 중 하나를 고르세요: {_all_bowls_ko()}."
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


def _check_required(bowl: str, values: dict) -> None:
    """필수 칸이 비면 거절한다. `생략` 한 단어는 채운 것으로 본다."""
    for name in sorted(cfg.required_fields(bowl)):
        if not _is_blank(values.get(name)):
            continue
        field = cfg.field_by_name(name)
        raise ValueError(
            f"{cfg.bowl_label(bowl)}({bowl}) 기록에는 '{name}'이 필요합니다 — "
            f"{field.desc.split('.')[0]}. 적을 게 정말 없으면 "
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
        "기억 한 건을 남긴다(append-only). 네 그릇 중 하나를 골라 담는다: "
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
