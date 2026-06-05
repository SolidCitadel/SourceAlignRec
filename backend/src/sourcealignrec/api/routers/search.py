"""검색 router — api-contract/search.md 정합 (POST /search)."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlmodel import Session, select

from sourcealignrec.api._schemas import ClassMeetingOut, WireModel, parse_meetings_json
from sourcealignrec.api._security import get_current_user
from sourcealignrec.db.models import (
    Course,
    CourseHistory,
    Offering,
    OfferingAttribute,
    Professor,
    User,
)
from sourcealignrec.db.session import get_session
from sourcealignrec.online import dept_lens
from sourcealignrec.online import filter as hard_filter

router = APIRouter(tags=["search"])

_MAX_RESULTS = 100


# ── Attribute key mapping (wire camelCase ↔ DB snake_case) ──────────────────


_ATTR_WIRE_TO_DB = {
    "grading": "grading_leniency",
    "assignment": "assignment_load",
    "team_project": "team_project",     # alias로 wire는 'teamProject', DB는 'team_project'
    "exam_weight": "exam_weight",       # alias로 wire는 'examWeight'
    "attendance": "attendance_strictness",
}


# ── Wire schemas ────────────────────────────────────────────────────────────


class AttributeFilter(WireModel):
    grading: list[str] = Field(default_factory=list)
    assignment: list[str] = Field(default_factory=list)
    team_project: list[str] = Field(default_factory=list)
    exam_weight: list[str] = Field(default_factory=list)
    attendance: list[str] = Field(default_factory=list)


class SearchFilter(WireModel):
    # 학과는 단일선택 = 카탈로그 필터 + 이수구분 렌즈 (KHU p_major와 동일 구조).
    # 빈 문자열이면 본인 학과(User.department) 기준으로 resolve. dept code(예: "A10627").
    department: str = ""
    course_types: list[str] = Field(default_factory=list)
    credits: list[int] = Field(default_factory=list)
    keyword: str = ""
    english_only: bool = False
    attributes: AttributeFilter = Field(default_factory=AttributeFilter)


class SearchRequest(WireModel):
    filter: SearchFilter
    sort: Literal["course_name", "course_id", "credit"] = "course_name"


class OfferingAttributesOut(WireModel):
    """row 없거나 winner가 '없음'이면 null emit. UI에서 그 칩 미표시."""
    grading: str | None = None
    assignment: str | None = None
    team_project: str | None = None
    exam_weight: str | None = None
    attendance: str | None = None


class OfferingSearchResultOut(WireModel):
    id: str
    course_name: str
    professor_name: str
    credit: int
    type: str
    department: str
    english_only: bool
    is_online: bool
    meetings: list[ClassMeetingOut]
    attributes: OfferingAttributesOut
    taken: bool = False            # 본인 수강이력에 있는 과목(course_id 매칭). 프론트 '수료 숨김' 대상.
    taken_grade: str | None = None  # taken=True일 때 최신 학기 성적, 아니면 null.


class SearchResponse(WireModel):
    results: list[OfferingSearchResultOut]


# ── Endpoint ────────────────────────────────────────────────────────────────


def _attribute_lookup(session: Session, offering_ids: list[str]) -> dict[str, dict[str, str]]:
    """offering_id → {attr_name(db): value}. 없으면 default."""
    if not offering_ids:
        return {}
    rows = session.exec(
        select(
            OfferingAttribute.offering_id,
            OfferingAttribute.attribute_name,
            OfferingAttribute.attribute_value,
        ).where(OfferingAttribute.offering_id.in_(offering_ids))
    ).all()
    result: dict[str, dict[str, str]] = {}
    for oid, name, value in rows:
        result.setdefault(oid, {})[name] = value
    return result


class DepartmentOut(WireModel):
    code: str
    name: str
    # 그 학과 카탈로그에 실재하는 이수구분 라벨(학사 위계순). 검색 필터 이수구분 선택지.
    course_types: list[str] = Field(default_factory=list)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(session: Session = Depends(get_session)):
    """검색 학과 선택지 — 이수구분 데이터가 있는 학과만 (단일선택 렌즈의 의미 있는 후보)."""
    return [
        DepartmentOut(code=code, name=name, course_types=dept_lens.dept_course_types(session, code))
        for code, name in dept_lens.available_departments(session)
    ]


@router.post("/search", response_model=SearchResponse)
def search(
    req: SearchRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    f = req.filter

    # 1) Hard filter (attribute only). 수강이력은 **제거하지 않고** taken 표기만 한다
    #    — 재수강 가능성 때문에 프론트 '수료 숨김' 소프트 토글이 숨김/복원 처리
    #    (api-contract/search.md §3.3, history.md §2). 따라서 taken_course_ids=[].
    db_attr_filters = {
        _ATTR_WIRE_TO_DB[k]: v for k, v in {
            "grading": f.attributes.grading,
            "assignment": f.attributes.assignment,
            "team_project": f.attributes.team_project,
            "exam_weight": f.attributes.exam_weight,
            "attendance": f.attributes.attendance,
        }.items() if v
    }
    candidate_ids = set(hard_filter.run(session, db_attr_filters, taken_course_ids=[]))

    # 수강이력(카탈로그 매칭분) → course_id별 최신 학기 성적. 결과 taken 표기용.
    taken_grade: dict[str, str] = {}
    _taken_term: dict[str, str] = {}
    for cid, grade, term in session.exec(
        select(CourseHistory.course_id, CourseHistory.grade, CourseHistory.term)
        .where(CourseHistory.user_id == user.id)
        .where(CourseHistory.is_custom == False)  # noqa: E712 — SQL boolean 비교
        .where(CourseHistory.course_id.is_not(None))
    ).all():
        if cid not in _taken_term or (term or "") > _taken_term[cid]:
            _taken_term[cid] = term or ""
            taken_grade[cid] = grade

    # 2) 학과 렌즈 resolve: 단일 학과 = 카탈로그 필터 + 이수구분 렌즈 (KHU p_major 구조).
    #    req.filter.department(code) 우선, 없으면 본인 학과(User.department) resolve.
    dept_code = f.department.strip() or dept_lens.resolve_department_code(session, user.department)

    # 그 학과 카탈로그의 이수구분 렌즈: offering_id → course_type(그 학과 기준).
    # 미수집/미해결 학과 → 빈 렌즈 → 결과 없음 (그 학과 카탈로그 데이터 부재).
    lens = dept_lens.dept_classification_map(session, dept_code)
    if not lens:
        return SearchResponse(results=[])

    # 3) 학점/영어강좌 SQL where (course_type은 렌즈 기준이라 Python side)
    stmt = select(Offering, Course, Professor).join(
        Course, Course.id == Offering.course_id,
    ).join(Professor, Professor.id == Offering.professor_id)
    if f.credits:
        stmt = stmt.where(Offering.credits.in_(f.credits))
    if f.english_only:
        stmt = stmt.where(Offering.is_english == True)  # noqa: E712 — SQLModel idiom

    rows = session.exec(stmt).all()

    # 4) 렌즈 멤버십(그 학과 카탈로그) + course_type(렌즈 기준) + keyword + candidate_ids (Python side)
    kw = f.keyword.strip().lower()
    course_types = set(f.course_types)
    filtered = []
    for offering, course, professor in rows:
        if offering.id not in candidate_ids:
            continue
        if offering.id not in lens:                       # 그 학과 카탈로그에 없음 → 제외
            continue
        if course_types and lens[offering.id] not in course_types:
            continue
        if kw:
            hay = f"{course.name} {professor.name}".lower()
            if kw not in hay:
                continue
        filtered.append((offering, course, professor))

    # 4) sort
    if req.sort == "course_name":
        filtered.sort(key=lambda x: x[1].name)
    elif req.sort == "course_id":
        filtered.sort(key=lambda x: x[0].id)
    elif req.sort == "credit":
        filtered.sort(key=lambda x: -(x[0].credits or 0))

    # 5) 상한 + attribute lookup
    capped = filtered[:_MAX_RESULTS]
    attr_map = _attribute_lookup(session, [o.id for o, _, _ in capped])

    results = []
    for offering, course, professor in capped:
        attrs_db = attr_map.get(offering.id, {})
        results.append(
            OfferingSearchResultOut(
                id=offering.id,
                course_name=course.name,
                professor_name=professor.name,
                credit=offering.credits or 0,
                type=lens.get(offering.id, ""),
                department=offering.dept_name or "",
                english_only=offering.is_english,
                is_online=bool(offering.is_online),
                meetings=parse_meetings_json(offering.meetings_json),
                attributes=_attrs_out(attrs_db),
                taken=offering.course_id in taken_grade,
                taken_grade=taken_grade.get(offering.course_id),
            )
        )
    return SearchResponse(results=results)


def _attrs_out(attrs_db: dict[str, str]) -> OfferingAttributesOut:
    """row 없거나 '없음' winner면 None. UI에서 그 칩 미표시 (api-contract §3.2)."""
    def emit(v: str | None) -> str | None:
        return None if v is None or v == "없음" else v

    return OfferingAttributesOut(
        grading=emit(attrs_db.get("grading_leniency")),
        assignment=emit(attrs_db.get("assignment_load")),
        team_project=emit(attrs_db.get("team_project")),
        exam_weight=emit(attrs_db.get("exam_weight")),
        attendance=emit(attrs_db.get("attendance_strictness")),
    )
