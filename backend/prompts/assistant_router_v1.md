# AI 비서 라우터 프롬프트 v1

사용자 질문을 분석해 지정된 JSON 스키마(RouterDecision)로 분류하라. **답변을 생성하지 말고 분류만** 하라.

## 필드

- `intent`:
  - `stats`  — 통계형 ("제일 큰 문제 뭐야?", "지난달 대비 어때?")
  - `evidence` — 근거형 ("위생 관련 리뷰 보여줘", "대기시간 불만 리뷰")
  - `both`   — 복합형 (통계 + 근거 리뷰 둘 다)
  - `chitchat` — 잡담/일반 대화
- `aspect`: 특정 항목(맛/친절/청결/대기시간/가격/분위기)에 관한 질문이면 그 항목명, 아니면 null
- `sentiment`: 긍정/부정 리뷰를 특정하면 `pos`/`neg`, 아니면 null
- `period_weeks`: 기간(최근 N주). 명시 없으면 4
- `query_text`: evidence 검색용 핵심 문장/키워드 (근거형일 때만, 아니면 null)

## 질문

{question}
