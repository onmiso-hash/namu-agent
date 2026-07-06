# context @ samsung — namu-20-deploy-design
> 🔄 갱신 2026-07-06 15:40 [samsung]

## ▶ 다음 (한 줄)
커밋·푸시 → CC 플러그인 0.1.2 업데이트+재시작 실측(cc-agents 로드·namu: 네임스페이스·~/.namu 분리) → agy repo 밖 워크스페이스 실측 → 워커 호출명 설계 → plan.md 기록+설계 문서

## 지금 어디까지
- 설계 게이트: ① 메모리=~/.namu 폴백+override ② 워커=플러그인 동봉 ③ agy 한계=실측 — 전부 사용자 승인
- 구현 완료(검수 PASS, 미커밋): config.py 3분기 폴백, plugin.json 2곳 0.1.2+"agents" 필드, agents/(agy 하위폴더)·cc-agents/(CC 플랫) 분리 동봉
- agy 실측 확정: 봉투 agents 인식(하위폴더 레이아웃), cc-agents/·plugin.json 필드 무시, 설치본 정리 완료("agents: 2 processed")
- CC 문서 확정: "agents" 필드=자동 스캔 대체, 동봉 에이전트 이름=`namu:namu-coder`(네임스페이스), 우선순위 최하

## 막힘·주의 (있으면)
- ⚠️ 새 함정: agy plugin install=비파괴 병합, 소스에서 지운 파일이 설치본에 잔존 → 수동 청소 필요 (이번에 실제 발생·해결)
- ⚠️ 워커 호출명 미결: 설치형 CC에서 스킬이 `namu:namu-coder`로 불러야 함 + NAMU_HOME 분리 모드선 namu_workers.yaml 부재 — 스킬 폴백 설계 필요
- CC 쪽 cc-agents 로드·네임스페이스는 문서 근거만 확보, 라이브 미실측(재시작 필요)

## 만지는 중인 파일
- `namu-plugin/config.py`·`plugin.json`·`.claude-plugin/plugin.json` — 수정 완료, 미커밋
- `namu-plugin/agents/`·`cc-agents/` — 신규, 미커밋
