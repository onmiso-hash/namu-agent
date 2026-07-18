import os
import pytest
from pathlib import Path
from task_resolve import (
    _parse_log_ts,
    _line_tag,
    _log_says_closed,
    check_project_marker_conflict,
    find_active_task,
    find_latest_closed_task,
    has_legacy_tasks,
    record_project_marker,
    resolve_active_task,
    tasks_root_for,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """실제 ~/.namu를 건드리지 않도록 HOME을 tmp 아래 가짜 홈으로 격리(namu-33 교훈)."""
    home = tmp_path / "fake_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home

def test_parse_log_ts():
    # 시각 있는 줄
    assert _parse_log_ts("[시작] 2026-06-28 10:15:30 hp · 시작") == ("2026-06-28", "10:15:30")
    # 대괄호 안의 태그만 있는 줄 (시각 없음)
    assert _parse_log_ts("[시작] 2026-06-28 hp · 내용") == ("2026-06-28", "00:00:00")
    # 시각 있는 줄 (다른 포맷)
    assert _parse_log_ts("[결정] 2026-06-29 07:35:51 hp · 내용") == ("2026-06-29", "07:35:51")
    # 비-log 줄
    assert _parse_log_ts("그냥 텍스트") is None
    assert _parse_log_ts("# log — task") is None

def _make_task(tasks_root: Path, slug: str, next_body: str | None, log_ts: str, machine: str = "hp"):
    task_dir = tasks_root / slug
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text(f"# {slug}\n", encoding="utf-8")
    
    if next_body is not None:
        (task_dir / f"context.{machine}.md").write_text(
            f"## ▶ 다음\n{next_body}\n", encoding="utf-8"
        )
    
    (task_dir / "log.md").write_text(
        f"# log\n[시작] {log_ts} {machine} · 시작함\n", encoding="utf-8"
    )
    return task_dir

def test_find_active_latest_log_ts(tmp_path):
    _make_task(tmp_path, "older", "진행중", "2026-06-28 10:00:00")
    _make_task(tmp_path, "newer", "진행중", "2026-06-29 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "newer"

def test_find_active_skips_all_done(tmp_path):
    _make_task(tmp_path, "done", "(완료)", "2026-06-29 10:00:00")
    _make_task(tmp_path, "active", "진행중", "2026-06-28 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "active"

def test_find_active_no_context_is_active(tmp_path):
    # context 파일이 아예 없음
    _make_task(tmp_path, "no-context", None, "2026-06-29 10:00:00")
    
    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "no-context"

def test_find_active_missing_machine_context_still_found(tmp_path):
    # context.hp.md만 있고, context.samsung.md는 없어도 잡힘
    _make_task(tmp_path, "only-hp", "진행중", "2026-06-29 10:00:00", machine="hp")

    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "only-hp"


def test_resolve_active_task_uses_personal_pool(fake_home, tmp_path):
    """resolve_active_task(ws)는 개인 풀 ~/.namu/tasks/<basename(ws)>/ 아래에서 찾는다(namu-34)."""
    ws_dir = tmp_path / "project"
    ws_dir.mkdir()
    _make_task(fake_home / ".namu" / "tasks" / "project", "ws-task", "진행중", "2026-06-29 10:00:00")

    res = resolve_active_task(str(ws_dir))
    assert res is not None
    assert res[0] == "ws-task"


def test_resolve_active_task_ignores_namu_home_env(fake_home, monkeypatch, tmp_path):
    """NAMU_HOME 환경변수가 설정돼 있어도 ws(프로젝트) 기준만 본다(namu-26 이원화, namu-34로 저장 위치만 개인 풀로 이동).

    이전 동작(NAMU_HOME 우선)이었다면 이 테스트는 실패한다 — NAMU_HOME 아래
    tasks에 활성 task를 심어 놓고 ws 쪽엔 아무것도 안 둬서, 옛 로직이면
    NAMU_HOME의 task를 찾고 새 로직이면 None을 반환해야 정상이다.
    """
    namu_home = tmp_path / "namu_home"
    _make_task(namu_home / "tasks", "memory-root-task", "진행중", "2026-06-29 10:00:00")

    ws_dir = tmp_path / "project"
    ws_dir.mkdir()

    monkeypatch.setenv("NAMU_HOME", str(namu_home))

    res = resolve_active_task(str(ws_dir))
    assert res is None


def test_resolve_active_task_empty_ws_returns_none():
    """ws가 비어있으면 안전 폴백으로 None."""
    assert resolve_active_task("") is None


# ---------------------------------------------------------------------------
# tasks_root_for — 경로 규칙 단일화(namu-34 ①)
# ---------------------------------------------------------------------------


def test_tasks_root_for_uses_fake_home_and_basename(fake_home, tmp_path):
    """tasks_root_for(project_dir) == <fake HOME>/.namu/tasks/<basename(project_dir)>."""
    project_dir = tmp_path / "some-project"
    project_dir.mkdir()

    result = tasks_root_for(str(project_dir))
    assert result == fake_home / ".namu" / "tasks" / "some-project"


def test_tasks_root_for_ignores_trailing_slash(fake_home, tmp_path):
    project_dir = tmp_path / "some-project"
    project_dir.mkdir()

    result = tasks_root_for(str(project_dir) + "/")
    assert result == fake_home / ".namu" / "tasks" / "some-project"


def test_config_tasks_dir_for_matches_task_resolve(fake_home, tmp_path, monkeypatch):
    """config.tasks_dir_for()가 task_resolve.tasks_root_for()와 동일 결과를 낸다(규칙 이중 구현 금지 검증)."""
    import config as cfg

    project_dir = tmp_path / "another-project"
    project_dir.mkdir()

    assert cfg.tasks_dir_for(project_dir) == tasks_root_for(project_dir)


# ---------------------------------------------------------------------------
# .project 마커 — 충돌 감지(namu-34 ②)
# ---------------------------------------------------------------------------


def test_record_project_marker_writes_line(fake_home, tmp_path):
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    record_project_marker(tasks_root, "hp", str(project_dir))

    marker = (tasks_root / ".project").read_text(encoding="utf-8")
    assert marker.strip() == f"hp={os.path.realpath(project_dir)}"


def test_record_project_marker_is_idempotent(fake_home, tmp_path):
    """같은 machine·같은 경로로 재호출해도 줄이 늘지 않는다(멱등)."""
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    record_project_marker(tasks_root, "hp", str(project_dir))
    record_project_marker(tasks_root, "hp", str(project_dir))
    record_project_marker(tasks_root, "hp", str(project_dir))

    lines = (tasks_root / ".project").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_record_project_marker_appends_new_line_on_change(fake_home, tmp_path):
    """기존 줄은 수정·삭제하지 않고 새 줄만 append(append-only)."""
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()

    record_project_marker(tasks_root, "hp", str(project_a))
    record_project_marker(tasks_root, "hp", str(project_b))

    lines = (tasks_root / ".project").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == f"hp={os.path.realpath(project_a)}"
    assert lines[1] == f"hp={os.path.realpath(project_b)}"


def test_record_project_marker_separate_machines_both_kept(fake_home, tmp_path):
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    record_project_marker(tasks_root, "hp", str(project_dir))
    record_project_marker(tasks_root, "samsung", str(project_dir))

    lines = (tasks_root / ".project").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_check_project_marker_conflict_none_when_no_marker(fake_home, tmp_path):
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_dir = tmp_path / "proj"
    assert check_project_marker_conflict(tasks_root, "hp", str(project_dir)) is None


def test_check_project_marker_conflict_none_when_matching(fake_home, tmp_path):
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    record_project_marker(tasks_root, "hp", str(project_dir))
    assert check_project_marker_conflict(tasks_root, "hp", str(project_dir)) is None


def test_check_project_marker_conflict_detects_mismatch(fake_home, tmp_path):
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()

    record_project_marker(tasks_root, "hp", str(project_a))

    result = check_project_marker_conflict(tasks_root, "hp", str(project_b))
    assert result is not None
    registered, current = result
    assert registered == str(os.path.realpath(project_a))
    assert current == str(os.path.realpath(project_b))


def test_check_project_marker_conflict_none_for_different_machine(fake_home, tmp_path):
    """다른 machine 줄은 비교 대상이 아니다 — 현재 machine 줄이 없으면 충돌 없음."""
    tasks_root = fake_home / ".namu" / "tasks" / "proj"
    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()

    record_project_marker(tasks_root, "hp", str(project_a))
    assert check_project_marker_conflict(tasks_root, "samsung", str(project_b)) is None


# ---------------------------------------------------------------------------
# 구 위치 감지 — has_legacy_tasks(namu-34 ⑤)
# ---------------------------------------------------------------------------


def test_has_legacy_tasks_true_when_old_location_has_log(tmp_path):
    task_dir = tmp_path / "tasks" / "old-task"
    task_dir.mkdir(parents=True)
    (task_dir / "log.md").write_text("[시작] 2026-06-28 10:00:00 hp · 시작\n", encoding="utf-8")

    assert has_legacy_tasks(tmp_path) is True


def test_has_legacy_tasks_false_when_no_tasks_dir(tmp_path):
    assert has_legacy_tasks(tmp_path) is False


def test_has_legacy_tasks_false_when_tasks_dir_empty(tmp_path):
    (tmp_path / "tasks").mkdir()
    assert has_legacy_tasks(tmp_path) is False


# ---------------------------------------------------------------------------
# _line_tag / _log_says_closed — log=권위 판정 (namu-27)
# ---------------------------------------------------------------------------

def test_line_tag_extracts_bracket_prefix():
    assert _line_tag("[시작] 2026-06-28 10:15:30 hp · 시작") == "시작"
    assert _line_tag("[완료] 2026-06-29 hp · 완료") == "완료"
    assert _line_tag("그냥 텍스트") is None
    assert _line_tag("# log — task") is None


def test_log_says_closed_done_only(tmp_path):
    """[완료] 단독 -> 닫힘."""
    log_path = tmp_path / "log.md"
    log_path.write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n"
        "[완료] 2026-06-29 10:00:00 hp · 완료\n",
        encoding="utf-8",
    )
    assert _log_says_closed(log_path) is True


# 실물 함정: tasks/namu-25-usage-guide/log.md — [완료] 뒤에 [정정] 줄이 있다.
# "마지막 줄이 [완료]인가"로 구현하면 이 task가 도로 유령(오탐지)이 된다.
_NAMU25_LOG_FIXTURE = """# log — namu-25-usage-guide
(append만. context 꼬이면 이걸로 복원)

[시작] 2026-07-09 13:24:47 samsung · 계획 확정(사용자 결정): HP에서 타 프로젝트에 설치형 실사용 실측 → 채록 기반 사용 가이드 작성. 배경 = 현 html은 설치 설명서일 뿐 사용 설명서 부재(07-09 평가)
[실측] 2026-07-09 19:37:54 hp · ① 원격 설치 헤드리스분 PASS — 대상=onnamu-project(사용자 확정). marketplace add(HTTPS clone 성공)→install user 스코프 0.1.7·sha ef8ca96(방금 pull 커밋=GitHub발 물증)·기존 local 0.1.1 무사→onnamu-project서 claude mcp list ✔Connected(0.1.7 캐시 경로).
[실측] 2026-07-09 20:48:04 hp · ①② 완주 — 사용자 라이브: 세션 브리핑 없음(신규 환경 md=None 설계상 침묵+CC 무화면 사양 겹침, ~/.namu/db 19:37 생성 물증으로 경로·서버 정상 판정), /mcp 3도구 ✔, /namu-task 실작업 1건 전 사이클 완주.
[결정] 2026-07-09 20:56:00 hp · ④⑤ 사용자 게이트 통과 — ④ 별도 문서(docs/usage_guide.md 신설, 8절+뺀 것 목록, 실측 채록만 사용) ⑤ 한계+임시 안내.
[완료] 2026-07-09 21:10:32 hp · #25 종료 — 완료조건 ①~⑤ 전부 충족(사용자 검수 통과 처리). 이월: namu-26 후보 4건(데이터 루트 일원화·SKILL.md machine 문구·환영 브리핑·statusline 동봉). 커밋·푸시 진행
[정정] 2026-07-10 09:14:43 samsung · 유령 해소 — hp 마감(21:10) 시 context 미닫음으로 활성 task 오탐지. context.samsung·context.hp의 '▶ 다음'을 (완료) 단독 표기로 정정 (마감 규약: 단독 표기·전 machine 파일)
"""


def test_log_says_closed_done_then_correction_is_still_closed(tmp_path):
    """namu-25 실물 패턴: [완료] 뒤에 [정정] — 구간 존재 판정이므로 여전히 닫힘."""
    log_path = tmp_path / "log.md"
    log_path.write_text(_NAMU25_LOG_FIXTURE, encoding="utf-8")
    assert _log_says_closed(log_path) is True


def test_log_says_closed_done_then_restart_is_reopened(tmp_path):
    """[완료] 뒤에 새 [시작](재개)이 붙으면 그 이후 구간만 보므로 열림(False)."""
    log_path = tmp_path / "log.md"
    log_path.write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n"
        "[완료] 2026-06-29 10:00:00 hp · 완료\n"
        "[시작] 2026-06-30 10:00:00 hp · 재개\n"
        "[결정] 2026-06-30 11:00:00 hp · 방향\n",
        encoding="utf-8",
    )
    assert _log_says_closed(log_path) is False


def test_log_says_closed_aborted(tmp_path):
    """[중단] -> 닫힘."""
    log_path = tmp_path / "log.md"
    log_path.write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n"
        "[중단] 2026-06-29 10:00:00 hp · 보류\n",
        encoding="utf-8",
    )
    assert _log_says_closed(log_path) is True


def test_log_says_closed_no_closing_tag(tmp_path):
    """[시작] 이후 완료/중단 태그가 전혀 없으면 열림(False)."""
    log_path = tmp_path / "log.md"
    log_path.write_text(
        "[시작] 2026-06-28 10:00:00 hp · 시작\n"
        "[결정] 2026-06-28 11:00:00 hp · 방향\n",
        encoding="utf-8",
    )
    assert _log_says_closed(log_path) is False


def test_find_active_task_namu25_closed_after_context_correction(tmp_path):
    """namu-25 실물 사례: log에 [완료]가 있어도(마일스톤/과부하 태그) 닫힘 권위는 context다.

    (namu-50 개정) 예전엔 이 테스트가 "context가 진행중([진행중])이어도 log의
    [완료]만으로 닫힘"을 정답으로 인코딩했다 — 이게 바로 새 규칙이 고치는 버그
    패턴(마일스톤 [완료]가 진짜 종료로 오판)이다. 실제 namu-25 사건도 [정정]
    커밋으로 context.hp/samsung의 '▶ 다음'을 (완료) 단독 표기로 명시 정정한
    뒤에야 진짜로 닫혔으므로, fixture도 그 정정 후 상태(= "(완료)")로 명시해
    context 권위로 닫힘이 판정됨을 검증한다.
    """
    task_dir = tmp_path / "namu-25-usage-guide"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("# namu-25-usage-guide\n", encoding="utf-8")
    (task_dir / "log.md").write_text(_NAMU25_LOG_FIXTURE, encoding="utf-8")
    # [정정] 이후 실제 상태: context ▶다음이 (완료) 단독 표기로 정정됨
    (task_dir / "context.hp.md").write_text("## ▶ 다음\n(완료)\n", encoding="utf-8")

    assert find_active_task(tmp_path) is None
    closed = find_latest_closed_task(tmp_path)
    assert closed is not None
    assert closed.name == "namu-25-usage-guide"


def test_find_active_task_context_authority_overrides_log_milestone_done(tmp_path):
    """namu-50 회귀 테스트: 마일스톤 [완료]가 쌓인 진행 중 task가 유령(닫힘)으로 오판되면 안 된다.

    task A(worked) = [시작](과거) → [완료] 마일스톤(중간) → [결정](최신), context
    ▶다음은 실제 다음 할 일(= (완료) 아님). task B(등록만) = [시작]만, A보다 과거.

    수정 전(_is_closed = log_says_closed OR all_contexts_done)이면: A는
    log_says_closed=True(구간 내 [완료] 존재)로 닫힘 오판돼 건너뛰고, B가
    active로 잘못 선택된다. 수정 후(context 권위)면 A의 context가 아직
    (완료)가 아니므로 A가 active로 정확히 선택된다.
    """
    task_a = tmp_path / "namu-50-worked"
    task_a.mkdir()
    (task_a / "task.md").write_text("# namu-50-worked\n", encoding="utf-8")
    (task_a / "log.md").write_text(
        "# log\n"
        "[시작] 2026-06-25 09:00:00 hp · 시작함\n"
        "[완료] 2026-06-26 09:00:00 hp · 코어 이음새 완료\n"
        "[결정] 2026-06-27 09:00:00 hp · 다음 유닛 방향 확정\n",
        encoding="utf-8",
    )
    (task_a / "context.hp.md").write_text(
        "## ▶ 다음\n라우팅 서버 유닛 이어서 진행\n", encoding="utf-8"
    )

    task_b = tmp_path / "namu-51-registered-only"
    task_b.mkdir()
    (task_b / "task.md").write_text("# namu-51-registered-only\n", encoding="utf-8")
    (task_b / "log.md").write_text(
        "# log\n[시작] 2026-06-20 09:00:00 hp · 등록만 함\n", encoding="utf-8"
    )
    (task_b / "context.hp.md").write_text(
        "## ▶ 다음\n아직 착수 전\n", encoding="utf-8"
    )

    res = find_active_task(tmp_path)
    assert res is not None
    assert res[0] == "namu-50-worked"


def test_is_closed_true_when_all_contexts_done(tmp_path):
    """context 권위: 모든 context.*.md ▶다음이 (완료)면 _is_closed=True, find_active_task에서 제외."""
    from task_resolve import _is_closed

    task_dir = tmp_path / "finished-task"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("# finished-task\n", encoding="utf-8")
    (task_dir / "log.md").write_text(
        "# log\n[시작] 2026-06-01 09:00:00 hp · 시작함\n", encoding="utf-8"
    )
    (task_dir / "context.hp.md").write_text("## ▶ 다음\n(완료)\n", encoding="utf-8")
    (task_dir / "context.samsung.md").write_text("## ▶ 다음\n(완료)\n", encoding="utf-8")

    assert _is_closed(task_dir) is True
    assert find_active_task(tmp_path) is None


def test_is_closed_legacy_fallback_to_log_when_no_context(tmp_path):
    """context 파일이 하나도 없는 레거시 task는 여전히 log 폴백([시작]…[완료]로 끝나면 닫힘)."""
    from task_resolve import _is_closed

    task_dir = tmp_path / "legacy-task"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("# legacy-task\n", encoding="utf-8")
    (task_dir / "log.md").write_text(
        "# log\n"
        "[시작] 2026-06-01 09:00:00 hp · 시작함\n"
        "[완료] 2026-06-02 09:00:00 hp · 종료\n",
        encoding="utf-8",
    )
    # context.*.md 없음(레거시)

    assert _is_closed(task_dir) is True
