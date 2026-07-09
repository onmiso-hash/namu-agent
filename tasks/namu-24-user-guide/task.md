# namu-24-user-guide — 설치형 마무리 + 일반 사용자용 HTML 가이드
📅 생성 2026-07-09 [samsung] · 🔗 관련: #23(install_guide.md), #22(agy_reinstall.ps1)

## 목적
비개발자도 NAMU 설치형의 개념을 이해하고 무리없이 따라 설치할 수 있게, 미완성 요소(스크립트 배포·machine 자동 감지·워커 문법·private 전제)를 마무리하고 친절한 HTML 가이드를 만든다.

## 완료조건
- [x] ① `agy_reinstall.ps1`이 플러그인 폴더 안(`namu-plugin/scripts/`)으로 이동 — 설치형 사용자도 보유 (버전 0.1.7)
- [x] ② `NAMU_MACHINE` 미설정 시 hostname 자동 폴백(config.py) + 회귀 테스트
- [x] ③ `namu_workers.yaml` 기본 문법 문서화
- [x] ④ install_guide.md 독자 전제 명확화 — private 유지, "자격증명 보유 지인" 대상
- [x] ⑤ `docs/install_guide.html` — 일반 사용자용 단일 자급자족 HTML (개념→준비→단계별→증상별 트러블슈팅)

## 범위 밖
- repo 공개 전환, 영어 README
- 워커 이종 엔진 어댑터 (`namu_workers.yaml` override 실구현)
