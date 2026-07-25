"""memo 그릇 — 스틱노트(namu-56).

NAMU의 다른 그릇과 성질이 정반대인 유일한 저장소다.

- **mutable**: 떼면 파일에서 항목이 사라진다. tombstone(삭제 표식)을 남기지 않는다.
  이력이 남아야 하는 기억(learnings/profile/tasks)은 append-only, 쓰고 버리는 기억은
  mutable — 이 경계가 namu-56의 설계 결정이다.
- **SQLite 인덱싱 없음**: 지식베이스(learnings) 오염 0이 이 그릇의 존재 이유다.
  "영화 8시 20분" 같은 일회성 메모가 갈 곳이 없어 learnings.yaml로 밀려들어오던
  문제를 해결하려고 만들었으므로, 검색 인덱스에 섞으면 목적을 배반한다.
- **git merge="file"**: 줄 단위 union 병합을 쓰면 한쪽에서 뗀 메모가 다른 PC의
  파일에 남아 있다가 병합 때 되살아난다(union은 삭제를 표현하지 못한다).

저장 형식은 YAML 리스트 **한 문서**다(profile.yaml의 `---` 다중 문서 append와 다르다).
mutable 그릇은 어차피 쓸 때마다 파일 전체를 다시 쓰므로, 통째로 읽고 통째로 쓰는
형식이 가장 단순하고 떼기 구현이 자명해진다.
"""
import os
import tempfile
from pathlib import Path

import yaml
from ulid import ULID

import config as cfg


def _memo_path(paths: "cfg.DataPaths | None" = None) -> Path:
    p = paths or cfg.data_paths_for()
    return p.memo_yaml or cfg.MEMO_YAML_PATH


def load_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """붙어 있는 메모 전부를 붙인 순서(오래된 것 먼저)로 반환. 파일이 없으면 빈 목록.

    깨진 yaml에 예외를 던지지 않고 빈 목록으로 처리한다 — 메모는 부가 기능이라,
    한 줄 깨졌다고 세션 브리핑이나 recall 전체가 실패하면 손해가 훨씬 크다.
    """
    path = _memo_path(paths)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        docs = yaml.safe_load(raw)
    except yaml.YAMLError:
        return []
    if not isinstance(docs, list):
        return []
    return [d for d in docs if isinstance(d, dict)]


def _write_all(entries: list[dict], paths: "cfg.DataPaths | None" = None) -> None:
    """메모 전체를 파일에 쓴다(원자적 교체).

    mutable 그릇이라 매번 전체를 덮어쓰므로, 쓰는 도중 중단되면 메모가 통째로
    날아갈 수 있다. 임시 파일에 먼저 쓰고 os.replace로 갈아끼워 그 창을 없앤다 —
    append-only 그릇에는 없던 위험이라 여기서만 필요한 방어다.
    """
    path = _memo_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(entries, allow_unicode=True, default_flow_style=False, sort_keys=False)

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".memo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def short_ids(entries: list[dict], minimum: int = 8) -> dict[str, str]:
    """각 메모의 id → **지금 붙어 있는 메모들 사이에서 유일한 최단 접두**.

    브리핑에 26자 ULID를 그대로 실으면 메모 본문이 묻히므로 앞부분만 보여주는데,
    고정 길이로 자르면 안 된다는 게 실측에서 드러났다: ULID 앞 10자는 생성 시각이라
    **같은 밀리초에 붙인 메모들은 앞 8자가 똑같다**. 그 상태로 8자를 보여주면
    사용자가 화면의 값을 그대로 복사해도 "여러 장과 일치합니다"로 거절당한다 —
    보여준 것이 곧 동작하지 않는 셈이다. 그래서 표시용 길이를 목록 전체를 보고
    정한다(충돌이 없으면 minimum 그대로).
    """
    ids = [str(e.get("id") or "") for e in entries]
    result: dict[str, str] = {}
    for full in ids:
        length = minimum
        while length < len(full) and sum(1 for other in ids if other.startswith(full[:length])) > 1:
            length += 1
        result[full] = full[:length]
    return result


def add(
    text: str,
    tags: list | None = None,
    via: str | None = None,
    paths: "cfg.DataPaths | None" = None,
) -> str:
    """메모 한 장을 붙이고 id를 반환한다.

    스키마는 최소로 고정한다(id/timestamp/text/machine/tags/via) — 유효기간(만료)은
    넣지 않기로 결정했다(2026-07-25 사용자 확정). 자동 삭제는 "내가 안 지웠는데
    없어졌다"가 되기 쉽고, 뗄 시점은 사람이 정하는 게 맞다.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text는 필수입니다(빈 메모는 붙일 수 없습니다)")

    entry = {
        "id": str(ULID()),
        "timestamp": cfg.now().isoformat(),
        "text": text,
        "machine": cfg.NAMU_MACHINE,
        "tags": tags or [],
        "via": via,
    }
    entries = load_all(paths)
    entries.append(entry)
    _write_all(entries, paths)
    return entry["id"]


def remove(memo_id: str, paths: "cfg.DataPaths | None" = None) -> dict:
    """메모 한 장을 뗀다. 뗀 항목을 반환한다.

    id 전체 대신 **앞부분만** 줘도 된다(ULID 26자를 사람이 옮겨 적는 건 비현실적).
    다만 접두가 여러 장에 걸리면 지우지 않고 후보를 들어 거절한다 — 메모는 지우면
    복구할 수 없으므로(tombstone 없음) 애매하면 아무것도 하지 않는 편이 안전하다.
    """
    memo_id = (memo_id or "").strip()
    if not memo_id:
        raise ValueError("id는 필수입니다")

    entries = load_all(paths)
    exact = [e for e in entries if e.get("id") == memo_id]
    matches = exact or [e for e in entries if str(e.get("id", "")).startswith(memo_id)]

    if not matches:
        raise ValueError(
            f"id {memo_id!r}인 메모가 없습니다 — 붙어 있는 메모: {len(entries)}장"
        )
    if len(matches) > 1:
        ids = ", ".join(str(e.get("id")) for e in matches)
        raise ValueError(f"id {memo_id!r}가 메모 여러 장과 일치합니다: {ids} — 더 길게 주세요")

    target = matches[0]
    _write_all([e for e in entries if e is not target], paths)
    return target
