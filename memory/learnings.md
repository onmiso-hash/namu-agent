# NAMU Shared Learnings

> 모든 에이전트가 공유하는 학습 기억. append-only — 삭제 금지.

---

## 성공 패턴 (Success Patterns)

<!-- 형식: ## [날짜] [작업유형] 제목
판단 이유와 함께 기록 -->

---

### [2026-06-23] claude-subscription 성공

**작업:** 파이썬으로 피보나치 수열 10번째까지 출력하는 코드 짜줘. 코드만.

**결과:** ```python
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        print(a)
        a, b = b, a + b

fibonacci(10)
```

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

### [2026-06-23] claude-subscription 성공

**작업:** "승인 완료" 라고만 대답해줘

**결과:** 승인 완료

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

### [2026-06-24] claude-subscription 성공

**작업:** 지구에서 달까지 거리는? 한 문장으로만.

**결과:** 지구에서 달까지의 평균 거리는 약 **384,400km**입니다.

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

### [2026-06-24] claude-subscription 성공

**작업:** 안녕, 간단히 자기소개해줘

**결과:** 안녕하세요! 👋

저는 **Claude**입니다. Anthropic이 만든 AI 어시스턴트예요.

현재 **NAMU Agent System** 환경에서 동작하고 있어요. 이 시스템은 벤더 독립 멀티에이전트 플랫폼으로, 다양한 AI를 작업에 맞게 활용할 수 있도록 설계된 프로젝트입니다.

**제가 도울 수 있는 것들:**
- 💬 대화 및 질문 답변
- 💻 코...

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

### [2026-06-24] claude-subscription 성공

**작업:** y

**결과:** 네! 😊 무엇을 도와드릴까요?

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

### [2026-06-24] claude-subscription 성공

**작업:** 파이썬이랑 자바스크립트 중 뭐가 더 좋아?

**결과:** 좋은 질문이에요! 솔직히 말하면 저는 AI라서 "좋아한다"는 감정은 없지만, 객관적으로 비교해드릴게요 😄

---

### [2026-06-24] claude-subscription 성공

**작업:** y

**결과:** 네! 😊 더 궁금한 게 있으시면 편하게 물어보세요~

Python이나 JavaScript 관련해서 더 알고 싶은 게 있으신가요? 아니면 다른 주제도 좋아요! 🙌

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

## 🐍 Python vs 🟨 JavaScript

| 항목 | Python | JavaScript |
|------|--------|-----------|
| **문법** | 깔끔하고 읽기 쉬움 | 유연하지만 quirky |
| **주 용도...

**판단:** 어댑터 `claude-subscription` (priority=2) 자동 선택

## 실패 패턴 (Failure Patterns)

<!-- 형식: ## [날짜] [작업유형] 제목
실패 원인과 교훈 기록 -->

---

## 도출된 기준 (Derived Rules)

<!-- 패턴 분석으로 자동/수동 도출된 판단 기준 -->
