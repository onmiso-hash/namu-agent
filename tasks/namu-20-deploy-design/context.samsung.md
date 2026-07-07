# context @ samsung — namu-20-deploy-design
> 🔄 갱신 2026-07-06 15:52 [samsung]

## ▶ 다음 (한 줄)
**세션 시작 시 ⓐ 게이트 재안내부터**: mcp_config 절대경로 주입 — A안(훅 self-healing, 추천: 사용자 조작 0·재설치 자가복구, 단 설치 후 첫 세션 1회 MCP 부재) vs B안(설치 후 1회 스크립트/문서) 사용자 선택 → 이후 ⓑ 워커·스킬 호출명 엔진별 폴백 ⓒ 분리 모드 workers yaml 부재 ⓓ NAMU_MACHINE 온보딩 설계 → plan.md 기록

## 지금 어디까지
- 설계 게이트: ① 메모리=~/.namu 폴백+override ② 워커=플러그인 동봉 ③ agy 한계=실측 — 전부 사용자 승인
- 구현 완료(검수 PASS, 커밋 b5a2c2d·푸시 완료): config.py 3분기 폴백, plugin.json 0.1.2+"agents" 필드, agents/(agy)·cc-agents/(CC) 분리 동봉
- CC 실측 ①② PASS: namu:namu-coder/reviewer 노출·junk 미노출, NAMU_HOME 3분기 전수 검증
- **agy 실측 ③ 완료**(사용자 라이브, D:\Temp\namu-agy-ws): 스킬 PASS(단 호출명 `/namu:SKILL`=파일명 기반), MCP FAIL→원인 규명, 워커 PASS(무접두 `namu-reviewer` 실호출 성공)
- **MCP 경로 실측 완료**: 절대경로 ✓ / `~` ✗ / `${PLUGIN_ROOT}` ✗(agy는 `${...}` 치환 자체가 없음) = **agy 플러그인 MCP는 절대경로만 가능** 확정. 절대경로로 record 실측까지 PASS — ~/.namu 스캐폴딩+ULID+machine:unknown 물증 정합. 분리 모드 agy 라이브 전수 검증 끝
- 부수: PreInvocation 훅은 repo 밖 정상 작동(훅 CWD=플러그인 폴더, MCP CWD=워크스페이스 비대칭). 설치본 mcp_config는 절대경로로 정상화해 둠(이 기기 한정 동작)

## 막힘·주의 (있으면)
- 🔴 **mcp_config 소스 수정 미결**: 소스에 절대경로 불가(사용자별 상이) → 설치 시 절대경로 주입 방안 설계 필요(훅 self-healing vs 설치 스크립트/문서 — 사용자 게이트 대기)
- ⚠️ 이 dev PC는 NAMU_MACHINE=samsung이 OS 사용자 환경변수로 영구 등록 — 분리 모드 실측 시 세션 내 제거 필수(.env 상속과 별개 오염원)
- ⚠️ 호출명 엔진별 상이 확정: 워커 CC=`namu:namu-coder`/agy=`namu-coder`, 스킬 CC=`namu:namu-task`/agy=`/namu:SKILL` — 폴백 설계 필요
- ⚠️ agy plugin install=비파괴 병합, 소스에서 지운 파일이 설치본에 잔존 → 수동 청소 필요
- ⚠️ 분리 모드 신규 사용자 NAMU_MACHINE 미설정 → machine="unknown" = 멀티 PC 식별 공백 (온보딩 설계 대상)
- 참고: CC 세션 env에 repo .env 값(NAMU_HOME 등)이 실려 자식 프로세스로 상속됨 — dev 환경 정상, 실측 시 오염 주의
- 참고: agy 서브에이전트 도구 실행에 사용자 승인 타임아웃 존재(린터 실행 → 수동 검토 폴백 관측)

## 만지는 중인 파일
- `tasks/namu-20-deploy-design/` — 상태 파일 갱신 중 (실측 ①②③ 결과 미커밋)
- `namu-plugin/mcp_config.json` — 수정 대상 확정 (소스 미수정, 주입 방안 게이트 대기 / 설치본은 절대경로로 정상화 완료)
- 임시 산출물: D:\Temp\namu-agy-ws(워크스페이스)·C:\Users\onmiso\.namu(스캐폴딩+테스트 record 1건)·repo 루트 image~5.png — 기록 완료, 정리 가능
