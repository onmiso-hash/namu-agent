# OpenCode에서 NAMU 쓰기

OpenCode(터미널)에서도 NAMU 기억·작업 절차를 쓴다. Claude Code·agy·Grok용
플러그인 봉투와 같은 역할을 하는 OpenCode 전용 플러그인이 이 저장소에
들어 있다(`.opencode/plugins/namu/`). 같은 기억 서버(`mcp_server.py`)와
같은 절차 스킬을 그대로 쓰고, OpenCode가 요구하는 등록 형식(TS 플러그인)으로만
갈아입혔다 — "봉투 하나 추가, 내용물 공유" 원칙 그대로다.

## 지원 범위

- 기억: 전부. 로컬 stdio로 같은 기억 서버를 직접 띄우므로 도구 16개가
  그대로 노출된다.
- 작업 절차: `/namu`(브리핑) · `/namu-task`(오케스트레이션) ·
  `/namu-update`(업데이트) · `namu-coder`/`namu-reviewer` 워커 ·
  세션 첫 호출 브리핑+검사 묶음(저장소 뒤처짐·판 드리프트·주간 점검) ·
  매 호출 상시 주의 재알림 · 고치기 전 저장소 뒤처짐 묻기 ·
  마무리 `[다음]` 누락 권고. 전부 플러그인이 자동으로 건다.
- 호스트 한계로 못 하는 것 (Claude Code와 다른 점):
  - 마무리 검사는 **막지 않고 권고만** 한다. OpenCode에 세션 종료 훅이
    없어서, `[다음]` 줄이 없으면 프롬프트에 검사문을 덧붙여 모델이
    사용자에게 확인하게 한다.
  - 세션 측정은 안 한다. 측정기는 클로드 대화 기록 형식만 읽어서,
    OpenCode 세션은 잴 수 없다 (Grok도 같은 한계가 있다).
  - statusLine은 없다. OpenCode TUI에 하단 한 줄을 넣는 건 별도
    TUI 플러그인 작업으로 남겨 두었다.
  - `statusline-setup` 스킬은 Claude Code 전용이라 OpenCode에서 쓰지 않는다.

## 설치

전제: Python 3.12+ · [uv](https://docs.astral.sh/uv/) · git · OpenCode V2 ·
이 저장소 클론 1부.

```
git clone https://github.com/onmiso-hash/namu-agent.git
```

아래에서 `/abs/path/namu-agent`는 그 위치로 바꿔 읽는다.

1. 쓰는 프로젝트 설정에 플러그인 한 줄을 넣는다.
   프로젝트 설정(`<프로젝트>/.opencode/opencode.jsonc`) 또는
   전역 설정(`~/.config/opencode/opencode.jsonc`):

   ```jsonc
   {
     "$schema": "https://opencode.ai/config.json",
     "plugins": ["/abs/path/namu-agent/.opencode/plugins/namu"]
   }
   ```

   저장소 통째로 받는 방법도 된다:

   ```
   opencode plugin add github:onmiso-hash/namu-agent#main::path:.opencode/plugins/namu
   ```

   플러그인이 기억 서버(MCP) · 스킬 3종 · 명령 3종 · 훅을 전부 등록하므로,
   `mcp`·`skills` 항목을 손으로 쓸 필요가 없다. 버전이 있는 npm 패키지로는
   아직 배포하지 않는다.

2. 워커 2명을 프로젝트에 복사한다 (OpenCode 플러그인 API로 에이전트를
   직접 등록할 수 없어 파일로 둔다).

   ```
   mkdir -p .opencode/agents
   cp /abs/path/namu-agent/.opencode/agents/namu-coder.md .opencode/agents/
   cp /abs/path/namu-agent/.opencode/agents/namu-reviewer.md .opencode/agents/
   ```

   본문은 Claude Code용(`.claude/agents/`)과 같은 내용이고, 앞부분만
   OpenCode 형식(`description` + `mode: subagent`, 검수자는 쓰기 금지)이다.

3. 플러그인 의존성을 한 번 받는다 (배포 산출물이 아니라 빌드 확인용).

   ```
   cd /abs/path/namu-agent/.opencode/plugins/namu && npm install
   ```

4. 연결 확인.

   ```
   opencode mcp list
   ```

   `namu-memory connected`가 뜨면 된다. 첫 기동은 uv가 의존성을 준비하느라
   1~2분 걸릴 수 있다.

## 첫 작업

1. OpenCode를 열고 `/namu`를 부른다. 쪽지·열린 작업·관련 교훈이 브리핑으로 나온다.
2. 여러 단계 코딩은 `/namu-task <슬러그>`로 한다.
   recall→분할→`namu-coder` 위임→`namu-reviewer` 검수→사용자 게이트→`namu_record` 순이다.
3. 검수가 fail이면 자동으로 다시 돌리지 않는다. ① 재실행(횟수 입력) /
   ② 통과 처리 / ③ 중단 중 하나를 고른다.
4. "마무리해"라고 하면 작업일지에 `[다음]` 줄이 있는지 검사한다. 없으면
   막는 대신 모델이 확인을 구한다 — 남길 것이 없으면 없다고 답하면 된다.

## 업데이트·삭제

- 업데이트: `/namu-update`를 부르거나, 저장소에서 직접 당긴다.
  (`git -C /abs/path/namu-agent pull`). 기억(`~/.namu`)은 저장소와
  분리되어 있어 업데이트해도 쌓인 교훈이 지워지지 않는다.
- 삭제: 설정에서 `plugins` 항목을 지우고,
  복사했던 `.opencode/agents/namu-*.md`를 지운다.
  `~/.namu`는 손대지 않는 한 그대로 남는다.

## 문제 해결

- `opencode mcp list`에서 연결이 안 되면 OpenCode 로그
  (`~/.local/share/opencode/log/opencode.log`)에서 `loading plugin` 뒤에
  이 플러그인 경로가 있는지 본다. 없으면 `plugins` 항목의 경로가
  `.opencode/plugins/namu` (package.json이 있는 폴더)를 가리키는지 확인한다.
- `uv: command not found`면 uv부터 설치한다. 플러그인은 PATH에서
  `uv`를 찾고, 없으면 `~/.local/bin/uv`를 쓴다.
- 스킬이 안 보이면 플러그인이 제대로 올라왔는지 먼저 본다. 스킬 ID는
  폴더명(`namu`, `namu-task`, `namu-update`)이며 앞부분 `name`이 아니다.
- 이 저장소 자체를 OpenCode로 개발할 때는 루트의 `.opencode/`가 그대로
  쓰인다(플러그인 자동 탐색 + 상대경로). 커밋 대상이며,
  개인 설정(`settings.local.json`류)은 넣지 않는다.
- 플러그인 코드를 고쳤으면 타입 검사를 돌린다:
  `cd .opencode/plugins/namu && ./node_modules/.bin/tsc --noEmit`.
  `index.ts` 저장은 OpenCode가 감지해 자동 리로드한다.
