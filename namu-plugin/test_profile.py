"""profile.py 단위 테스트 (namu-49 Unit A — 2그릇 메모리의 profile 그릇).

실제 ~/.namu/memory/profile.yaml을 절대 건드리지 않는다 — cfg.PROFILE_YAML_PATH를
tmp_path 하위로 monkeypatch한다(test_cache_stale.py/test_hook_stale_rebuild.py의
격리 패턴을 따름).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

import config as cfg
import profile as _profile


def _isolate_cfg(monkeypatch, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    monkeypatch.setattr(cfg, "PROFILE_YAML_PATH", yaml_path)
    monkeypatch.setattr(cfg, "NAMU_MACHINE", "test")
    return yaml_path


def test_record_fact_then_load_all_and_active(monkeypatch, tmp_path):
    yaml_path = _isolate_cfg(monkeypatch, tmp_path)
    assert not yaml_path.exists()

    entry_id = _profile.record_fact(
        subject="user", statement="선호 언어는 한국어", source="사용자가 직접 말함",
    )

    assert isinstance(entry_id, str) and entry_id

    all_docs = _profile.load_all()
    assert len(all_docs) == 1
    doc = all_docs[0]
    assert doc["id"] == entry_id
    assert doc["subject"] == "user"
    assert doc["statement"] == "선호 언어는 한국어"
    assert doc["source"] == "사용자가 직접 말함"
    assert doc["machine"] == "test"
    assert doc["verified_by"] == "human"
    assert doc["tags"] == []
    assert doc["supersedes"] is None
    assert "timestamp" in doc

    active_docs = _profile.active()
    assert len(active_docs) == 1
    assert active_docs[0]["id"] == entry_id


def test_supersedes_chain_only_latest_is_active(monkeypatch, tmp_path):
    """A <- B <- C 체인이면 active() == [C]만 남는다."""
    _isolate_cfg(monkeypatch, tmp_path)

    id_a = _profile.record_fact(subject="user", statement="A", source="s1")
    id_b = _profile.record_fact(subject="user", statement="B", source="s2", supersedes=id_a)
    id_c = _profile.record_fact(subject="user", statement="C", source="s3", supersedes=id_b)

    all_docs = _profile.load_all()
    assert [d["id"] for d in all_docs] == [id_a, id_b, id_c]

    active_docs = _profile.active()
    assert len(active_docs) == 1
    assert active_docs[0]["id"] == id_c
    assert active_docs[0]["statement"] == "C"


def test_load_all_and_active_empty_when_file_missing(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    assert _profile.load_all() == []
    assert _profile.active() == []


def test_source_required(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        _profile.record_fact(subject="user", statement="뭔가", source="")


def test_verified_by_invalid_rejected(monkeypatch, tmp_path):
    _isolate_cfg(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        _profile.record_fact(
            subject="user", statement="x", source="y", verified_by="bogus",
        )


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
