"""Hard Filter — Attribute 조건 미충족 과목 제외."""
from __future__ import annotations

from sqlmodel import Session, select

from sourcealignrec.db.models import Offering, OfferingAttribute

UNKNOWN_TOKEN = "정보 없음"  # api-contract/search.md §2 filter chip "정보 없음"


def run(
    session: Session,
    filters: dict[str, list[str]],
    taken_course_ids: list[str],
) -> list[str]:
    """Hard Filter 통과한 offering_id 목록 반환.

    각 attribute filter (allowed list 비어있지 않을 때):
    - row 있음 + value가 allowed에 있음 → 통과
    - row 있음 + value가 "없음" (신호 없음) → "정보 없음"이 allowed에 있으면 통과
    - row 없음 → "정보 없음"이 allowed에 있으면 통과, 없으면 제외
    - 그 외 → 제외

    taken_course_ids: 이미 수강한 course_id의 Offering 전체 제외.
    """
    all_offerings = session.exec(select(Offering.id, Offering.course_id)).all()

    excluded: set[str] = {oid for oid, cid in all_offerings if cid in set(taken_course_ids)}

    active_filters = {k: v for k, v in filters.items() if v}
    if active_filters:
        attr_rows = session.exec(
            select(
                OfferingAttribute.offering_id,
                OfferingAttribute.attribute_name,
                OfferingAttribute.attribute_value,
            )
        ).all()

        offering_attrs: dict[str, dict[str, str]] = {}
        for oid, name, value in attr_rows:
            offering_attrs.setdefault(oid, {})[name] = value

        for oid, _ in all_offerings:
            if oid in excluded:
                continue
            attrs = offering_attrs.get(oid, {})
            for attr_name, allowed in active_filters.items():
                val = attrs.get(attr_name)
                # "없음" winner(신호 없음) 또는 row 없음 → unknown으로 취급.
                is_unknown = val is None or val == "없음"
                if is_unknown:
                    if UNKNOWN_TOKEN not in allowed:
                        excluded.add(oid)
                        break
                else:
                    if val not in allowed:
                        excluded.add(oid)
                        break

    return [oid for oid, _ in all_offerings if oid not in excluded]
