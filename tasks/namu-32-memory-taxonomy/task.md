# namu-32-memory-taxonomy — 메모리 3원 분류 확정 (제품지식/개인전역/프로젝트상태)
📅 생성 2026-07-11 [hp] · 🔗 관련: namu-26(저장소 이원화 확정), namu-30(설치형 sync 구현), namu-31(이월 등록)

## 목적
namu-31 이월 "기억 풀 이원화 해소". 설계 세션(07-11) 결론: 개발 repo 기억과
설치형(~/.namu) 기억은 성격이 다른 지식(제품지식 vs 개인전역지식)이라 병합하지
않고, 대신 ① 이름으로 구분을 명시하고 ② 문서로 3원 분류를 못박고 ③ 아직
꺼져있는 개인전역 풀 동기화를 실제로 켠다. 분류는 AI 판단이 아니라 실행 위치
(NAMU_HOME)로 기계적으로 결정된다 — 기존 config.py 로직 그대로, 표시 이름만 분기.

## 완료조건
- [x] ① config.py 파일명 분기 — NAMU_HOME == REPO_ROOT(개발 모드)일 때만
      learnings 파일명을 `product_learnings.yaml`로, 그 외(설치형/명시 env)는
      기존 `learnings.yaml` 유지. 기존 902줄 파일은 `git mv`로 이력 보존 이동.
      learnings.yaml 경로를 참조하는 코드·테스트 전수 점검(파일명 하드코딩 잔재 0).
- [x] ② 문서화 — CLAUDE.md "메모리 구조"에 3원 분류(제품지식=repo
      `product_learnings.yaml` / 개인전역=`~/.namu` `learnings.yaml` /
      프로젝트상태=cwd tasks) 문단 추가 + "핵심 파일" 표 갱신.
      plan.md 결정 테이블에 2026-07-11 결정 행 추가(왜 병합하지 않는지 근거 포함).
- [x] ③ ~/.namu 동기화 켜기 — 사용자가 비공개 원격 repo 준비 후
      `namu_sync_setup` 호출로 활성화. 기존 ~/.namu의 교훈(1건)이 원격에
      push되고 `.namu_sync` 마커 생성 확인.
- [x] ④ 검증 — 기존 테스트 전수 통과 + 개발 repo 세션에서 recall/record가
      `product_learnings.yaml`을 읽고 쓰는지, 설치형 경로는 `learnings.yaml`
      그대로인지 실측. stale 캐시 재생성이 새 파일명에서도 동작 확인.

## 범위 밖
- 두 풀의 내용 병합·연합 조회(federated recall) — 이번 설계에서 "안 한다"로 결정
- task 저장 위치 중앙화 opt-in — 별도 논점으로 유지(이월 목록 잔류)
- 소비자 문서 4종(가이드) 갱신 — 설치형 동작은 변화 없어 원칙상 불필요,
  구현 후 재확인
