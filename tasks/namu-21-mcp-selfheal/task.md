# namu-21-mcp-selfheal — agy 설치본 mcp_config 절대경로 훅 self-healing
📅 생성 2026-07-07 [samsung] · 🔗 관련: namu-20-deploy-design (함정 목록 #3), namu-16-live-verify

## 목적
agy 재설치(uninstall→install)마다 설치본 mcp_config.json이 상대경로로 초기화되어 repo 밖에서 MCP가 조용히 죽는 문제를, 플러그인 훅이 세션 시작 시 자기 기기 절대경로로 자동 교정(self-healing)하게 해 수동 재주입 작업을 없앤다. (A안, 사용자 게이트 2026-07-07 통과 — B안 설치 스크립트 대비 agy install에 후처리 훅이 없어 세션 훅이 유일한 자동 개입 지점)

## 완료조건
- [ ] 훅이 설치본 mcp_config.json의 상대경로를 감지해 그 기기의 절대경로로 자동 교정 (이미 절대경로면 무변경 = 멱등)
- [ ] samsung 라이브 실측: agy 재설치 직후 세션에서 자동 교정 발동 → 이후 세션 MCP 정상 로드
- [ ] CC 쪽 무영향 확인 (CC .mcp.json의 ${CLAUDE_PLUGIN_ROOT} 방식 그대로)
- [ ] deploy_design.md 함정 목록 #3에 해소 방법 기록

## 범위 밖
- agy `-p` 모드 + MCP 멈춤 (agy 자체 결함, 우리가 못 고침)
- NAMU_MACHINE 온보딩 (별건)
