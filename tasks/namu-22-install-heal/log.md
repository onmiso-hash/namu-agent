# log — namu-22-install-heal
(append만. context 꼬이면 이걸로 복원)

[시작] 2026-07-08 08:06:30 hp · 작업 생성, 목적·완료조건 확정 — 사용자 확인 통과. 소재=#21 마감 직후 발견된 UX 구멍(PreInvocation 훅은 첫 일반 메시지에야 발동 → 재설치 직후 /mcp만 치면 "설치 실패" 오인). 합의안=①--heal 진입점 ②scripts/agy_reinstall.ps1 ③라이브 실측(스크립트 후 첫 세션 /mcp 정상) ④deploy_design.md 첫 세션 함정 명시, 0.1.5. 범위 밖=bash판·agy 훅 이벤트 조사
[결정] 2026-07-08 08:16:45 hp · 구현(coder)+검수(reviewer) PASS — ① session_inject.py --heal 분기(main 초입 stdin 전, stdlib만, 훅 모드·heal_mcp_config 본체 무변경 git diff 확인) ② scripts/agy_reinstall.ps1(uninstall 실패무시→install 실패중단→설치본 --heal, python→py -3 폴백, PS 5.1 호환+PowerShell 파서 PARSE OK) ④ deploy_design.md 함정 #3 첫 세션 함정+해소(0.1.5)·절차 표 갱신 ⑤ 0.1.5 범프 2곳. 테스트 19 passed(기존 16+신규 3, 0.2초). --heal repo 실측=가드 무변경 정상. 남은 것=③ 사용자 라이브 실측(Windows: ps1 실행→첫 세션 메시지 없이 /mcp 정상)
[완료] 2026-07-08 08:25:45 hp · #22 종료 — 완료조건 전부 충족: ①②④⑤ 구현+검수 PASS(hp, 테스트 19 passed, 0.1.5) + ③ 라이브 실측 PASS(samsung, Windows): agy_reinstall.ps1 실행 → 설치 시점 --heal 선교정 → 첫 세션 메시지 없이 /mcp 정상(namu-memory 로드, 사용자 라이브). record 1건(01KWZE7ECJ5K1W61VGV0B1YBFJ, samsung, human). #21 훅은 안전망으로 유지, 첫 세션 함정 해소
