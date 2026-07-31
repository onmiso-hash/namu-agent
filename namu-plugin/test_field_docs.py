"""문서에 실린 칸 배치표가 `config.FIELDS`와 갈라지지 않는지 (namu-65 후속 ①).

표가 코드와 문서 두 곳에 살면 갈라지고, **갈라진 표를 읽은 AI가 잘못된 그릇에 담은
것**이 namu-65의 발단이었다. 그래서 문서의 표는 손으로 적지 않고 생성하며, 여기서는
두 가지를 못 박는다.

1. 생성 결과 자체가 표와 맞는가 (칸 하나도 빠지지 않고, 필수/선택/못 씀이 선언대로인가)
2. 문서에 실제로 실린 구역이 지금 생성 결과와 같은가 (손으로 고치면 여기서 실패)

2번은 이 repo에서만 검사한다 — 설치본에는 `docs/`가 없고, 그 경우 "문서 없음"은 결함이
아니라 정상이라 건너뛴다.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
import record_input

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = REPO_ROOT / "scripts" / "gen_field_docs.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_field_docs", GEN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. 생성 결과가 선언과 맞는가
# ---------------------------------------------------------------------------

def _table_rows():
    lines = record_input.field_table_markdown().splitlines()
    return [line for line in lines[2:] if line.strip()]


def test_table_has_one_row_per_field():
    assert len(_table_rows()) == len(cfg.FIELDS)


def test_table_columns_follow_bowl_registry():
    header = record_input.field_table_markdown().splitlines()[0]
    cells = [c.strip() for c in header.strip("|").split("|")]
    # 열 순서를 손으로 적으면 그릇을 새로 추가할 때 표가 밀린다 — 레지스트리를 따른다.
    assert cells[1:-1] == [cfg.bowl_label(b) for b in cfg.BOWL_NAMES]


@pytest.mark.parametrize("field", cfg.FIELDS, ids=lambda f: f.name)
def test_each_row_marks_required_optional_absent(field):
    row = next(r for r in _table_rows() if r.startswith(f"| `{field.name}` "))
    cells = [c.strip() for c in row.strip("|").split("|")]
    marks = dict(zip(cfg.BOWL_NAMES, cells[1:]))
    for bowl in cfg.BOWL_NAMES:
        if bowl in field.required_in:
            assert marks[bowl] == "필수"
        elif bowl in field.bowls:
            assert marks[bowl] == "선택"
        else:
            assert marks[bowl] == "—"


def test_alias_table_covers_every_declared_alias():
    table = record_input.alias_table_markdown()
    for alias in cfg.FIELD_ALIASES:
        assert f"`{alias.old}`" in table
        assert (f"`{alias.new}`" if alias.new else "(없앰)") in table


def test_generated_markdown_never_breaks_table_cells(monkeypatch):
    # 설명에 세로줄이나 줄바꿈이 들어오면 표가 통째로 깨진다. 그때 조용히 깨진 표가
    # 남으면 이 장치가 막으려던 '어긋난 표'가 그대로 돌아온다.
    bad = cfg.Field(
        name="probe",
        bowls=cfg.BOWL_NAMES,
        required_in=(),
        desc="세로줄 | 과 줄바꿈\n이 든 설명",
        example="x",
    )
    monkeypatch.setattr(cfg, "FIELDS", cfg.FIELDS + (bad,))
    row = next(
        r for r in record_input.field_table_markdown().splitlines()
        if r.startswith("| `probe` ")
    )
    assert "\n" not in row
    # 칸 구분자는 '앞에 역슬래시가 없는' 세로줄뿐이다 — escape된 것은 글자로 센다.
    cells = re.split(r"(?<!\\)\|", row.strip("|"))
    assert len(cells) == len(cfg.BOWL_NAMES) + 2


def test_docs_section_mentions_omitted_word():
    # `생략` 한 단어가 규칙의 핵심인데(설계 원칙 3) 문서에 없으면 필수 칸 앞에서
    # 무엇을 적어야 할지 알 수 없다.
    assert cfg.OMITTED in record_input.docs_section()


# ---------------------------------------------------------------------------
# 2. 문서에 실린 구역이 최신인가
# ---------------------------------------------------------------------------

def test_design_doc_section_is_up_to_date():
    gen = _load_generator()
    if not gen.TARGET.exists():
        pytest.skip("설치본에는 docs/가 없다 — 검사 대상 아님")
    current = gen.TARGET.read_text(encoding="utf-8")
    assert current == gen.splice(current, gen.render()), (
        "설계서 4장의 칸 표가 config.FIELDS와 어긋납니다 — "
        "`python scripts/gen_field_docs.py`를 실행하세요."
    )
