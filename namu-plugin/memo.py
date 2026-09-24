"""memo 그릇 — 스틱노트(namu-56).

NAMU의 다른 그릇과 성질이 정반대인 유일한 저장소다.

- **mutable**: 떼면 파일에서 항목이 사라진다. tombstone(삭제 표식)을 남기지 않는다.
  이력이 남아야 하는 기억(learnings/profile/tasks)은 append-only, 쓰고 버리는 기억은
  mutable — 이 경계가 namu-56의 설계 결정이다.
- **교훈 색인과 섞지 않는다**: 지식베이스(learnings) 오염 0이 이 그릇의 존재 이유다.
  "영화 8시 20분" 같은 일회성 메모가 갈 곳이 없어 learnings.yaml로 밀려들어오던
  문제를 해결하려고 만들었으므로, 교훈 색인에 섞으면 목적을 배반한다. 검색 색인은
  **자기 표를 따로** 갖는다(`bowl_memo`, fts5-memo-tasks-index — namu-56이 금지한
  것은 교훈 색인에 섞이는 것이지 색인을 갖는 것이 아니었다). 원본은 여전히 이 파일이다.
- **git merge="file"**: 줄 단위 union 병합을 쓰면 한쪽에서 뗀 메모가 다른 PC의
  파일에 남아 있다가 병합 때 되살아난다(union은 삭제를 표현하지 못한다).

저장 형식은 YAML 리스트 **한 문서**다(profile.yaml의 `---` 다중 문서 append와 다르다).
mutable 그릇은 어차피 쓸 때마다 파일 전체를 다시 쓰므로, 통째로 읽고 통째로 쓰는
형식이 가장 단순하고 떼기 구현이 자명해진다.

그 대가로 붙이기·떼기가 "전부 읽기 → 고치기 → 전부 쓰기"가 되어 **잠금이 필요하다**
(`_locked`). 다른 그릇은 끝에 덧붙이기만 하므로 이 문제가 없다.
"""
import contextlib
import os
import tempfile
import threading
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


def _load_for_write(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """쓰기 직전에 읽는 목록 — `load_all`과 달리 깨진 파일을 빈 목록으로 삼키지 않는다.

    읽기(브리핑·recall)는 깨진 파일을 빈 목록으로 흡수해야 하지만, 쓰기가 같은 규칙을
    따르면 "빈 목록 + 새 한 장"으로 파일을 덮어써 기존 메모가 전부 사라진다. 병합이
    멈춰 충돌 표시가 워킹트리에 남은 짧은 순간에 붙이기가 끼면 실제로 이렇게 된다
    (2026-09-25 최종 검토). 그래서 파일이 있는데 목록으로 읽히지 않으면 쓰지 않고
    거절한다 — 붙이기가 실패하는 편이 붙여 둔 메모를 잃는 편보다 낫다.
    """
    path = _memo_path(paths)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        docs = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"메모 파일({path})을 읽을 수 없어 쓰지 않았습니다 — 기존 메모를 덮어쓰지 않기 "
            f"위해서입니다. 파일을 고친 뒤 다시 시도해 주세요: {exc}"
        ) from exc
    if docs is None:
        return []
    if not isinstance(docs, list):
        raise ValueError(
            f"메모 파일({path})이 목록 형식이 아니어서 쓰지 않았습니다 — 파일을 고친 뒤 "
            "다시 시도해 주세요."
        )
    return [d for d in docs if isinstance(d, dict)]


# 같은 프로세스 안의 겹침 — 웹 서버는 동기 도구를 스레드 풀에서 돌리므로 한 프로세스
# 안에서도 붙이기 둘이 겹친다. 파일 잠금도 열기마다 따로 걸려 스레드끼리 막아 주긴
# 하지만, 윈도우 쪽은 기다리다 10초 뒤 포기하는 방식이라 스레드끼리는 여기서 먼저
# 줄을 세워 파일 잠금에서 기다릴 일을 프로세스 사이의 겹침으로만 줄인다.
_THREAD_LOCK = threading.Lock()

# 윈도우 msvcrt.locking(LK_LOCK)은 1초 간격으로 열 번 시도한 뒤 OSError를 던진다.
# 메모 쓰기는 밀리초 단위라 그만큼 막힐 일은 없지만, 다른 프로세스가 잠시 오래 쥐고
# 있어도 기록이 통째로 실패하지 않게 몇 번 더 기다린다.
_WINDOWS_LOCK_ROUNDS = 6


@contextlib.contextmanager
def _locked(paths: "cfg.DataPaths | None" = None):
    """memo.yaml 읽기-고치기-쓰기 구간 전체를 잠근다.

    ## 왜 (2026-09-25 검토 실측)

    붙이기 40개를 동시에 돌리자 **5장만 남았다** — 각자 같은 옛 목록을 읽고 제 것
    하나만 붙여 덮어써서다. 이 그릇은 tombstone이 없어 사라진 메모를 되찾을 길도 없다.
    원자적 교체(`_write_all`)는 "쓰다 만 파일"만 막을 뿐 "남의 쓰기를 덮는 것"은 못
    막는다.

    ## 어떻게

    스레드 잠금 + 프로세스 사이 파일 잠금 두 겹이다. 파일 잠금이 필요한 이유는 같은
    기계에서 stdio 서버(Claude Code 세션마다 하나)와 웹 서버가 **따로 떠서** 같은
    memo.yaml을 쓰기 때문이다. 잠금 파일(`.memo.lock`)은 memo.yaml 옆에 두고 지우지
    않는다 — 지웠다 다시 만들면 두 프로세스가 서로 다른 파일을 잠그는 틈이 생긴다.
    내용은 늘 비어 있어 동기화에 한 번 실려도 다시 바뀌지 않는다.

    POSIX는 `fcntl.flock`, 윈도우(미니PC)는 `msvcrt.locking`이다. 어느 쪽이든 파일을
    닫으면 잠금이 풀리므로 도중에 예외가 나도 잠금이 남지 않는다.
    """
    memo_path = _memo_path(paths)
    memo_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = memo_path.parent / ".memo.lock"
    with _THREAD_LOCK:
        with open(lock_path, "a+b") as fh:
            if os.name == "nt":  # pragma: no cover - 윈도우(미니PC)에서만 도는 갈래
                import msvcrt

                fh.seek(0)
                for attempt in range(_WINDOWS_LOCK_ROUNDS):
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        if attempt == _WINDOWS_LOCK_ROUNDS - 1:
                            raise
                try:
                    yield
                finally:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


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


def layers(entry: dict) -> tuple[str, str, str]:
    """메모 한 장에서 (summary, reason, body)를 꺼낸다. **읽는 쪽은 전부 이걸 쓴다.**

    3층 도입(namu-65) 전에 붙인 메모는 `text` 한 칸뿐이다. 그 시절 text는 붙여둔
    내용 전부였으므로 요약 자리와 원문 자리 양쪽의 폴백이 된다 — 화면은 종전과 똑같이
    보이고, 새로 붙는 메모부터 브리핑에 한 줄만 실린다.
    """
    legacy = entry.get("text") or ""
    summary = entry.get("summary") or legacy
    body = entry.get("body") or legacy
    reason = entry.get("reason") or ""
    return str(summary), str(reason), str(body)


def add(
    text: str | None = None,
    tags: list | None = None,
    via: str | None = None,
    paths: "cfg.DataPaths | None" = None,
    *,
    summary: str | None = None,
    reason: str | None = None,
    body: str | None = None,
) -> str:
    """메모 한 장을 붙이고 id를 반환한다.

    스키마는 최소로 고정한다(id/timestamp/3층/machine/tags/via) — 유효기간(만료)은
    넣지 않기로 결정했다(2026-07-25 사용자 확정). 자동 삭제는 "내가 안 지웠는데
    없어졌다"가 되기 쉽고, 뗄 시점은 사람이 정하는 게 맞다.

    namu-65 3단계로 3층이 들어왔다. 옛 `text`는 붙여둔 내용 자체였으므로 `body`로
    간다 — 요약(`summary`)만 브리핑에 실리고 원문은 통째로 남는 구조다. 옛 이름으로
    부르면 summary/body 양쪽을 그 값으로 채운다(화면이 종전과 같아진다).
    """
    text = (text or "").strip()
    summary = (summary or "").strip() or text
    body = (body or "").strip() or text
    if not summary or not body:
        raise ValueError("빈 메모는 붙일 수 없습니다(요약과 원문이 필요합니다)")

    entry = {
        "id": str(ULID()),
        "timestamp": cfg.now().isoformat(),
        "summary": summary,
        "reason": (reason or "").strip() or None,
        "body": body,
        "machine": cfg.NAMU_MACHINE,
        "tags": tags or [],
        "via": via,
    }
    with _locked(paths):
        entries = _load_for_write(paths)
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

    # 고르기부터 쓰기까지 한 잠금 안에서 한다 — 고른 뒤 잠그면 그 사이 붙은 메모가
    # 옛 목록으로 덮여 사라진다.
    with _locked(paths):
        entries = _load_for_write(paths)
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
