# context @ hp — namu-17-subagent-parity
> 🔄 갱신 2026-07-05 23:45 [hp]

## ▶ 다음 (한 줄)
(완료) HP 대칭 셋업 전부 끝 2026-07-05: ① git pull(기완료) ② `agy plugin install ./namu-plugin` 성공(skills·mcpServers·hooks 각 1, 설치본 invoke_subagent 분기 grep 확인, "agents: skipped" 정상) ③ CC 플러그인 0.1.0→0.1.1(--scope local) + 재시작 후 `claude plugin list`로 0.1.1 enabled 확인 ④ agy settings.json allow에 "command(python)" 추가. HP 이월분 없음 — task 완전 종료

## 지금 어디까지
- 본체는 삼성에서 종료(2026-07-05, log [완료] 참조) — 워커 층 대칭 완성, 이 파일은 HP 로컬 셋업 이월분만 담음
- 워커 정의(.agents/agents/namu-{coder,reviewer}/)는 워크스페이스 파일이라 **pull만으로 agy가 자동 로드** — 별도 설치 불필요, 핫 리로드됨
- 재설치가 필요한 건 **플러그인 설치본(복사본)뿐**: agy 스킬 분기 + CC 0.1.1

## 막힘·주의 (있으면)
- HP agy 설치처는 `~/.gemini/config/plugins/namu/` (#16 기록) — install 후 `grep invoke_subagent` 해보면 분기 반영 확인 가능
- CC 플러그인 스코프는 local(~/project/namu-agent) — update 시 `--scope local` 필요할 수 있음(삼성 실측)

## 만지는 중인 파일
- 없음 (셋업 절차뿐)
