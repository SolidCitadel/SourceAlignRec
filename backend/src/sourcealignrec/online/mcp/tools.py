"""MCP 도구 구현 — user-free 도메인 함수 5개.

반환은 전부 JSON 직렬화 가능한 dict. 데이터 부재는 not-found / 빈+note / null+note로 구분한다
(__init__.py 규약 참조). 모든 함수는 첫 인자로 SQLModel Session을 받는다 (호출 측이 세션 관리).
"""
from __future__ import annotations

import json

from sqlalchemy import or_
from sqlmodel import Session, func, select

from sourcealignrec.api._review_view import (
    REVIEW_TYPE_FIELDS,
    _TYPE_THRESHOLD,
    types_for_review,
)
from sourcealignrec.core.config import settings
from sourcealignrec.db.models import (
    Course,
    Offering,
    OfferingAttribute,
    OfferingDeptClassification,
    OfferingProfile,
    Professor,
    ProfessorProfile,
    ProfessorRepresentativeReview,
    RepresentativeReview,
    Review,
    ReviewClassification,
)
from sourcealignrec.online import dept_lens
from sourcealignrec.online import filter as hard_filter
from sourcealignrec.online.systems import system_d
from sourcealignrec.online.systems._common import generate_recommendation

_MAX_RESULTS = 50

# attribute wire(도구 인자)→db 컬럼명. routers/search.py와 동일 매핑.
_ATTR_WIRE_TO_DB = {
    "grading": "grading_leniency",
    "assignment": "assignment_load",
    "team_project": "team_project",
    "exam_weight": "exam_weight",
    "attendance": "attendance_strictness",
}
_ATTR_DB_TO_WIRE = {v: k for k, v in _ATTR_WIRE_TO_DB.items()}

# 강의계획서 필드: overview/objectives는 평문, 나머지는 JSON 배열 (db/models.py Offering).
_SYLLABUS_FIELDS = (
    "course_overview",
    "learning_objectives",
    "weekly_topics",
    "evaluation_items",
    "prerequisite_courses",
)


# ── 내부 helper ──────────────────────────────────────────────────────────────


def _parse_json(raw: str | None):
    """JSON 문자열 → 파싱값. 실패 시 원문 그대로."""
    try:
        return json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return raw


def _parse_professor_profile(profile_json: str | None) -> dict[str, str] | None:
    """ProfessorProfile.profile_json → 4필드 dict. row 없거나 본문(format) 비면 None.

    routers/professors.py `_parse_profile`와 동일 규칙 (4필드: format/evaluation/
    reviews_summary/caveats, topic 제외). 정본 구조: db/models.py ProfessorProfile.
    """
    if not profile_json:
        return None
    try:
        d = json.loads(profile_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not d.get("format", "").strip():
        return None
    return {
        "format": d.get("format", ""),
        "evaluation": d.get("evaluation", ""),
        "reviews_summary": d.get("reviews_summary", ""),
        "caveats": d.get("caveats", ""),
    }


def _parse_offering_profile(profile_json: str | None) -> dict[str, str] | None:
    """OfferingProfile.profile_json → 5필드 dict. row 없으면 None.

    5필드(topic/format/evaluation/reviews_summary/caveats) 정본: db/models.py OfferingProfile.
    routers/offerings.py와 달리 빈 struct 대신 None을 emit (MCP 데이터부재 규약: null+note).
    """
    if not profile_json:
        return None
    try:
        d = json.loads(profile_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return {
        "topic": d.get("topic", ""),
        "format": d.get("format", ""),
        "evaluation": d.get("evaluation", ""),
        "reviews_summary": d.get("reviews_summary", ""),
        "caveats": d.get("caveats", ""),
    }


def _representative_reviews(session: Session, offering: Offering) -> list[dict]:
    """offering의 대표 강의평(DynamicScore 선정, Course+Professor 단위) → 리뷰 dict list.

    rank 순. 각 리뷰에 ReviewClassifier 타입 list 부착. 선정 리뷰 없으면 빈 list.
    """
    rows = session.exec(
        select(Review.id, Review.raw_text, Review.term, RepresentativeReview.rank)
        .join(RepresentativeReview, RepresentativeReview.review_id == Review.id)
        .where(RepresentativeReview.course_id == offering.course_id)
        .where(RepresentativeReview.professor_id == offering.professor_id)
        .order_by(RepresentativeReview.rank)
    ).all()
    if not rows:
        return []
    cls = {
        c.review_id: c
        for c in session.exec(
            select(ReviewClassification).where(
                ReviewClassification.review_id.in_([rid for rid, *_ in rows])
            )
        ).all()
    }
    return [
        {"rank": rank, "term": term, "text": text, "types": types_for_review(cls.get(rid))}
        for rid, text, term, rank in rows
    ]


def _attribute_lookup(session: Session, offering_ids: list[str]) -> dict[str, dict[str, str]]:
    """offering_id → {db_attr_name: value}."""
    if not offering_ids:
        return {}
    rows = session.exec(
        select(
            OfferingAttribute.offering_id,
            OfferingAttribute.attribute_name,
            OfferingAttribute.attribute_value,
        ).where(OfferingAttribute.offering_id.in_(offering_ids))
    ).all()
    out: dict[str, dict[str, str]] = {}
    for oid, name, value in rows:
        out.setdefault(oid, {})[name] = value
    return out


def _attrs_clean(attrs_db: dict[str, str]) -> dict[str, str]:
    """db attr → wire 이름. row 없거나 '없음' winner는 제외 (신호 없음)."""
    out: dict[str, str] = {}
    for db_name, value in attrs_db.items():
        wire = _ATTR_DB_TO_WIRE.get(db_name)
        if wire and value and value != "없음":
            out[wire] = value
    return out


def _offering_card(offering: Offering, course: Course | None, professor: Professor | None,
                   attrs_db: dict[str, str], course_type: str | None = None) -> dict:
    """검색·추천 결과 1건 공통 shape.

    type(이수구분)은 조회학과(department) 기준 렌즈 값 — dept 없이 조회하면 None(학과별로 달라 단일값 무의미).
    department는 개설학과(고정).
    """
    return {
        "offering_id": offering.id,
        "course_name": course.name if course else None,
        "professor_id": offering.professor_id,
        "professor_name": professor.name if professor else None,
        "credit": offering.credits or 0,
        "type": course_type or None,
        "department": offering.dept_name or None,
        "term": offering.term,
        "english_only": bool(offering.is_english),
        "is_online": bool(offering.is_online),
        "meetings": _parse_json(offering.meetings_json),
        "attributes": _attrs_clean(attrs_db),
    }


def _filter_offerings(
    session: Session,
    *,
    query: str = "",
    dept_lens_map: dict[str, str] | None = None,
    course_types: list[str] | None = None,
    credits: list[int] | None = None,
    attributes: dict[str, list[str]] | None = None,
    english_only: bool = False,
) -> list[tuple[Offering, Course, Professor]]:
    """routers/search.py의 필터 로직(user/taken 제외판). (offering, course, professor) list 반환.

    dept_lens_map(offering_id→이수구분) 주면 그 학과 카탈로그 멤버십 필터 + 이수구분(course_types)
    필터를 렌즈 기준으로 적용. 수강이력·taken 없음 — ChatKHU엔 user 개념이 없다. 정렬·상한은 호출 측.
    """
    db_attr_filters = {
        _ATTR_WIRE_TO_DB[k]: v
        for k, v in (attributes or {}).items()
        if v and k in _ATTR_WIRE_TO_DB
    }
    candidate_ids = set(hard_filter.run(session, db_attr_filters, taken_course_ids=[]))

    stmt = (
        select(Offering, Course, Professor)
        .join(Course, Course.id == Offering.course_id)
        .join(Professor, Professor.id == Offering.professor_id)
    )
    if credits:
        stmt = stmt.where(Offering.credits.in_(credits))
    if english_only:
        stmt = stmt.where(Offering.is_english == True)  # noqa: E712 — SQLModel idiom
    rows = session.exec(stmt).all()

    # 학과 카탈로그 멤버십 + 이수구분(렌즈) + keyword는 Python side.
    kw = (query or "").strip().lower()
    course_types_set = set(course_types or [])
    out: list[tuple[Offering, Course, Professor]] = []
    for offering, course, professor in rows:
        if offering.id not in candidate_ids:
            continue
        if dept_lens_map is not None:
            if offering.id not in dept_lens_map:        # 그 학과 카탈로그에 없음
                continue
            if course_types_set and dept_lens_map[offering.id] not in course_types_set:
                continue
        if kw and kw not in f"{course.name} {professor.name}".lower():
            continue
        out.append((offering, course, professor))
    return out


def _hydrate_recommendations(
    session: Session, items: list, lens_map: dict[str, str] | None = None,
) -> list[dict]:
    """RecommendationOutput.recommendations(rank, offering_id, rationale) → 카드 + rationale."""
    if not items:
        return []
    offering_ids = [it.offering_id for it in items]
    rows = session.exec(
        select(Offering, Course, Professor)
        .join(Course, Course.id == Offering.course_id)
        .join(Professor, Professor.id == Offering.professor_id)
        .where(Offering.id.in_(offering_ids))
    ).all()
    by_id = {o.id: (o, c, p) for o, c, p in rows}
    attr_map = _attribute_lookup(session, offering_ids)
    out: list[dict] = []
    for it in items:
        triple = by_id.get(it.offering_id)
        if triple is None:
            continue
        o, c, p = triple
        ct = lens_map.get(o.id) if lens_map else None
        card = _offering_card(o, c, p, attr_map.get(o.id, {}), ct)
        card["rank"] = it.rank
        card["rationale"] = it.rationale
        out.append(card)
    return out


# ── 도구 1: search_courses ───────────────────────────────────────────────────


def search_courses(
    session: Session,
    query: str = "",
    *,
    department: str | None = None,
    course_types: list[str] | None = None,
    credits: list[int] | None = None,
    attributes: dict[str, list[str]] | None = None,
    english_only: bool = False,
    limit: int = _MAX_RESULTS,
) -> dict:
    """과목 검색. query는 과목명·교수명 부분일치. department(학과명)를 주면 그 학과 카탈로그로
    한정하고 이수구분(type)을 그 학과 기준으로 매긴다. course_types(이수구분) 필터는 department가
    있어야 적용된다. 매칭 0건이면 빈 results + note. 미수집 학과면 그 사실을 note로 구분."""
    dept_code = dept_lens.resolve_department_code(session, department) if department else None
    lens_map = dept_lens.dept_classification_map(session, dept_code) if dept_code else None
    if department and not lens_map:
        avail = dept_lens.available_departments(session)
        return {
            "count": 0, "results": [],
            "note": (
                f"'{department}' 학과의 카탈로그는 아직 수집되지 않았습니다(이 빈 결과는 '과목이 없다'는 뜻이 "
                f"아닙니다). 이수구분을 매길 수 있는 학과: {', '.join(n for _, n in avail)}."
            ),
        }
    rows = _filter_offerings(
        session, query=query, dept_lens_map=lens_map, course_types=course_types,
        credits=credits, attributes=attributes, english_only=english_only,
    )
    rows.sort(key=lambda x: x[1].name)
    capped = rows[:limit]
    attr_map = _attribute_lookup(session, [o.id for o, _, _ in capped])
    results = [
        _offering_card(o, c, p, attr_map.get(o.id, {}), lens_map.get(o.id) if lens_map else None)
        for o, c, p in capped
    ]
    out = {"count": len(results), "results": results}
    if not results:
        out["note"] = "조건에 맞는 과목이 없습니다."
    elif len(rows) > limit:
        out["note"] = f"{len(rows)}건 중 상위 {limit}건만 반환했습니다. 조건을 좁혀 다시 검색하세요."
    return out


# ── 도구 2: get_course ───────────────────────────────────────────────────────


def get_course(session: Session, offering_id: str) -> dict:
    """과목 상세 — 메타 + 종합 프로필(profile) + 대표 강의평(reviews).

    profile = 강의계획서·강의평을 종합한 5필드 요약(topic/format/evaluation/reviews_summary/caveats).
    reviews = DynamicScore 선정 대표 강의평 원문. 요약·대표 근거를 한 번에 주는 1차 상세 창구.
    raw 강의계획서(주차별 주제·평가 항목 등 축자 사실)는 get_syllabus로 분리.

    offering 없으면 found:false. profile 미생성이면 profile:null + profile_note.
    대표 강의평 없으면 reviews:[] + reviews_note.
    """
    row = session.exec(
        select(Offering, Course, Professor)
        .join(Course, Course.id == Offering.course_id)
        .join(Professor, Professor.id == Offering.professor_id)
        .where(Offering.id == offering_id)
    ).first()
    if row is None:
        return {"found": False, "offering_id": offering_id, "note": "해당 과목을 찾을 수 없습니다."}
    offering, course, professor = row
    attr_map = _attribute_lookup(session, [offering_id])

    out = {"found": True, **_offering_card(offering, course, professor, attr_map.get(offering_id, {}))}
    # 이수구분은 조회학과별로 다름 → 무상태 상세에선 학과별 전체를 준다(단일 type은 None).
    out["classifications"] = [
        {"department": odc.dept_name, "type": odc.course_type}
        for odc in session.exec(
            select(OfferingDeptClassification)
            .where(OfferingDeptClassification.offering_id == offering_id)
        ).all()
    ]

    profile_row = session.get(OfferingProfile, offering_id)
    profile = _parse_offering_profile(profile_row.profile_json if profile_row else None)
    out["profile"] = profile
    if profile is None:
        out["profile_note"] = "이 강의의 종합 프로필 정보는 아직 없습니다."

    reviews = _representative_reviews(session, offering)
    out["reviews"] = reviews
    if not reviews:
        out["reviews_note"] = "이 강의에 대한 강의평 데이터가 아직 없습니다."
    return out


# ── 도구 3: get_syllabus ─────────────────────────────────────────────────────


def get_syllabus(session: Session, offering_id: str) -> dict:
    """과목 강의계획서 원문(축자 사실). 개요·학습목표·주차별 주제·평가 항목·선수과목.

    평가 비중·주차별 진도·선수과목처럼 계획서에 명시된 구체 사실이 필요할 때 사용.
    종합 요약·강의평은 get_course. offering 없으면 found:false, 계획서 없으면 syllabus:null + note.
    """
    offering = session.get(Offering, offering_id)
    if offering is None:
        return {"found": False, "offering_id": offering_id, "note": "해당 과목을 찾을 수 없습니다."}

    syllabus: dict = {}
    for field in _SYLLABUS_FIELDS:
        val = getattr(offering, field)
        if not val or val == "[]":
            continue
        syllabus[field] = _parse_json(val)

    out = {"found": True, "offering_id": offering_id, "syllabus": syllabus or None}
    if not syllabus:
        out["note"] = "강의계획서 정보가 없습니다."
    return out


# ── 도구 4: get_reviews_all ──────────────────────────────────────────────────

_REVIEWS_ALL_MAX = 50  # limit 클램프 상한 (컨텍스트 보호)


def get_reviews_all(
    session: Session,
    offering_id: str,
    *,
    types: list[str] | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    """과목 전체 강의평(noise 제외) — 타입 필터 + 페이지네이션.

    대표 강의평(get_course의 reviews)보다 많은 원문이 필요할 때 사용. types를 주면 그 타입 중
    하나라도 해당하는 강의평만(OR). limit/offset으로 페이지. noise 리뷰는 제외, 최신 학기 우선 정렬.
    offering 없으면 found:false. 매칭 0건이면 빈 reviews + note. 반환: total(전체 매칭 수)·
    returned·has_more로 더 있는지 판단.
    """
    offering = session.get(Offering, offering_id)
    if offering is None:
        return {"found": False, "offering_id": offering_id, "note": "해당 과목을 찾을 수 없습니다."}

    limit = max(1, min(limit, _REVIEWS_ALL_MAX))
    offset = max(0, offset)
    requested = [t for t in (types or []) if t in REVIEW_TYPE_FIELDS]

    # noise 제외: 분류 row가 있으면 is_noise=False, 미분류(user 등록 등 row 없음)는 통과.
    conds = [
        Review.course_id == offering.course_id,
        Review.professor_id == offering.professor_id,
        ReviewClassification.is_noise.is_(False) | ReviewClassification.id.is_(None),
    ]
    if requested:
        # 타입 필터는 분류 row 필요 (미분류는 NULL>=임계값=False로 자연 제외).
        conds.append(
            or_(*[getattr(ReviewClassification, f"{t}_score") >= _TYPE_THRESHOLD for t in requested])
        )

    total = session.exec(
        select(func.count())
        .select_from(Review)
        .outerjoin(ReviewClassification, ReviewClassification.review_id == Review.id)
        .where(*conds)
    ).one()

    rows = session.exec(
        select(Review, ReviewClassification)
        .outerjoin(ReviewClassification, ReviewClassification.review_id == Review.id)
        .where(*conds)
        .order_by(Review.term.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    reviews = [
        {"term": r.term, "text": r.raw_text, "types": types_for_review(c)}
        for r, c in rows
    ]
    out = {
        "found": True,
        "offering_id": offering_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(reviews),
        "has_more": offset + len(reviews) < total,
        "reviews": reviews,
    }
    if total == 0:
        out["note"] = (
            f"요청한 타입({', '.join(requested)})에 해당하는 강의평이 없습니다."
            if requested
            else "이 강의에 대한 강의평 데이터가 아직 없습니다."
        )
    return out


# ── 도구 5: get_professor ────────────────────────────────────────────────────


def get_professor(
    session: Session,
    professor_id: str | None = None,
    name: str | None = None,
) -> dict:
    """교수 정보(소속 + 종합 4필드 프로필 + 대표 강의평 + 개설 강의). id 또는 name으로 조회.
    동명 다수면 후보 list 반환. ProfessorProfile 미생성 교수면 profile:null + profile_note."""
    if professor_id:
        professor = session.get(Professor, professor_id)
    elif name:
        matches = session.exec(select(Professor).where(Professor.name == name.strip())).all()
        if len(matches) > 1:
            return {
                "found": True, "multiple": True,
                "candidates": [
                    {"id": m.id, "name": m.name, "affiliation": m.affiliation} for m in matches
                ],
                "note": "동명 교수가 여러 명입니다. id로 다시 조회하세요.",
            }
        professor = matches[0] if matches else None
    else:
        return {"found": False, "note": "professor_id 또는 name 중 하나가 필요합니다."}

    if professor is None:
        return {"found": False, "note": "해당 교수를 찾을 수 없습니다."}

    review_count = session.exec(
        select(func.count()).select_from(Review).where(Review.professor_id == professor.id)
    ).one()

    rep_rows = session.exec(
        select(Review.id, Review.raw_text, Review.term, ProfessorRepresentativeReview.rank)
        .join(
            ProfessorRepresentativeReview,
            ProfessorRepresentativeReview.review_id == Review.id,
        )
        .where(ProfessorRepresentativeReview.professor_id == professor.id)
        .order_by(ProfessorRepresentativeReview.rank)
    ).all()
    rep_cls = {
        c.review_id: c
        for c in session.exec(
            select(ReviewClassification).where(
                ReviewClassification.review_id.in_([rid for rid, *_ in rep_rows])
            )
        ).all()
    } if rep_rows else {}
    representative_reviews = [
        {"rank": rank, "term": term, "text": text, "types": types_for_review(rep_cls.get(rid))}
        for rid, text, term, rank in rep_rows
    ]

    off_rows = session.exec(
        select(Offering.id, Course.name, Offering.term)
        .join(Course, Course.id == Offering.course_id)
        .where(Offering.professor_id == professor.id)
        .order_by(Offering.term.desc())
    ).all()
    # 이수구분(type)은 조회학과별로 달라 단일값이 무의미 → 상세는 get_course의 classifications 참조.
    offerings = [
        {"offering_id": oid, "course_name": cname, "term": term}
        for oid, cname, term in off_rows
    ]

    profile_row = session.get(ProfessorProfile, professor.id)
    profile = _parse_professor_profile(profile_row.profile_json if profile_row else None)

    out = {
        "found": True,
        "id": professor.id,
        "name": professor.name,
        "affiliation": professor.affiliation,
        "review_count": review_count,
        "profile": profile,
        "representative_reviews": representative_reviews,
        "offerings": offerings,
    }
    if profile is None:
        out["profile_note"] = "이 교수의 종합 프로필 정보는 아직 없습니다."
    return out


# ── 도구 6: recommend_courses ────────────────────────────────────────────────


def recommend_courses(
    session: Session,
    query: str,
    offering_ids: list[str],
    *,
    model: str | None = None,
) -> dict:
    """후보 list 중 자연어 요구에 맞는 강의를 랭킹. search_courses로 좁힌 뒤 호출(search→recommend).

    offering_ids = 후보 모집단(search_courses 결과의 offering_id list). 자연어 query로 OfferingProfile
    유사도 검색 → shortlist → LLM 랭킹+rationale. 학과 게이팅 없음 — 게이트는 강의평 유무가 아니라
    전처리된 OfferingProfile(임베딩 포함, sar-build-profiles 산출물) 유무다. 후보 중 프로필 보유 과목만
    랭킹되며, 보유 과목이 없으면 no_profiled_candidates로 구분된다(강의평이 있어도 프로파일링 안 된
    과목은 빠짐). 빈 결과는 reason으로 구분:
      no_candidates          — offering_ids 비어있음 (먼저 search_courses 호출)
      no_profiled_candidates — 후보 중 전처리된 프로필 보유 과목 없음
      generation_failed      — LLM 추천 생성 실패
    """
    model = model or settings.api_recommend_model
    candidate_ids = list(dict.fromkeys(offering_ids or []))  # dedupe, 순서 보존
    if not candidate_ids:
        return {
            "recommendations": [], "reason": "no_candidates",
            "note": "추천할 후보가 없습니다. 먼저 search_courses로 후보 강의를 찾아 그 offering_id를 전달하세요.",
        }

    state = system_d.retrieve_from_candidates(session, query, candidate_ids)
    if not state.shortlist_ids:
        return {
            "recommendations": [], "reason": "no_profiled_candidates",
            "note": "후보 중 추천에 활용할 분석 정보가 준비된 강의가 없습니다.",
        }

    context = system_d.build_context(session, state)
    parsed, _transcript, meta = generate_recommendation(model, query, context, state.shortlist_ids)
    if parsed is None:
        return {"recommendations": [], "reason": "generation_failed",
                "note": "추천을 생성하지 못했습니다."}

    return {"recommendations": _hydrate_recommendations(session, parsed.recommendations),
            "reason": "ok"}