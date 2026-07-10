# namu-29-hook-deps — CC 브리핑 훅 의존성 자급 (개발 repo 밖 무음 사멸 수정)
📅 생성 2026-07-10 [hp] · 🔗 관련: namu-25-usage-guide, namu-27-session-sync, namu-28-guide-refresh

## 목적
CC SessionStart 훅(hooks/session_recall.py)에 PEP 723 의존성 블록이 없어,
`uv run --script`가 개발 repo 밖 cwd에서 맨몸 환경으로 실행된다 → config.py의
dotenv import에서 ModuleNotFoundError → 광범위 except가 무음 삼킴(exit 0) →
설치형 사용자에게 세션 브리핑·환영 안내·git behind 경고·훅발 캐시 재생성이
전부 미동작. onnamu-project 라이브 스크린샷(브리핑 0개) + 헤드리스 재현
(traceback 물증)으로 실증(2026-07-10 hp). 개발 repo에서만 통과했던 이유는
repo의 .venv가 의존성을 조용히 메워 버그를 가렸기 때문. 근본 수정한다.

## 완료조건
- [x] ① session_recall.py에 PEP 723 블록 추가 — session_inject.py(동종 agy 훅,
      같은 모듈 트리 import)와 동일한 의존성 세트
- [x] ② 재현 케이스 역전 — 개발 repo 밖 cwd(임시 폴더)에서
      `echo '{"cwd":"<임시폴더>"}' | uv run --script .../session_recall.py`
      실행 시 hookSpecificOutput JSON이 출력된다 (수정 전: 무출력 실증됨)
- [x] ③ 회귀 없음 — 개발 repo cwd에서 기존과 동일하게 브리핑 JSON 출력
- [x] ④ uv 호출 스크립트 전수 점검 결과 반영 — 누락은 session_recall.py 단 1건
      (사전 조사 완료: session_inject.py는 블록 보유). 다른 파일 수정 불필요 확인
- [x] ⑤ plugin.json 버전 0.1.9 → 0.1.10
- [x] ⑥ 기존 테스트 회귀 없음 (기저 fail 6건 제외 기준)
- [x] ⑦ 라이브 실측 — onnamu-project 새 CC 세션에서 "🌳 브리핑 블록 몇 개?"
      질문에 1개 응답 (사용자 협조 필요, 이중 주입 여부도 이 질문으로 동시 확정)

## 범위 밖
- statusLine (별도 채널, onnamu에서 정상 동작 실증됨)
- 기저 테스트 실패 6건 (별도 이월 후보)
- 설치 가이드 스코프 설명 보강 (namu-30 후보로 이월)
