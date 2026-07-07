# context @ hp — namu-22-install-heal
> 🔄 갱신 2026-07-08 08:16 [hp]

## ▶ 다음 (한 줄)
③ 라이브 실측 (사용자, Windows PowerShell): `scripts\agy_reinstall.ps1` 실행 → agy 새 세션에서 **메시지 입력 없이** `/mcp` → namu-memory 3도구 정상 확인

## 지금 어디까지
- ①②④⑤ 구현+검수(reviewer) PASS — 테스트 19 passed, ps1은 PowerShell 파서 검증 OK
- ① --heal 진입점: session_inject.py main() 초입(stdin 전) 분기, stdlib만 사용, 훅 모드·heal_mcp_config 본체 무변경
- ② scripts/agy_reinstall.ps1: uninstall(실패 무시)→install(실패 시 중단)→설치본 --heal(python→py -3 폴백), PS 5.1 호환
- ④ deploy_design.md 함정 #3에 첫 세션 함정+해소(0.1.5), 절차 표 갱신 ⑤ 0.1.5 범프 2곳
- 커밋·푸시·record는 ③ 실측 후

## 막힘·주의 (있으면)
- ③은 Windows 쪽 agy 필요 — hp의 Windows 호스트 또는 samsung에서 실측 (ps1 자체는 WSL 실측 불가)
- 실측 성공 기준: 스크립트 출력에 heal 교정 문구 + 첫 세션 /mcp에서 namu-memory 로드(이전엔 세션 2회 필요했던 것이 1회로)

## 만지는 중인 파일
- `namu-plugin/hooks/session_inject.py` — --heal 분기 (구현 완료)
- `namu-plugin/test_mcp_selfheal.py` — 신규 3건 (구현 완료)
- `scripts/agy_reinstall.ps1` — 신규 (구현 완료)
- `docs/deploy_design.md`, `namu-plugin/plugin.json`, `namu-plugin/.claude-plugin/plugin.json`
