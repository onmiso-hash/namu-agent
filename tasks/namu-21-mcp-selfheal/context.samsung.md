# context @ samsung — namu-21-mcp-selfheal
> 🔄 갱신 2026-07-07 23:17 [samsung]

## ▶ 다음 (한 줄)
(완료)

## 지금 어디까지
- #21 자체는 완료·커밋·푸시 끝 (e907179까지)
- 후속 이월이던 namu-22-install-heal은 착수·완료됨(2026-07-08) — 이월 상세는 log 23:17 줄
- (2026-07-08 정정) ▶ 다음에 "(완료) — 후속 이월..." 뒷말이 붙어 완료 판정(정확 일치)에 안 걸려 statusLine에 유령 노출 → 규약대로 (완료) 단독으로 정정
- 단, 마감 후 UX 구멍 확인: 재설치 직후 세션서 /mcp만 치면 훅 미발동 → "설치 실패" 오인. 해법 방향 확정(--heal 진입점 + scripts/agy_reinstall.ps1 + 문서), 구현은 namu-22로
- namu-22 완료조건 합의안: ① --heal 단독 진입점 ② 재설치 스크립트(uninstall→install→heal) ③ 라이브 실측=스크립트 후 첫 세션 메시지 없이 /mcp 정상 ④ deploy_design.md 첫 세션 함정 명시. 0.1.5. 범위 밖=bash판·agy 훅 이벤트 조사

## 막힘·주의 (있으면)
- namu-22 task.md는 미생성 — 착수 세션에서 위 합의안으로 생성 후 사용자 확인부터
- hp 반영: pull 후 scripts 생기기 전까지는 uninstall→install→세션1(메시지 1회)→세션2 절차 유지

## 만지는 중인 파일
- (없음 — 상태 파일만 갱신)
