# context @ hp — namu-33-home-routing
> 🔄 갱신 2026-07-11 17:46 [hp]

## ▶ 다음 (한 줄)
(완료)

## 지금 어디까지
- 코더 1회 완료: config.py 폴백 ② cwd 조건(`_cwd_is_within`, resolve+is_relative_to) 추가, 신규 테스트 2건(가짜 repo 픽스처/HOME 격리), plugin.json 2곳 0.1.13 범프. 83/83 green
- 리뷰어 1회 PASS: 코드 실물 대조, 83/83 재실행, 라이브 실측 3종(repo 밖 env 제거→~/.namu·learnings.yaml / repo 안→product_learnings.yaml(우선순위 ① .env 경유) / 임시 HOME record 왕복 실물 생성) 전부 정상
- 오케스트레이터: ~/.bashrc NAMU_HOME export 제거(NAMU_MACHINE=hp 유지), fresh shell 시뮬레이션(env -u + bash -ic)으로 실측 확인
- 완료조건 5개 전부 충족, record 01KX85NWRZ8ZVHQ35CH11XGVDF 저장(제품지식 풀 착지 확인) — task 마감

## 막힘·주의 (있으면)
- 이 세션 MCP 서버는 옛 env(NAMU_HOME=개발 repo)로 떠 있으나, 이번 record 대상이 제품지식 풀이라 목적지가 일치 — MCP record 사용 가능
- 커밋은 미수행 (워킹트리 변경 상태)

## 만지는 중인 파일
- `namu-plugin/config.py` — 폴백 ② cwd 조건 (완료)
- `namu-plugin/test_config_home_routing.py` — 신규 회귀 테스트 (완료)
- `namu-plugin/plugin.json`, `namu-plugin/.claude-plugin/plugin.json` — 0.1.13 (완료)
- `~/.bashrc` — NAMU_HOME export 제거 (완료, git 밖)
