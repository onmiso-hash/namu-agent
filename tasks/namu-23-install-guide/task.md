# namu-23-install-guide — 플러그인 설치형 배포 사용설명서
📅 생성 2026-07-08 [samsung] · 🔗 관련: namu-20-deploy-design, namu-18-public-readme

## 목적
#18 README는 clone 기반(repo=NAMU_HOME) 현재형까지만 다룬다. #20에서
설치형 3요소(메모리 위치·워커 배포·agy 한계)가 설계·실측으로 확정됐으므로,
임의 프로젝트에서 플러그인으로 설치해 쓰는 사용자용 설명서를 쓴다.

## 완료조건
- [ ] ① `docs/install_guide.md` 신설 — CC/agy 설치 절차, 메모리 위치(~/.namu, NAMU_HOME/NAMU_MACHINE env), 업데이트 절차(directory vs 원격 구분), 함정 목록(deploy_design.md 5종의 사용자 버전), `-p` 비대화 한계 명기
- [ ] ② 실측: repo 밖 프로젝트에서 GitHub 원격 marketplace 설치 검증 (#18에서 미검증으로 남긴 경로 — /mcp 3도구 + 세션 자동주입 확인)
- [ ] ③ 루트 README.md에 설치형 안내 링크 한 줄 연결

## 범위 밖
- 영어판 README (공개 임박 시 별건 — 로드맵 기존 분류 유지)
- 이종 엔진 워커 어댑터
