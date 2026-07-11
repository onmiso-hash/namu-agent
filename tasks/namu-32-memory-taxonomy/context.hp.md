# context @ hp — namu-32-memory-taxonomy
> 🔄 갱신 2026-07-11 17:00 [hp]

## ▶ 다음 (한 줄)
사용자 게이트: 커밋·푸시 승인 + record 방법 확인 → 이후 ③(sync 켜기)은 원격 repo 준비 대기

## 지금 어디까지
- 완료조건 ①②④ 구현·검수 PASS: config 분기, git mv(45건 무결), .gitattributes union,
  CLAUDE.md/plan.md 문서화, 신규 테스트 2건 포함 81/81, 버전 0.1.12(agy 쪽 0.1.9 드리프트 겸 해소).
- ③(~/.namu sync 켜기)은 사용자 원격 repo 준비 후 — task 열어둠.

## 막힘·주의 (있으면)
- ⚠️ 이 세션의 MCP 서버는 rename 이전에 부팅됨 — namu_record를 지금 부르면 옛 경로
  (memory/learnings.yaml)를 되살려 쓴다. record는 fresh subprocess(db.py 직접) 또는
  세션 재시작 후에 할 것.

## 만지는 중인 파일
- (staged) config.py·product_learnings.yaml·.gitattributes·CLAUDE.md·plan.md·plugin.json 2종·신규 테스트
