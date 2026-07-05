# namu-17-subagent-parity — 네이티브 서브에이전트 대칭 (⑦)
📅 생성 2026-07-05 [samsung] · 🔗 관련: namu-16-live-verify (메모리·자동주입 대칭 완료 후속)

## 목적
NAMU의 실행/워커 층(오케스트레이터 + namu-coder + namu-reviewer 서브에이전트)이 현재 Claude Code에만 존재해 멀티스텝 작업이 사실상 CC에 종속됨. agy에도 같은 워커 구조를 세워 "봉투 둘·내용물 하나" 대칭을 실행 층까지 완성한다.

## 완료조건
- [ ] agy 1.0.16 네이티브 서브에이전트 형식 실측 확정 (정의 파일 위치·문법 — plan.md 결정 테이블에 기록)
- [ ] coder·reviewer 워커 정의를 agy 형식으로 포팅 (내용물 동일)
- [ ] 플러그인 내 namu-task 스킬이 agy에서 깨지는 문제 해소 (agy 분기 or 숨김 — 실측 결과로 결정)
- [ ] 플러그인 자급자족 검토: `.claude/agents/namu-*.md` → `namu-plugin/agents/` 이동 여부 결정 (13번 보류분)
- [ ] 라이브 검증: agy에서 워커 흐름(코딩→검수→사용자 게이트) 통과
- [ ] 규칙 유지 확인: 검수 fail 자동 재실행 금지 · recall/record는 오케스트레이터만

## 범위 밖
- 이종 엔진 워커(Ollama/유료 Gemini) spawn 어댑터 — 후속 로드맵
- namu_workers.yaml override 마법사
