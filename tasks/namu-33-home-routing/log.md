# log — namu-33-home-routing
(append만. context 꼬이면 이걸로 복원)

[시작] 2026-07-11 17:33:31 hp · 작업 생성 (namu-32 이월). 사전 조사로 갭 두 겹 확인: ① bashrc 전역 NAMU_HOME export ② config.py 폴백 2번이 cwd 아닌 플러그인 위치(REPO_ROOT) 기준 — directory 소스 설치라 bashrc 제거만으론 안 닫힘
[결정] 2026-07-11 17:33:31 hp · 폴백 2번을 "cwd가 REPO_ROOT 안쪽일 때만"으로 좁히기(사용자 선택). 기존 오염 기록 감사·이관은 범위 밖(사용자 선택). NAMU_MACHINE은 bashrc에 유지
[분담] 2026-07-11 17:40:00 hp · 코더 1회(config.py 폴백 ② cwd 조건 + 테스트 2건 + 0.1.13 범프, 83/83) → 리뷰어 1회 PASS(라이브 실측 3종: repo 밖→~/.namu, repo 안→product_, 임시 HOME record 왕복). 재실행 0
[결정] 2026-07-11 17:45:00 hp · bashrc 정리는 오케스트레이터 직접 수행(사용자 홈 파일이라 워커 미경유) — NAMU_HOME export 제거, NAMU_MACHINE=hp 유지, fresh shell 실측(env -u + bash -ic)으로 NAMU_HOME 빈 값 확인
[완료] 2026-07-11 17:46:22 hp · 완료조건 5/5 충족, record 01KX85NWRZ8ZVHQ35CH11XGVDF 저장(verified_by: human, 제품지식 풀 착지 확인). 커밋은 미수행 — 사용자 요청 시 별도
