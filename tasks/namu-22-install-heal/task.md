# namu-22-install-heal — agy 재설치 시 설치 시점 즉시 mcp_config 교정
📅 생성 2026-07-08 [hp] · 🔗 관련: namu-21-mcp-selfheal

## 목적
#21 훅 self-healing은 첫 일반 메시지에야 발동 → 재설치 직후 /mcp만 치는
사용자는 에러만 보고 "설치 실패"로 오인. 설치 시점에 즉시 교정해
첫 세션부터 MCP가 정상 로드되게 한다. (훅은 안전망으로 유지)

## 완료조건
- [ ] ① `--heal` 단독 진입점 (session_inject.py의 heal_mcp_config를 CLI로 직접 호출)
- [ ] ② `scripts/agy_reinstall.ps1` — uninstall → install → heal 일괄 실행
- [ ] ③ 라이브 실측: 스크립트 실행 후 첫 세션에서 메시지 없이 /mcp 정상
- [ ] ④ deploy_design.md에 "첫 세션 함정" 명시 + 새 절차 반영
- [ ] 플러그인 0.1.5 범프

## 범위 밖
- bash판 재설치 스크립트
- agy 훅 이벤트(설치 시점 훅 존재 여부) 조사
