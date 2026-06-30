---
name: namu
description: NAMU 세션 브리핑. 사용자가 /namu를 부를 때만 사용한다. 진행 중 task의 진행이력·다음 할 일·최근 교훈을 정해진 형식으로 보여준다.
---
NAMU "세션 브리핑"을 출력한다. 아래 순서대로 수행하고 마지막에 정해진 형식으로만 보여줘라. 파일을 수정·생성하지 말 것(읽기 전용).

1. 활성 task 선정 (task 중심):
   - 다음 Bash 명령을 실행하여 활성 task의 slug를 얻어라. (스크립트 경로는 작업 루트 기준)
     ```bash
     python scripts/namu_active_task.py
     ```
   - 출력된 slug가 없으면 "진행 중 task 없음"으로 간주한다.
2. 선정된 task 폴더에서:
   - `task.md` → 제목/목적 1줄.
   - `log.md` → 마지막 3~5줄.
   - 각 `context.<machine>.md` → `## ▶ 다음` 본문(머신 라벨 붙여 나열, `(완료)` 생략).
3. `namu_recall`을 `limit=5`로 호출해 최근 교훈을 받는다.
4. 아래 형식으로만 출력(이 외 잡담 금지):

   🌳 NAMU 세션 브리핑
   📌 진행 중: <slug> · <제목>
   🕘 최근 이력 (log.md):
      <마지막 3~5줄>
   ▶ 다음:
      · (<machine>) <그 머신 context의 ▶ 다음 본문>
   💡 최근 교훈:
      - <[outcome] task — reason>
   상세가 필요하면 "recall로 상세 보여줘"라고 하세요.
