# namu-26-single-source — 메모리/작업상태 저장소 이원화 + 온보딩/statusline 동봉
📅 생성 2026-07-09 [hp] · 🔗 관련: #25(실측 채록), #24(hostname 폴백·agy_reinstall 동봉 전례)

## 목적
namu-25 실측에서 드러난 "설치형 첫 하루의 구멍"을 코드/문서로 메운다. 근본 원인은 시스템 불변식이 config.py와 SKILL.md·보조 스크립트에서 제각기 서술돼 조용히 어긋난 것. **제품 비전(로컬 중앙 메모리 + 향후 git 크로스-PC 공유)에 맞춰 저장소를 이원화**한다: 교훈·db는 `~/.namu` 중앙(글로벌 공유 대상), **작업 상태(tasks)는 프로젝트 종속 데이터이므로 그 프로젝트 폴더(cwd)에** 둔다(그 프로젝트 git으로 공유). 이렇게 하면 statusLine·브리핑의 "진행 중 task" 탐지가 프로젝트 경계 안에서 정확해지고, git 동기화 스코프가 데이터 성격과 일치한다.

## 완료조건
- [x] ① SKILL.md machine 문구 정합 — config 실동작(`NAMU_MACHINE` env → hostname 소문자 폴백, unknown은 hostname도 빌 때만)에 맞춤. `.env` 부재만으로 unknown 찍지 말 것 명시. **(코더 1차 완료)**
- [ ] ② 저장소 이원화 — 메모리 루트(교훈·db = `NAMU_HOME`, 설치형은 `~/.namu`)와 **tasks 루트(프로젝트 cwd 기준)를 config.py에서 분리**. SKILL.md 작업 루트 문구도 "tasks는 현재 프로젝트 폴더 기준, 메모리(`~/.namu`)와 별개"로 정합. (1차에서 tasks를 `~/.namu`로 몰던 방향을 cwd로 전환)
- [ ] ③ tasks 탐지 통일 — statusLine(`task_resolve.resolve_active_task`)과 브리핑(`session_recall.py` 훅 + `session_context.find_active_task`)이 **동일한 프로젝트 cwd/tasks**를 가리키게 한다. 현 불일치 해소: `resolve_active_task`의 `NAMU_HOME or ws` → 프로젝트(ws) 기준으로, 훅은 stdin JSON의 cwd(폴백 `os.getcwd()`)를 읽어 탐지에 사용.
- [x] ④ 신규 환경 환영 브리핑 — 진행 task·교훈 0건일 때 `None` 대신 "설치 정상·/mcp로 확인" 안내 md 반환 + 회귀 테스트. **(코더 1차 완료)**
- [x] ⑤ statusline 플러그인 동봉 — `namu-plugin/scripts/namu_statusline.py` 동봉(import 경로 수정) + `usage_guide.md` 5절 안내. plugin.json 자동등록 미지원 조사 반영. **(코더 1차 완료)**
- [ ] ⑥ 0.1.8 범프(2곳) + `usage_guide.md` 2·4절을 이원화(tasks=프로젝트 로컬)에 맞게 정정 + 기존/신규 테스트 통과.

## 범위 밖
- agy 라이브 재설치 실측·소비자 환경 재실측 (별건, 사용자 협조 필요)
- 글로벌 `~/.claude/settings.json`(git 밖) 자동 수정 — 개발 기기 statusLine 경로는 수동 안내만
- 교훈·db를 프로젝트 로컬로 옮기는 것 — 메모리는 계속 `~/.namu` 중앙(글로벌 공유 대상), 이번에 바꾸는 건 tasks뿐
- `~/.namu` git 자동 동기화 구현 (로드맵 후속)
