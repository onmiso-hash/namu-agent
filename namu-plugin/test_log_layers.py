"""작업일지 세 줄 묶음 읽기 테스트 (namu-65 4·5단계).

지키는 규칙은 둘이다.
① 화면에는 **요약이 있으면 요약, 없으면 첫 줄**만 싣는다 — 2,000자짜리 재진입
   메모가 브리핑에 그대로 쏟아지던 것이 이번 작업의 출발점이다.
② 화면에서 뺀 부분도 **검색에서는 빠지지 않는다** — 안 그러면 요약을 만든 대가로
   내용을 잃는다.

옛 450줄과 새 묶음이 한 파일에 섞여도 항목 수가 흔들리지 않는지도 함께 본다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import task_resolve as tr

_MIGRATED = (
    "# log\n"
    "[다음] 2026-07-28 01:20:33 hp · 실측 결과 4개 중 3개 통과, 결함 2개 발견 — "
    "아직 닫지 말 것. 결함A는 이름 중복이 데이터 원본에 남아 있고 결함B는 브리핑이 "
    "사용자 화면에 안 뜬다.\n"
    "    요약: 제목 조립부에서 슬러그 중복 표기를 원천 제거한다.\n"
    "    왜: 여러 소비자가 공유하는 함수라 원천 수정이 낫다.\n"
)

_NEW_BLOCK = (
    "# log\n"
    "[다음] 2026-07-31 11:00:00 hp · 구현 1단계부터 착수한다\n"
    "    왜: 데이터 옮기기가 끝나 코드 차례이기 때문\n"
    "    상세: config.py의 BOWLS 옆에 그릇별 허용 칸 선언을 만든다\n"
)

_OLD_ONLY = "# log\n[다음] 2026-07-20 09:00:00 hp · 옛 형식 한 줄 그대로\n"


@pytest.fixture()
def task_dir(tmp_path):
    def _make(log_text: str) -> Path:
        d = tmp_path / "namu-99"
        d.mkdir(exist_ok=True)
        (d / "log.md").write_text(log_text, encoding="utf-8")
        return d
    return _make


def test_summary_line_wins_over_the_long_head(task_dir):
    note = tr.next_note(task_dir(_MIGRATED))
    assert note == "제목 조립부에서 슬러그 중복 표기를 원천 제거한다."


def test_head_line_is_used_when_there_is_no_summary(task_dir):
    # 새로 적히는 묶음은 머리줄 자체가 요약이다.
    assert tr.next_note(task_dir(_NEW_BLOCK)) == "구현 1단계부터 착수한다"


def test_old_single_line_is_unchanged(task_dir):
    assert tr.next_note(task_dir(_OLD_ONLY)) == "옛 형식 한 줄 그대로"


def test_continuation_lines_are_not_counted_as_entries(task_dir):
    # 읽는 쪽 규약은 여전히 "'['로 시작하는 줄만 항목"이다 — 옛 줄과 섞여도 안전.
    d = task_dir(_MIGRATED + _NEW_BLOCK.replace("# log\n", ""))
    lines = (d / "log.md").read_text(encoding="utf-8").splitlines()
    heads = [ln for ln in lines if ln.startswith("[")]
    assert len(heads) == 2


def test_continuations_are_parsed_by_label():
    lines = _NEW_BLOCK.splitlines()
    got = tr._continuations(lines, 1)
    assert got == {
        "왜": "데이터 옮기기가 끝나 코드 차례이기 때문",
        "상세": "config.py의 BOWLS 옆에 그릇별 허용 칸 선언을 만든다",
    }


def test_unlabelled_indented_lines_are_ignored():
    lines = ["[기록] 2026-07-31 11:00:00 hp · 머리줄", "    그냥 이어 쓴 문단"]
    assert tr._continuations(lines, 0) == {}


def test_display_text_keeps_what_it_hides_for_search():
    lines = _MIGRATED.splitlines()
    shown, rest = tr._display_text(lines, 1, "실측 결과 4개 중 3개 통과")
    assert shown == "제목 조립부에서 슬러그 중복 표기를 원천 제거한다."
    # 화면에서 뺀 머리줄과 '왜'가 검색용 뭉치에 남아야 한다.
    assert "여러 소비자가 공유하는 함수라" in rest
    assert "실측 결과 4개 중 3개 통과" in rest


def test_new_block_keeps_reason_and_body_for_search():
    lines = _NEW_BLOCK.splitlines()
    shown, rest = tr._display_text(lines, 1, "구현 1단계부터 착수한다")
    assert shown == "구현 1단계부터 착수한다"
    assert "데이터 옮기기가 끝나" in rest and "BOWLS 옆에" in rest


def test_next_why_reads_the_reason_line(task_dir):
    # ▸(가장 최근 작업)에만 붙는 한 줄 — 이어받는 지점이 왜 그 지점인지 알려준다.
    assert tr.next_why(task_dir(_MIGRATED)) == "여러 소비자가 공유하는 함수라 원천 수정이 낫다."
    assert tr.next_why(task_dir(_NEW_BLOCK)) == "데이터 옮기기가 끝나 코드 차례이기 때문"


def test_next_why_is_none_for_old_single_lines(task_dir):
    assert tr.next_why(task_dir(_OLD_ONLY)) is None
