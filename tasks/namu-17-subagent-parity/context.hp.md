# context @ hp — namu-17-subagent-parity
> 🔄 갱신 2026-07-05 23:35 [samsung이 HP 몫으로 작성]

## ▶ 다음 (한 줄)
HP 대칭 셋업 4步: ① git pull(이미 했으면 skip) ② `agy plugin install ./namu-plugin`(스킬 분기 0.1.1 반영, skills·mcpServers·hooks 각 1 확인) ③ CC `claude plugin update namu@namu-marketplace --scope local` 후 재시작 ④ (선택) `~/.gemini/antigravity-cli/settings.json` permissions.allow에 `"command(python)"` 추가(서브에이전트 run_command 승인 큐 60초 타임아웃 처방, 삼성 기적용) → 끝나면 이 파일 "▶ 다음"을 (완료)로

## 지금 어디까지
- 본체는 삼성에서 종료(2026-07-05, log [완료] 참조) — 워커 층 대칭 완성, 이 파일은 HP 로컬 셋업 이월분만 담음
- 워커 정의(.agents/agents/namu-{coder,reviewer}/)는 워크스페이스 파일이라 **pull만으로 agy가 자동 로드** — 별도 설치 불필요, 핫 리로드됨
- 재설치가 필요한 건 **플러그인 설치본(복사본)뿐**: agy 스킬 분기 + CC 0.1.1

## 막힘·주의 (있으면)
- HP agy 설치처는 `~/.gemini/config/plugins/namu/` (#16 기록) — install 후 `grep invoke_subagent` 해보면 분기 반영 확인 가능
- CC 플러그인 스코프는 local(~/project/namu-agent) — update 시 `--scope local` 필요할 수 있음(삼성 실측)

## 만지는 중인 파일
- 없음 (셋업 절차뿐)
