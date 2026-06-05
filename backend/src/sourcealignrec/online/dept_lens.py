"""학과 렌즈 — 이수구분은 (offering, 조회학과) 쌍 속성이다.

표시 surface(검색·상세·추천·교수·courses·MCP)가 공유하는 정본:
- `resolve_department_code`: User.department(자유문자열) → Department.code
- `dept_classification_map`: dept 기준 offering_id → course_type(이수구분 렌즈)
- `available_departments`: 이수구분 데이터(classification) 보유 학과 (선택지·안내용)

이수구분은 표시 전용 — Hard Filter·검색 retrieval·LLM 컨텍스트에는 들어가지 않는다.
렌즈 밖(그 학과 카탈로그에 없음) offering은 빈 문자열로 표시(칩 제거).
"""
from __future__ import annotations

from sqlmodel import Session, select

from sourcealignrec.db.models import Department, OfferingDeptClassification

# 추천 지원 학과 — OfferingProfile corpus가 컴공-학생 강의평 기반이라 컴공 카탈로그만 대표성 있음.
# 비컴공은 cross-listed CS만 나오는 편향된 반쪽 추천이라 차단. profile이 전 학과로 확장되면 여기만 수정.
RECOMMEND_SUPPORTED_DEPT_CODES: list[str] = ["A10627"]  # 소프트웨어융합대학 컴퓨터공학부 컴퓨터공학과


def is_recommend_supported(dept_code: str | None) -> bool:
    return dept_code in RECOMMEND_SUPPORTED_DEPT_CODES


def resolve_department_code(session: Session, dept_query: str | None) -> str | None:
    """User.department(예 '컴퓨터공학과') → Department.code. lenient substring·유일 매칭만."""
    q = (dept_query or "").strip()
    if not q:
        return None
    rows = session.exec(select(Department.code, Department.name)).all()
    matches = [code for code, name in rows if q in (name or "")]
    return matches[0] if len(matches) == 1 else None


def dept_classification_map(
    session: Session, dept_code: str | None, offering_ids: list[str] | None = None,
) -> dict[str, str]:
    """dept_code 기준 offering_id → course_type(이수구분). offering_ids 주면 그 범위만 조회."""
    if not dept_code:
        return {}
    stmt = select(
        OfferingDeptClassification.offering_id, OfferingDeptClassification.course_type,
    ).where(OfferingDeptClassification.dept_code == dept_code)
    if offering_ids is not None:
        if not offering_ids:
            return {}
        stmt = stmt.where(OfferingDeptClassification.offering_id.in_(offering_ids))
    return {oid: ct for oid, ct in session.exec(stmt).all()}


# 이수구분 표시 위계 — KHU gradIsuCd 코드 순서(숫자 오름차순)는 학사 위계가 아니라
# (전공필수=04 < 전공기초=11) 위계와 어긋나므로 무의미하다. 도메인 위계를 명시한다:
# 공통/전공 기초 → 필수 → 선택 → 교양류 → 교직·대학원류 → 미분류. 미등재 라벨은 끝(라벨 사전순).
_COURSE_TYPE_ORDER: list[str] = [
    "공통필수", "전공기초", "전공공통", "전공필수", "전공선택",
    "공통과목", "일반선택", "교직", "교직전선", "선수과목",
    "논문지도과목", "종합시험", "외국어대체", "논문대체", "구분없음", "과정구분없음",
]


def dept_course_types(session: Session, dept_code: str | None) -> list[str]:
    """dept_code 카탈로그에 실재하는 이수구분 라벨 — 학사 위계순. 검색 필터 선택지 정본.

    하드코딩(예 '교양')이 아니라 그 학과 offering의 실제 field_gb 라벨만 노출한다.
    학과를 바꾸면 그 학과에 있는 라벨만 뜨고(없는 건 안 뜸), 미수집 학과면 빈 목록.
    """
    if not dept_code:
        return []
    rows = session.exec(
        select(OfferingDeptClassification.course_type)
        .where(OfferingDeptClassification.dept_code == dept_code)
        .distinct()
    ).all()
    rank = {t: i for i, t in enumerate(_COURSE_TYPE_ORDER)}
    return sorted(set(rows), key=lambda t: (rank.get(t, len(_COURSE_TYPE_ORDER)), t))


def available_dept_codes(session: Session) -> list[str]:
    """이수구분 데이터(classification)가 있는 학과 code 목록."""
    return sorted(set(session.exec(select(OfferingDeptClassification.dept_code)).all()))


def available_departments(session: Session) -> list[tuple[str, str]]:
    """(code, name) — classification 보유 학과, name 정렬."""
    codes = available_dept_codes(session)
    if not codes:
        return []
    rows = session.exec(
        select(Department.code, Department.name).where(Department.code.in_(codes))
    ).all()
    return sorted(rows, key=lambda r: r[1])
