# context @ samsung — namu-17-subagent-parity
> 🔄 갱신 2026-07-05 22:39 [samsung]

## ▶ 다음 (한 줄)
잔여 완료조건: 3번(namu-task 스킬 agy 깨짐 해소) 착수 + 4번(플러그인 동봉 여부) 결정 + run_command 권한 게이트 확인

## 지금 어디까지
- ✅ 완료조건 1번(형식 실측 확정) — plan.md 결정 테이블 07-05 행
- ✅ 완료조건 2번(coder·reviewer 포팅) — `.agents/agents/namu-{coder,reviewer}/agent.md`, 도구명 전종 런타임 확정(1차 fail서 edit_file 제거 → 2차 executor 통과=잔여 5종 유효 보증)
- ✅ 완료조건 5번(라이브 워커 흐름) — coder가 scratch_worker_test.py 실생성(디스크 확인), reviewer가 "pass"+근거 반환, 비동기 완주. CC 워커 흐름과 1:1 대칭
- 🔶 완료조건 6번(규칙 유지) — fail 시 사람 게이트는 1차 fail 때 실천됨. recall/record 오케스트레이터 전용은 namu-task 절차(3번)와 함께 확인
- ⬜ 완료조건 3번(namu-task 스킬 agy 깨짐 해소) — 미착수
- ⬜ 완료조건 4번(플러그인 동봉 여부 결정) — 워크스페이스 배치 검증됨, 플러그인 봉투 agents 카테고리 런타임 미검증

## 막힘·주의 (있으면)
- ⚠️ reviewer가 linter를 "터미널 명령 실행 권한 문제"로 못 돌리고 육안 검수 — run_command가 tools에 있어도 서브에이전트 실행이 권한 게이트에 막히는 듯. agy 권한 설정(settings/toolPermission) 확인 필요, 검수 품질 직결
- 바이너리 문자열≠등록 도구(edit_file 실례) — 도구명은 fail-fast 에러 메시지가 가장 신뢰할 근거
- (확정) agent.md 핫 리로드 지원 — 같은 세션서 수정→다음 invoke 즉시 반영(사용자 확인)

## 만지는 중인 파일
- (커밋 완료) `.agents/agents/namu-{coder,reviewer}/agent.md` · `docs/plan.md` 결정 행 · tasks 기록 — 검증 잔재(namu-load-probe·scratch_worker_test.py·image.png)는 삭제됨
