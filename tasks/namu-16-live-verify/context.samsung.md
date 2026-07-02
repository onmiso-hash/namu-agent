## ▶ 다음
⑥ 커밋(사용자) → ⑦ 네이티브 서브에이전트 대칭 + HP 대칭 설치(HP 세션에서 `agy plugin install` + 옛 `.agents/hooks.json`·`mcp_config.json` 직접 등록 청소) + 공개 README.

## 현재 상태
- ⑥ agy 플러그인 승격 **라이브 검증 통과** (2026-07-02 삼성): `/mcp`에 namu-memory ✓ 3 tools + PreInvocation 자동주입(🌳+📌) 확인 — 삼성 agy 최초의 MCP·자동주입.
- 확정된 agy 플러그인 형식: 루트 plugin.json / mcp_config.json(경로=**agy 실행 폴더 기준**, 워크스페이스-상대 `namu-plugin/...` 사용 — `${extensionPath}` 미치환 버그 우회) / hooks.json(네임스페이스 래핑 `{"namu":{"PreInvocation":[...]}}`, 경로=**플러그인 설치 폴더 기준** `hooks/...`).
- session_inject.py 보강 3건: typing-extensions 의존성 추가(python-ulid 3.1.0 패키징 버그) / stdout UTF-8 강제(cp949) / workspacePaths chdir(훅 cwd=플러그인 폴더 대응).
- 한계(문서화 필요): agy를 namu-agent 폴더 밖에서 켜면 MCP 스폰 실패(✗, 비치명) — agy가 `${extensionPath}`를 고치면 해소 가능.
- 커밋 대기 중 (namu-plugin 신규 3파일 + session_inject.py + tasks 상태 2파일).
