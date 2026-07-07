# context @ hp — namu-20-deploy-design
> 🔄 갱신 2026-07-07 22:05 [hp]

## ▶ 다음 (한 줄)
(완료) — 커밋·푸시만 남음(사용자 확인 대기). 후속 별건: 설치형 사용설명서·영어 README

## 지금 어디까지
- samsung 커밋 2건(b5a2c2d, 0247f66) pull 완료 — 커밋·푸시 단계 종료
- CC 0.1.2 실측 전부 PASS: cc-agents 로드·`namu:` 네임스페이스 확인 + `namu:namu-coder` 라이브 호출 성공(파일 물증). agy 전용 agents/ 미로드 = "agents" 필드가 자동 스캔 대체 확증
- ~/.namu 분리 모드 실측 PASS(시뮬레이션) → 완료조건 ① 충족
- agy 0.1.2 재설치 완료(uninstall→install=잔재 함정 정석 해법, "agents: 2 processed")
- agy repo 밖 3단: 스킬 PASS·훅 PASS·MCP **대화형 PASS**(사용자 라이브+스크린샷, 완료조건 ③ 충족) — 유일한 한계: **-p 비대화 모드+MCP=세션 멈춤**(경로 방식 무관, 서버는 정상). repo 안 -p 타임아웃도 동일 원인
- 새 발견: CC directory 마켓플레이스=소스 라이브 참조(pull+재시작만으로 반영). agy 전역 mcp_config.json은 install 후에도 빈 파일

## 막힘·주의 (있으면)
- ⚠️ agy -p+MCP 멈춤: 대화형 모드 동작 여부 미확인(사용자 라이브 필요). 결과에 따라 한계 목록에 확정 기재
- ⚠️ 워커 호출명 미결(이월): 설치형 CC 스킬이 `namu:namu-coder`로 불러야 함 + NAMU_HOME 분리 모드선 namu_workers.yaml 부재 — 스킬 폴백 설계 필요
- hp 로컬: 옛 `.agents/mcp_config.json`(절대경로)은 `.bak`으로 꺼진 상태, 쉘 전역 NAMU_HOME=repo export 존재

## 만지는 중인 파일
- 없음 (실측만 진행, 코드 무변경. 시뮬레이션 산출물은 scratchpad에만 존재)
