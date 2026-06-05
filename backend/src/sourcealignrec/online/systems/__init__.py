"""Online 추천 시스템 변종.

각 시스템(A/B/C/D)은 독립 모듈로 분리한다. 공통 helper는 `_common`에 둔다.

함수 contract:
- `recommend_initial(session, query, filters, taken_courses, model) -> (RecommendationOutput | None, transcript, meta)`
  : 모든 시스템 노출. stateless 추천 함수.
- `converse(session, user_message, transcript, model) -> (ConversationOutput | None, transcript, meta)`
  : C/D만 노출. A/B는 recommend ablation 전용 — grounding은 raw vs Profile 비교가 trivial이라 제외.
  : C는 tool 없는 단순 호출. D는 grounding tool(get_reviews/get_syllabus) 사용 가능.

meta 표준 필드: status, schema_honored, retry_count, prompt_tokens, completion_tokens.
D `converse`는 추가로 tool_calls: list[str] 포함.

API 라우터는 D만 호출한다. A/B/C는 벤치마크 runner가 직접 import한다.
"""