# namu-33-home-routing — NAMU_HOME 라우팅 갭 해소 (bashrc 전역 export + config 폴백 규칙)
📅 생성 2026-07-11 [hp] · 🔗 관련: namu-32(이월 출처, 메모리 3원 분류), namu-30(sync 하드가드)

## 목적
hp(개발 머신)에서 타 프로젝트 세션의 교훈이 개인전역지식 풀(`~/.namu/memory/learnings.yaml`)이
아니라 제품지식 풀(개발 repo `product_learnings.yaml`)로 들어가는 라우팅 갭을 닫아
3원 분류 원칙("분류는 실행 위치로 기계 결정")을 복원한다. 갭은 두 겹:
① `~/.bashrc`의 전역 `export NAMU_HOME=<개발 repo>` (env 최우선이라 모든 세션 오염),
② `config.py` 폴백 2번 — `REPO_ROOT/memory` 실재만 보고 REPO_ROOT로 폴백하는데,
REPO_ROOT는 cwd가 아닌 플러그인 파일 위치라서 directory 소스 설치(hp)에선 bashrc를
지워도 전 프로젝트가 개발 repo로 라우팅된다.

## 완료조건
- [ ] config.py 폴백 2번을 "cwd가 REPO_ROOT 안쪽일 때만 REPO_ROOT"로 좁힘 (주석의 의도 서술도 갱신)
- [ ] 신규 회귀 테스트: (a) cwd가 repo 안 + env 없음 → REPO_ROOT, (b) cwd가 repo 밖 + env 없음 + REPO_ROOT/memory 실재 → ~/.namu — 두 방향 모두, 기존 테스트 전체 green
- [ ] `~/.bashrc`의 `export NAMU_HOME=...` 줄 제거 (`NAMU_MACHINE=hp`는 유지)
- [ ] 라이브 실측: 개발 repo 밖 임시 폴더 cwd + env 미설정에서 record가 `~/.namu/memory/learnings.yaml`로, 개발 repo 안 cwd에서 `product_learnings.yaml`로 가는지 실물 판정 (fresh subprocess — namu-32 세션 수명 함정 주의)
- [ ] 플러그인 버전 0.1.13 범프 — plugin.json 2곳(CC·agy) grep 전수 확인

## 범위 밖
- product_learnings.yaml에 이미 들어간 타 프로젝트 기록의 감사·이관 (별도 task)
- 소비자 가이드 문서 갱신 (필요 시 별도 이월)
- session_context.py·namu_statusline.py의 진단 로그 경로(raw env NAMU_HOME 참조, 없으면 project_dir/db) — 소비자 환경은 원래 env 미설정이라 이번 변경으로 인한 회귀가 아님. 관찰만 기록.
