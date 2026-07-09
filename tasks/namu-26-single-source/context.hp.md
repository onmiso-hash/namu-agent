# context @ hp — namu-26-single-source
> 🔄 갱신 2026-07-09 22:10 [hp]

## ▶ 다음 (한 줄)
(완료)

## 지금 어디까지
- 2차 재작업 검수 PASS(리뷰어 실증): 이원화 확정 — 교훈·db=~/.namu 중앙, tasks=프로젝트 cwd 로컬
- 완료조건 ①~⑥ 전부 충족. 43 테스트 통과. NAMU_HOME=/tmp 실증(tasks 중앙으로 안 샘), TASKS_DIR 참조 0건, 메모리 상수 5개 불변
- 코드 변경 요체: config.TASKS_DIR 상수 → tasks_dir_for(project_dir) 헬퍼 / task_resolve.resolve_active_task=ws 기준(NAMU_HOME 무시) / session_recall.py 훅이 stdin JSON cwd 읽어 project_dir 주입(폴백 os.getcwd) / session_context·session_inject·orchestrator·namu_active_task 호출부 전수 통일

## 막힘·주의 (있으면)
- **라이브 미확인**: 리뷰어 실증은 CC 훅 stdin 스키마 '재현'이지 실제 raw stdin 캡처 아님(리뷰어 명시). namu-23 교훈(리눅스 검증이 실환경 결함 못 잡음)상 실제 새 CC 세션 브리핑 확인 필요. directory 소스라 커밋 없이도 새 세션이 소스 직참조 → 라이브 가능
- 커밋 전 라이브가 안전(문제 시 추가 커밋 회피)

## 만지는 중인 파일 (검수 PASS, 커밋 대기)
- config.py, task_resolve.py, session_context.py, hooks/session_recall.py, hooks/session_inject.py, core/orchestrator.py, scripts/namu_active_task.py, scripts/namu_statusline.py, namu-plugin/scripts/namu_statusline.py, skills/namu-task/SKILL.md, docs/usage_guide.md, plugin.json 2곳, 테스트 4파일
