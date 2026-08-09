"""새 프로젝트 게이트(new_project_gate) 단위 시험.

도구 계층 시험(test_mcp_bowl.py)은 서브프로세스 격리라 느리고, 클라우드 쪽 시험은
이 저장소에 없다. 정책 자체는 순수 함수라 여기서 직접 조인다 — 특히 회원 격리와
문턱 경계처럼 도구 계층에서 재현하기 번거로운 것들.
"""
import pytest

import new_project_gate as gate


@pytest.fixture(autouse=True)
def _clean_gate():
    gate._reset_for_tests()
    yield
    gate._reset_for_tests()


def test_known_project_passes_without_flag():
    """게이트는 처음 보는 이름에만 걸린다 — 매번 걸리면 기존 사용이 깨진다."""
    gate.check("proj-x", ["proj-x", "proj-y"], new_project=False)


def test_unknown_project_without_flag_raises_with_numbered_choices():
    with pytest.raises(ValueError) as e:
        gate.check("new-one", ["proj-x", "proj-y"], new_project=False)
    msg = str(e.value)
    assert "1. proj-x" in msg
    assert "2. proj-y" in msg
    assert "0. 새 프로젝트로 만들기 — 'new-one'" in msg
    # 우회 방법(칸 이름)을 알려주면 AI가 사람 대신 그걸 집어 든다.
    assert "new_project" not in msg


def test_empty_pool_still_asks():
    """프로젝트가 하나도 없어도 첫 프로젝트 이름을 AI가 지어내면 안 된다."""
    with pytest.raises(ValueError) as e:
        gate.check("first-one", [], new_project=False)
    assert "하나도 없습니다" in str(e.value)
    assert "0. 새 프로젝트로 만들기 — 'first-one'" in str(e.value)


def test_flag_alone_on_the_first_call_is_rejected():
    """질문을 한 번도 안 보여준 이름은 확인 칸을 켜도 못 만든다.

    이것이 게이트의 급소다 — 처음 구현할 때 이 경우를 통과시켰더니, AI가 거절문을
    읽을 것도 없이 첫 호출부터 칸만 켜면 질문 없이 프로젝트가 생겼다(검수에서
    잡힘). 확인 칸은 부르는 쪽이 스스로 켤 수 있으므로 '사람이 골랐다'의 증거가
    되지 못한다.
    """
    with pytest.raises(ValueError) as e:
        gate.check("new-one", ["proj-x"], new_project=True)
    msg = str(e.value)
    assert "질문을 보여준 적이 없" in msg
    assert "1. proj-x" in msg  # 이때도 물어볼 질문을 함께 준다


def test_first_call_with_flag_still_opens_the_normal_two_step_path():
    """첫 호출을 거절하되 막다른 길이 되면 안 된다 — 그 거절도 '물어본 것'으로
    쳐서, 사람이 답하고 온 재호출은 통과해야 한다."""
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=True)
    gate._asked_at[("", "new-one")] -= gate.COOLDOWN_SECONDS + 1  # 사람이 답하고 온 상황
    gate.check("new-one", ["proj-x"], new_project=True)


def test_immediate_retry_with_flag_is_rejected():
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=False)
    with pytest.raises(ValueError) as e:
        gate.check("new-one", ["proj-x"], new_project=True)
    assert "시간이 없었습니다" in str(e.value)
    # 두 번째 거절도 질문을 다시 들려준다 — AI가 문안을 잃어버리지 않게.
    assert "1. proj-x" in str(e.value)


def test_retry_after_the_wait_passes(monkeypatch):
    monkeypatch.setattr(gate, "COOLDOWN_SECONDS", 0.0)
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=False)
    gate.check("new-one", ["proj-x"], new_project=True)


def test_memory_is_kept_per_project_name():
    """A를 물어본 것이 B를 만들 자격이 되지는 않는다 — 이름마다 따로 묻는다."""
    with pytest.raises(ValueError):
        gate.check("proj-a", ["proj-x"], new_project=False)
    gate._asked_at[("", "proj-a")] -= gate.COOLDOWN_SECONDS + 1
    with pytest.raises(ValueError) as e:
        gate.check("proj-b", ["proj-x"], new_project=True)
    assert "질문을 보여준 적이 없" in str(e.value)


def test_memory_is_kept_per_member():
    """클라우드 격리 — 회원 A에게 물은 것이 회원 B의 호출을 통과시키면 안 된다."""
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=False, scope="alice")
    gate._asked_at[("alice", "new-one")] -= gate.COOLDOWN_SECONDS + 1
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=True, scope="bob")
    # alice 쪽은 제 순서대로 통과한다(격리가 한쪽만 막는 것이 아님을 확인).
    gate.check("new-one", ["proj-x"], new_project=True, scope="alice")


def test_prime_for_tests_stands_in_for_the_two_steps():
    """게이트가 관심사가 아닌 시험들이 쓰는 지름길이 실제로 통과시키는지."""
    gate._prime_for_tests("new-one")
    gate.check("new-one", ["proj-x"], new_project=True)


def test_prime_for_tests_is_scoped_too():
    gate._prime_for_tests("new-one", scope="alice")
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=True, scope="bob")


def test_person_word_switches_for_the_cloud():
    """개인용은 '사용자', 클라우드는 '회원' — 붙은 AI가 누구에게 물어야 하는지가
    메시지에 그대로 드러나야 한다."""
    with pytest.raises(ValueError) as e:
        gate.check("new-one", ["proj-x"], new_project=False, person="회원")
    assert "회원에게" in str(e.value)
    assert "사용자" not in str(e.value)


def test_memory_is_cleared_once_the_project_exists():
    """프로젝트가 실제로 생기고 나면 그 이름의 질문 기억은 버린다.

    남겨두면 그 프로젝트가 나중에 사라졌을 때(폴더 삭제·다른 회원의 같은 이름)
    묻지도 않고 만들어지는 길이 열린다 — 기억을 버리므로 그때는 다시 묻는다.
    """
    with pytest.raises(ValueError):
        gate.check("new-one", ["proj-x"], new_project=False)
    gate.check("new-one", ["proj-x", "new-one"], new_project=False)  # 이제 아는 이름
    with pytest.raises(ValueError) as e:
        gate.check("new-one", ["proj-x"], new_project=True)
    assert "질문을 보여준 적이 없" in str(e.value)
