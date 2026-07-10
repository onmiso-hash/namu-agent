# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML>=6.0", "python-ulid>=3.0.0", "python-dotenv>=1.0.0", "typing-extensions>=4.0"]
# ///
"""PreInvocation 훅 — agy 세션 컨텍스트 자동 주입.

conversationId 기반 플래그 파일로 세션당 1회만 주입.
어떤 에러도 {} 출력 + exit 0 (세션 안 막음).
`--heal` 인자로 단독 실행하면 mcp_config.json 절대경로 교정만 즉시 수행하고 종료한다(설치 직후용).
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _ensure_db(cfg) -> None:
    import db

    if not cfg.NAMU_DB_PATH.exists():
        db.init_db()
        if cfg.LEARNINGS_YAML_PATH.exists():
            db.rebuild_from_yaml()
    elif db.cache_is_stale(cfg.LEARNINGS_YAML_PATH, cfg.NAMU_DB_PATH):
        # 외부 터미널에서 git pull 후 agy를 시작한 경우 db가 낡아 있을 수 있음
        # (07-10 실측: yaml 40건 vs db 37건) — 세션 브리핑이 최신 교훈을 반영하도록 재생성.
        db.rebuild_from_yaml()


def heal_mcp_config(plugin_root: Path) -> bool:
    """agy 설치본 mcp_config.json의 상대경로 args를 절대경로로 교정.

    agy는 ${...} 변수 치환·~ 확장이 없어 절대경로만 동작하는데,
    동봉 mcp_config.json의 args는 워크스페이스 CWD 기준 상대경로라
    repo 밖(설치본)에서 MCP가 조용히 죽는다. 개발 repo는 절대 건드리지 않는다.
    재작성했으면 True, 무변경(이미 절대경로/파일 없음/에러)이면 False.
    """
    try:
        cfg_path = plugin_root / "mcp_config.json"
        if not cfg_path.exists():
            return False

        # 가드: 개발 repo(namu-plugin/의 부모에 .git)는 절대 재작성하지 않는다
        if (plugin_root.parent / ".git").exists():
            return False

        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        entry = servers.get("namu-memory", {})
        args = entry.get("args")
        if not isinstance(args, list):
            return False

        target = "namu-plugin/mcp_server.py"
        abs_path = str(plugin_root / "mcp_server.py")
        changed = False
        for i, arg in enumerate(args):
            if isinstance(arg, str) and arg.endswith(target) and not Path(arg).is_absolute():
                args[i] = abs_path
                changed = True

        if not changed:
            return False

        cfg_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def main() -> None:
    if "--heal" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        healed = heal_mcp_config(Path(__file__).resolve().parent.parent)
        if healed:
            abs_path = str(Path(__file__).resolve().parent.parent / "mcp_server.py")
            print(f"[namu --heal] mcp_config.json 절대경로 교정 완료: {abs_path}")
        else:
            print("[namu --heal] 무변경 (이미 절대경로이거나 대상 아님)")
        sys.exit(0)

    # 네이티브 Windows 파이프 stdout은 cp949라 이모지 출력 시 UnicodeEncodeError (#16 statusLine과 동일 패턴)
    sys.stdout.reconfigure(encoding="utf-8")
    heal_mcp_config(Path(__file__).resolve().parent.parent)
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw)
        except Exception:
            print("{}")
            sys.exit(0)

        conversation_id = data.get("conversationId")
        if not conversation_id:
            print("{}")
            sys.exit(0)

        flag = Path(tempfile.gettempdir()) / f"namu_injected_{conversation_id}"
        if flag.exists():
            print("{}")
            sys.exit(0)

        # agy 플러그인 훅의 cwd는 플러그인 설치 폴더 → 워크스페이스 .env를 못 찾음.
        # config가 find_dotenv(usecwd=True)로 .env를 찾기 전에 워크스페이스로 이동한다.
        workspace_paths = data.get("workspacePaths") or []
        if workspace_paths:
            try:
                os.chdir(workspace_paths[0])
            except OSError:
                pass

        # tasks는 프로젝트 로컬 저장소(namu-26 이원화) — 현재 워크스페이스 경로를
        # project_dir로 넘겨 그 프로젝트의 tasks/를 보게 한다. workspacePaths가 없으면
        # (위 chdir도 스킵됐으므로) 현재 프로세스 cwd로 폴백한다.
        project_dir = workspace_paths[0] if workspace_paths else os.getcwd()

        import config as cfg
        from session_context import build_context_markdown

        _ensure_db(cfg)

        with sqlite3.connect(cfg.NAMU_DB_PATH) as conn:
            md = build_context_markdown(conn, cfg.NAMU_MACHINE, project_dir)

        if md:
            print(json.dumps({"injectSteps": [{"ephemeralMessage": md}]}, ensure_ascii=False))
            flag.touch()
        else:
            print("{}")

    except Exception:
        print("{}")

    sys.exit(0)


if __name__ == "__main__":
    main()
