"""attachments.yaml 스토어 — 첨부 기록 그릇(namu-file-upload-download 4단계).

올린 파일의 **이력**을 담는다. 파일 몸통은 여기 없다 — 실물은 사용자 저장소의
`attach_file/`에 있고 그 폴더는 각 PC에서 격리되어 안 내려온다(config.ATTACH_*).
그래서 이 파일이 "무슨 파일이 있고 왜 올렸나"에 답하는 유일한 자리이며, 작아서
모든 기기로 내려와도 부담이 없다.

왜 기존 그릇에 안 담나(설계서 2판 7절):
- 교훈은 다시 쓸 배움을 담는 창고라 파일 이력이 섞이면 검색이 흐려진다.
- 작업일지는 작업 단위라 작업과 무관한 파일이 갈 곳이 없다.
- 쪽지는 지워지는 그릇이다.
- git 커밋 이력은 "왜·무슨 작업"을 모르고, 클라우드 서버 사본은 `--depth 1` 얕은
  복제라 이력 자체가 없다.

형식은 profile.yaml과 같은 append-only 다중 문서(`---` 구분)다. 고치거나 지우지
않으므로 **"지금 살아 있는 파일 목록"은 계산해서 얻는다**(`current_files`) —
status(올림/새 판/지움)가 그 계산의 유일한 근거다.
"""
import yaml
from ulid import ULID

import config as cfg

# 이 그릇에서 status가 받는 값. config.FIELDS의 닫힌 값 목록과 같아야 하며,
# 어긋나면 test_attachments.py가 깨진다(입력 검증은 config에서, 계산은 여기서
# 하므로 두 곳이 갈라지면 "저장은 되는데 목록에 안 잡히는" 값이 생긴다).
STATUS_UPLOADED = "올림"
STATUS_REVISED = "새 판"
STATUS_REMOVED = "지움"
VALID_STATUSES = (STATUS_UPLOADED, STATUS_REVISED, STATUS_REMOVED)


def _attachments_path(paths: "cfg.DataPaths | None" = None):
    p = paths or cfg.data_paths_for()
    return p.attachments_yaml or cfg.ATTACHMENTS_YAML_PATH


def record_attachment(
    path: str,
    bytes_: int,
    status: str,
    summary: str,
    reason: str,
    body: str,
    topic: str | None = None,
    project: str | None = None,
    supersedes: str | None = None,
    tags: list | None = None,
    via: str | None = None,
    paths: "cfg.DataPaths | None" = None,
) -> str:
    """첨부 기록 한 건을 남기고 id를 반환한다(append-only).

    `bytes_`에 밑줄이 붙은 것은 파이썬 내장 이름을 가리지 않기 위해서다 — 저장되는
    칸 이름과 도구 인자 이름은 설계서 그대로 `bytes`다.

    크기를 인자로 받는 이유(2026-08-07 실측): 목록을 만들 때 크기를 저장소에 물으면
    git이 크기를 알아내려고 빠진 파일 몸통을 전부 내려받는다(파일 2,548개에 7분 넘게
    안 끝나 중단). 그래서 크기는 올릴 때 한 번 적어 두고 목록은 여기서만 읽는다 —
    이 칸이 비면 목록 도구가 격리를 뚫는 쪽으로 되돌아갈 수밖에 없으므로 필수다.
    """
    path = (path or "").strip()
    if not path:
        raise ValueError("path(저장소 안 경로)는 필수입니다")
    if status not in VALID_STATUSES:
        raise ValueError(f"status는 {list(VALID_STATUSES)} 중 하나여야 합니다: {status!r}")
    try:
        size = int(bytes_)
    except (TypeError, ValueError):
        raise ValueError(f"bytes는 정수여야 합니다: {bytes_!r}") from None
    if size < 0:
        raise ValueError(f"bytes는 0 이상이어야 합니다: {size}")

    doc = {
        "id": str(ULID()),
        "timestamp": cfg.now().isoformat(),
        "path": path,
        "bytes": size,
        "status": status,
        "summary": summary,
        "reason": reason,
        "body": body,
        "task": topic,
        "project": project,
        "supersedes": supersedes,
        "machine": cfg.NAMU_MACHINE,
        "tags": tags or [],
        "via": via,
    }

    yaml_path = _attachments_path(paths)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False)
    with yaml_path.open("a", encoding="utf-8") as f:
        f.write("---\n" + yaml_str)

    return doc["id"]


def load_all(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """기록 전부를 적은 순서(오래된 것 먼저)로 반환. 파일이 없으면 빈 목록.

    깨진 yaml에 예외를 던지지 않는 것은 memo.load_all과 같은 판단이다 — 한 항목이
    깨졌다고 recall 전체가 실패하면 손해가 훨씬 크다.
    """
    yaml_path = _attachments_path(paths)
    try:
        raw = yaml_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        docs = list(yaml.safe_load_all(raw))
    except yaml.YAMLError:
        return []
    return [d for d in docs if isinstance(d, dict)]


def current_files(paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """**지금 저장소에 살아 있는 파일**만, 경로마다 최신 기록 한 건씩 반환한다.

    기억이 append-only라 "지금 있는 것"이 파일에 그대로 적혀 있지 않다 — 같은 경로에
    올림 → 새 판 → 지움이 차곡차곡 쌓이므로, 경로별로 마지막 기록을 보고 그것이
    '지움'이면 뺀다. 목록 도구(5단계)가 이 결과와 저장소의 이름 목록을 맞춰 본다.

    순서는 최신 기록이 앞이다(시간 역순) — 방금 올린 것을 먼저 찾기 때문이다.
    """
    latest: dict[str, dict] = {}
    for entry in load_all(paths):
        key = entry.get("path")
        if not key:
            continue
        latest[key] = entry
    alive = [e for e in latest.values() if e.get("status") != STATUS_REMOVED]
    alive.sort(key=lambda e: str(e.get("timestamp") or ""), reverse=True)
    return alive


def history(path: str, paths: "cfg.DataPaths | None" = None) -> list[dict]:
    """한 경로의 기록 전부를 오래된 순으로 반환한다(지운 뒤 다시 올린 것도 포함).

    "그 자료 어디 갔지?"에 "언제 뺐고 이유는 이것"이라고 답하려면 살아 있는 것만
    보여주는 current_files로는 부족하다.
    """
    path = (path or "").strip()
    return [e for e in load_all(paths) if e.get("path") == path]
