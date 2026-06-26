# NAMU Claude Code Plugin

NAMU 메모리 서버 + 오케스트레이션 스킬을 Claude Code 플러그인으로 패키징.

## 필요 조건

- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `NAMU_HOME` 환경변수 — learnings/tasks/db 데이터가 저장될 경로 (필수)
- `NAMU_MACHINE` 환경변수 — 현재 PC 식별자 (미설정 시 `unknown`)

## 환경변수 설정

셸 프로파일(`.bashrc` / `.zshrc` / `.profile`)에 추가:

```bash
export NAMU_HOME="$HOME/namu-agent"   # 이 repo 절대경로
export NAMU_MACHINE="my-pc"           # 현재 PC 이름
```

> `NAMU_HOME` 미설정 시 플러그인 캐시 경로에 데이터가 생성되어 git 동기화가 깨집니다.

## 사용법

```bash
claude --plugin-dir /path/to/namu-agent/namu-plugin
```

### MCP 서버 수동 실행 (디버그용)

```bash
NAMU_HOME=/path/to/namu-agent uv run --script mcp_server.py
```

## 구조

| 파일 | 역할 |
|------|------|
| `mcp_server.py` | MCP 도구 서버 (namu_recall / namu_search / namu_record) |
| `db.py` | SQLite 읽기·쓰기 (검색 캐시) |
| `config.py` | 경로·환경변수 설정 |
| `hooks/session_recall.py` | SessionStart 훅 — 과거 교훈 자동 주입 |
| `skills/namu-task/SKILL.md` | /namu-task 오케스트레이션 스킬 |
| `.mcp.json` | MCP 서버 자동 등록 |
| `hooks/hooks.json` | SessionStart 훅 설정 |
