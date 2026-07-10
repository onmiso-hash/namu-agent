# context @ samsung — namu-27-session-sync
> 🔄 갱신 2026-07-10 [samsung]

## ▶ 다음 (한 줄)
⑥ 라이브 실측 판정 — 이 커밋이 pull로 보이면 behind 경고→승인 pull→재안내 사이클 성공. 결과를 오케스트레이터 세션에 보고 → record·마감

## 지금 어디까지
- 완료조건 ①~⑤ 구현·검수 PASS(코더 1회, 리뷰어 결함 0). 미커밋 상태
- 판정 규칙: log 권위 = 마지막 [시작] 이후 [완료]/[중단] 존재(namu-25 [정정] 함정 실물 커버) OR 기존 context (완료)
- 이월 안내: 활성 없음 시 최근 마감 task [완료] 줄 '이월:' 추출 → "⏭ 다음 작업 후보" 섹션
- git 체크: check_git_behind(fetch+rev-list, 3초, 실패 무음+db/git_check.log 물증, NAMU_GIT_CHECK=0 스킵), behind>0이면 브리핑 맨 앞 경고+승인 pull 지시문
- 캐시: mcp 도구 3종 진입 시 + 훅 2종 _ensure_db가 cache_is_stale 재생성
- 테스트: 신규·수정 39/39, 전체 61 pass / 6 fail(main 기저 결함 — stash 대조로 검증, test_cache_stale 4·test_mcp_selfheal 2)

## 막힘·주의 (있으면)
- 라이브 실측은 커밋 전이 안전(#26 교훈 — directory 소스라 새 세션이 워킹트리 직참조)
- 기저 실패 6건(Windows temp PermissionError·cp949 캡처)은 이 task 범위 밖 — 별건 처리 후보
- 이 세션의 MCP 서버는 구코드로 부팅된 상태 — 새 코드 검증은 반드시 새 세션에서

## 만지는 중인 파일
- namu-plugin/task_resolve.py·session_context.py·hooks/session_recall.py·hooks/session_inject.py·mcp_server.py — ①~④ 구현
- namu-plugin/plugin.json·.claude-plugin/plugin.json — 0.1.9
- namu-plugin/test_task_resolve.py·test_session_context.py·test_hook_stale_rebuild.py — 테스트
