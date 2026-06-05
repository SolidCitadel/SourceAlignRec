"""Review classification → 타입 파생 공통 helper.

offerings / reviews / professors router가 공유. `{type}_score >= 0.5`인 타입 list.
임계값·타입 순서를 한 곳에서 관리해 라우터 간 파생 규칙 일관성 보장.
"""
from __future__ import annotations

from sourcealignrec.db.models import ReviewClassification

REVIEW_TYPE_FIELDS = ("grading", "exam", "assignment", "attendance", "teaching", "topic", "professor")
_TYPE_THRESHOLD = 0.5


def types_for_review(cls: ReviewClassification | None) -> list[str]:
    """ReviewClassification.{type}_score >= 0.5 → 활성 타입 list. cls 없으면 빈 list."""
    if cls is None:
        return []
    return [t for t in REVIEW_TYPE_FIELDS if getattr(cls, f"{t}_score", 0.0) >= _TYPE_THRESHOLD]
