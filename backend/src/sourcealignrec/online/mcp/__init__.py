"""MCP 도구 레이어 — 백엔드 read 능력을 user-free 도메인 함수로 노출.

ChatKHU(LLM)가 대화 중 호출하는 primitive 도구 모음. 추천은 후보를 좁히는 도구 하나일 뿐이다.
라우터(JWT/user 종속, 웹 wire shape)가 아니라 그 아래 도메인 로직을 직접 래핑한다.

데이터 부재 응답 규약 (plans/archive/2026-05-30-chatkhu-mcp.md §3 1단계) — 침묵 금지, 3구분:
  ① 대상 없음(잘못된 id) → found:false
  ② 유효 조건·매칭 0건 → 빈 결과 + note(사유)
  ③ 대상은 있으나 연관 데이터 부재(리뷰·계획서·profile) → 기본 + null/[] + note
"""
from sourcealignrec.online.mcp.tools import (
    get_course,
    get_professor,
    get_reviews_all,
    get_syllabus,
    recommend_courses,
    search_courses,
)

__all__ = [
    "search_courses",
    "get_course",
    "get_syllabus",
    "get_reviews_all",
    "get_professor",
    "recommend_courses",
]