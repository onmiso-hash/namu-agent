# NAMU Agent System

벤더 독립 멀티에이전트 시스템. 어느 AI에도 종속되지 않고, 작업에 맞는 에이전트를 생성/배분하며, 성공·실패 기록을 공유해 스스로 학습한다.

## 폴더 역할

| 폴더 | 역할 |
|------|------|
| `core/` | 오케스트레이터 엔진 — 에이전트 생성·배분·모니터링 |
| `adapters/` | AI 어댑터 — Claude/GPT/Gemini/Ollama 등 벤더별 구현 |
| `memory/` | 공유 학습 기억 (`learnings.md`) — GitHub 동기화 대상 |
| `tasks/` | 작업별 기록 파일 (`task.md`, `result.md`, `log.md`) |
| `db/` | SQLite — 패턴 분석·통계용 |

## 핵심 파일

- `adapters/base.py` — 모든 어댑터가 구현해야 할 `AIAdapter` ABC
- `config.py` — 경로·API 키·활성 어댑터 설정
- `memory/learnings.md` — append-only 학습 기록 (절대 삭제 금지)

## 설계 문서

- `docs/plan.md` — NAMU 전체 계획·결정 이력·로드맵
- `docs/mcp_memory_design.md` — MCP 메모리 서버 상세 설계 (스키마, SQLite 테이블, 도구 명세)

구현 작업 시 위 문서를 먼저 참조할 것.

## 어댑터 우선순위

로컬(Ollama) → 구독(Claude.ai/ChatGPT Plus) → API

새 어댑터 추가 시: `AIAdapter`를 상속하고 `ENABLED_ADAPTERS`에 이름을 등록한다.

## 개발 원칙

1. **벤더 독립** — 특정 AI SDK에 직접 의존하는 코드는 `adapters/` 안에만 둔다.
2. **파일이 곧 기억** — 중요한 상태는 파일로 남긴다. DB는 분석 보조 수단이다.
3. **append-only 로그** — `memory/learnings.md`와 작업 로그는 수정·삭제하지 않는다.
4. **승인 게이트** — 워커 에이전트 호출 전 오케스트레이터가 반드시 확인한다.
5. **판단 이유 기록** — 결과뿐 아니라 판단 근거까지 남겨야 자동 학습이 가능하다.

## 기술 스택

- Python 3.12+
- SQLite (내장)
- GitHub (메모리 동기화)
