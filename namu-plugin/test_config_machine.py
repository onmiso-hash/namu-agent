"""NAMU_MACHINE 해석 규칙(_resolve_machine) 회귀 테스트.

주의: repo 루트 .env에 NAMU_MACHINE=samsung이 있어 config 모듈을 import/reload하면
load_dotenv가 os.environ을 오염시켜 테스트가 깨진다. 따라서 config 모듈을 reload하지
않고 _resolve_machine 순수 함수만 직접 호출해 검증한다.
"""
from config import _resolve_machine


def test_env_value_present_is_used_as_is():
    assert _resolve_machine("my-laptop") == "my-laptop"


def test_env_value_with_surrounding_whitespace_is_stripped():
    assert _resolve_machine("  my-laptop  ") == "my-laptop"


def test_env_value_preserves_case():
    assert _resolve_machine("MyLaptop") == "MyLaptop"


def test_env_none_falls_back_to_hostname(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "HP-DESKTOP")
    assert _resolve_machine(None) == "hp-desktop"


def test_env_empty_string_falls_back_to_hostname(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "HP-DESKTOP")
    assert _resolve_machine("") == "hp-desktop"


def test_env_whitespace_only_falls_back_to_hostname(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "HP-DESKTOP")
    assert _resolve_machine("  ") == "hp-desktop"


def test_hostname_also_empty_falls_back_to_unknown(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "")
    assert _resolve_machine(None) == "unknown"


def test_hostname_whitespace_only_falls_back_to_unknown(monkeypatch):
    monkeypatch.setattr("config.platform.node", lambda: "   ")
    assert _resolve_machine(None) == "unknown"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
