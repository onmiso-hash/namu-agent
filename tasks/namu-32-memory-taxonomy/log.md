# log — namu-32-memory-taxonomy
(append만. context 꼬이면 이걸로 복원)

[시작] 2026-07-11 16:46:18 hp · 작업 생성, 목적·완료조건 확정 (namu-31 이월 — 기억 풀 이원화 해소 설계 세션 결론 구현: 병합 대신 3원 분류. ③ sync 켜기는 사용자 원격 repo 준비 후 유예)
[분담] 2026-07-11 16:48:35 hp · 코더 위임(사용자 게이트 승인) — ①config 분기+git mv ②문서화 ④테스트, 함정 3종(memory_sync 불변·개발repo gitattributes union 추가·소비자문서 불변) 지시서 명세
[분담] 2026-07-11 16:58:19 hp · 코더 1회 완료(81 테스트, agy plugin.json 0.1.9 드리프트 발견·해소 보고) → 리뷰어 검수 PASS(7기준: 분기 정확·rename 무결 45건·함정 3종 준수·81/81·실측 dev=product_/tmp=learnings·문서대조·드리프트 git log 확증)
[기록] 2026-07-11 17:01:56 hp · ①②④ 마감 — 커밋 ba8e658 + record 01KX834P51X7NQXNTA7JJ3AF9Y(fresh subprocess로 저장, 세션 내 MCP 서버는 옛 경로라 미사용, verified_by human). task 열어둠 — 남은 것 ③ ~/.namu sync 켜기(사용자 원격 repo 준비 대기)
[완료] 2026-07-11 17:24:05 hp · #32 종료 — 완료조건 ①~④ 전부 충족. ③은 onnamu-project 세션에서 실행(개발 repo 하드가드로 이 폴더 불가 → NAMU_HOME=~/.namu 서브프로세스 우회, 사용자 선택=setup만·bashrc 유지), 본 세션 실물 검증: 마커·origin 추적·3bcb637=원격 HEAD·union merge·교훈 1건 push 전부 확인. record 01KX834P51X7NQXNTA7JJ3AF9Y(기저장). 이월: hp(개발 머신)의 타 프로젝트 세션 기록이 bashrc 전역 NAMU_HOME 때문에 개인 풀 아닌 제품지식 풀로 들어가는 라우팅 갭 — 3원 분류 원칙과 어긋남, bashrc 정리+폴백 규칙 재검토 필요. 커밋·푸시 진행
