# namu-18-public-readme — 공개 README 작성
📅 생성 2026-07-06 [samsung] · 🔗 관련: namu-16-live-verify(statusLine cp949·터미널 실측) / namu-17-subagent-parity(플러그인 재설치·agy 실측)

## 목적
루트 README가 2026-06-23 초기 구상본에 멈춰 현재 아키텍처(MCP 메모리 플러그인, CC·agy 듀얼 엔진, 워커 층)를 반영하지 못함. 공개 배포(로드맵 2단계)의 전제로, 새 사용자(특히 비영어권 Windows)가 셋업에서 반드시 부딪힐 함정까지 문서화한 공개 README를 만든다. 언어=한국어(영어판은 공개 임박 시점에 추가).

## 완료조건
- [ ] 루트 README.md 전면 개정 — 현재 아키텍처 반영, 공개 독자 대상
- [ ] 셋업 가이드 — 필요조건·환경변수(NAMU_HOME/NAMU_MACHINE)·CC/agy 플러그인 설치 실측 절차
- [ ] 셋업 함정 명시 — ① 한글 Windows cp949→`python -X utf8`(statusLine) ② 구식 conhost 이모지 `�`→Windows Terminal ③ agy repo 밖 실행 한계 ④ 플러그인 설치본=복사본이라 갱신 시 재설치
- [ ] namu-plugin/README.md 현행화 — 실측 설치 절차(marketplace / agy plugin install) 기준
- [ ] 검수 — reviewer가 문서 내용을 plan.md 실측 기록과 대조

## 범위 밖
- 영어판 README (공개 배포 임박 시점에 별도)
- plan.md 자체 정리(헤더 복구·아카이브) — 별건
