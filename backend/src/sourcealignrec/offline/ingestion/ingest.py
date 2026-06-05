"""Offline 파이프라인 — raw 데이터 적재 CLI.

Usage:
    sar-ingest --data-dir ./data
"""
import argparse
import json
import re
from pathlib import Path

from sqlmodel import Session, select

from sourcealignrec.db.models import (
    Course, Professor, Offering, Review,
    OfferingAttribute, OfferingDeptClassification,
)
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.ingestion.syllabus_parser import load_syllabus, parse_professor
from sourcealignrec.offline.ingestion.time_place_parser import parse_time_place


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _professor_id(name: str, affiliation: str | None = None) -> str:
    base = re.sub(r"\s+", "", name).lower()
    if affiliation:
        aff = re.sub(r"\s+", "", affiliation).lower()
        return f"{base}_{aff}"
    return base


def _resolve_professor_id(raw_syllabus: dict, name: str, affiliation: str | None) -> str:
    """professor_id 정본 = KHU teach_cd(교수 고유코드) — 이름 충돌·소속 분할 방지.
    teach_cd 없으면 이름+소속 fallback."""
    teach_cd = str(raw_syllabus.get("teach_cd", "")).strip()
    return teach_cd or _professor_id(name, affiliation)


def _course_base_id(course_code: str) -> str:
    """분반 코드를 과목 prefix로 변환.

    - "CSE30502" → "CSE305" (마지막 2자리 분반번호 제거)
    - "EE21100" → "EE211"
    - "CSE305-02" → "CSE305" (대시 형식도 지원, legacy)
    """
    if re.search(r"-\d+$", course_code):
        return re.sub(r"-\d+$", "", course_code)
    return course_code[:-2]


def _parse_term(semester_text: str) -> str:
    m = re.search(r"(\d+)년\s*(\d)학기", semester_text)
    if not m:
        return "unknown"
    year = int(m.group(1))
    sem = m.group(2)
    full_year = 2000 + year if year < 100 else year
    return f"{full_year}-{sem}"


_EXAM_KEYWORDS = {"중간고사", "기말고사", "시험"}


def _parse_category(raw: str | None) -> str | None:
    """mapping `category`에서 이수구분 추출. 예: '전공선택(05)/전공필수(04)' → '전공선택'."""
    if not raw:
        return None
    head = raw.split("/", 1)[0].strip()
    # "전공선택(05)" → "전공선택"
    paren = head.find("(")
    if paren > 0:
        head = head[:paren].strip()
    return head or None


def _exam_weight_value(evaluation_items: list[dict]) -> str | None:
    if not evaluation_items:
        return None
    exam_ratio = sum(
        item.get("ratio", 0)
        for item in evaluation_items
        if any(kw in item.get("item", "") for kw in _EXAM_KEYWORDS)
    )
    if exam_ratio >= 60:
        return "높음"
    if exam_ratio >= 30:
        return "보통"
    return "낮음"


# ── LOAD ──────────────────────────────────────────────────────────────────────

def load(data_dir: Path) -> None:
    """raw JSON → DB."""
    mapping_files = sorted((data_dir / "raw/review-mappings/linked").glob("*.json"))
    if not mapping_files:
        raise FileNotFoundError("review-mappings/linked 파일 없음")
    mapping_file = mapping_files[-1]

    rows = json.loads(mapping_file.read_text(encoding="utf-8"))["rows"]
    print(f"mapping rows: {len(rows)}  ({mapping_file.name})")

    reviews_dir = data_dir / "raw/reviews/parsed"
    syllabi_dir = data_dir / "raw/syllabi"

    with Session(engine) as session:
        # ── Phase 1: everytime matched 구동 — 리뷰 있는 offering + 리뷰 적재 ──
        seen_offerings: set[str] = set()
        for row in rows:
            if row.get("match_status") != "matched":
                continue

            course_code: str = row["syllabus_course_code"]
            professor_name: str = row["syllabus_professor"]
            term: str = row["term"]
            lecture_id: str = row["lecture_id"]

            course_id = _course_base_id(course_code)
            offering_id = f"{course_code}_{term}"
            seen_offerings.add(offering_id)

            if not session.get(Course, course_id):
                session.add(Course(id=course_id, name=row["course_name"]))

            syllabus_path = syllabi_dir / f"{course_code}_{term}.json"
            sf = load_syllabus(syllabus_path)
            raw_syllabus = json.loads(syllabus_path.read_text(encoding="utf-8")) if syllabus_path.exists() else {}

            name_from_syllabus, affiliation = parse_professor(raw_syllabus)
            professor_name_resolved = name_from_syllabus or professor_name
            professor_id = _resolve_professor_id(raw_syllabus, professor_name_resolved, affiliation)

            if not session.get(Professor, professor_id):
                session.add(Professor(
                    id=professor_id,
                    name=professor_name_resolved,
                    affiliation=affiliation,
                ))

            if not session.get(Offering, offering_id):
                tp_raw = row.get("time_place") or ""
                meetings = parse_time_place(tp_raw)
                is_online = "온라인" in tp_raw
                # mapping의 credit이 primary (종합정보시스템 학사 정량). syllabus는 fallback.
                try:
                    credits_val: int | None = int(row.get("credit"))
                except (TypeError, ValueError):
                    credits_val = sf["credits"] if sf else None
                # Offering.course_type = 개설학과 기준(syllabus 단일값). 학생 렌즈는 OfferingDeptClassification.
                ct_val = sf["course_type"] if sf else None
                session.add(Offering(
                    id=offering_id,
                    course_id=course_id,
                    professor_id=professor_id,
                    term=term,
                    credits=credits_val,
                    course_type=ct_val,
                    dept_name=sf["dept_name"] if sf else None,
                    is_english=sf["is_english"] if sf else False,
                    is_online=is_online,
                    notice=(row.get("note") or "").strip() or None,
                    meetings_json=json.dumps(meetings, ensure_ascii=False),
                    recognized_depts_json=json.dumps(sf["recognized_depts"] if sf else [], ensure_ascii=False),
                    syllabus_url=sf["syllabus_url"] if sf else None,
                    syllabus_text=sf["syllabus_text"] if sf else None,
                    course_overview=sf["course_overview"] if sf else None,
                    learning_objectives=sf["learning_objectives"] if sf else None,
                    instruction_type_note=sf["instruction_type_note"] if sf else None,
                    instruction_type_ratios=json.dumps(sf["instruction_type_ratios"], ensure_ascii=False) if sf else "[]",
                    evaluation_items=json.dumps(sf["evaluation_items"], ensure_ascii=False) if sf else "[]",
                    weekly_topics=json.dumps(sf["weekly_topics"], ensure_ascii=False) if sf else "[]",
                    prerequisite_courses=json.dumps(sf["prerequisite_courses"], ensure_ascii=False) if sf else "[]",
                ))

            if sf:
                _upsert_syllabus_attributes(session, offering_id, sf["evaluation_items"])
                _upsert_dept_classifications(session, offering_id, sf["recognized_depts"])

            review_file = reviews_dir / f"{lecture_id}.json"
            if review_file.exists():
                _load_reviews(session, review_file, course_id, professor_id)

        # ── Phase 2: syllabi 구동 — 리뷰 없는 catalog offering (A2: 전 학과 카탈로그) ──
        review_less = 0
        for syllabus_path in sorted(syllabi_dir.glob("*.json")):
            raw_syllabus = json.loads(syllabus_path.read_text(encoding="utf-8"))
            course_code = str(raw_syllabus.get("course_code", "")).strip()
            term = str(raw_syllabus.get("term", "")).strip()
            if not course_code or not term:
                continue
            offering_id = f"{course_code}_{term}"
            if offering_id in seen_offerings or session.get(Offering, offering_id):
                continue

            sf = load_syllabus(syllabus_path)
            if not sf:
                continue
            seen_offerings.add(offering_id)
            course_id = _course_base_id(course_code)
            if not session.get(Course, course_id):
                session.add(Course(id=course_id, name=raw_syllabus.get("course_name") or course_code))

            name_from_syllabus, affiliation = parse_professor(raw_syllabus)
            professor_id = _resolve_professor_id(raw_syllabus, name_from_syllabus, affiliation)
            if not session.get(Professor, professor_id):
                session.add(Professor(id=professor_id, name=name_from_syllabus, affiliation=affiliation))
            session.flush()  # Course/Professor를 Offering FK insert 전에 확정

            session.add(Offering(
                id=offering_id,
                course_id=course_id,
                professor_id=professor_id,
                term=term,
                credits=sf["credits"],
                course_type=sf["course_type"],
                dept_name=sf["dept_name"],
                is_english=sf["is_english"],
                is_online=False,
                notice=None,
                meetings_json="[]",   # 강의시간 파싱은 review-less catalog에선 deferred
                recognized_depts_json=json.dumps(sf["recognized_depts"], ensure_ascii=False),
                syllabus_url=sf["syllabus_url"],
                syllabus_text=sf["syllabus_text"],
                course_overview=sf["course_overview"],
                learning_objectives=sf["learning_objectives"],
                instruction_type_note=sf["instruction_type_note"],
                instruction_type_ratios=json.dumps(sf["instruction_type_ratios"], ensure_ascii=False),
                evaluation_items=json.dumps(sf["evaluation_items"], ensure_ascii=False),
                weekly_topics=json.dumps(sf["weekly_topics"], ensure_ascii=False),
                prerequisite_courses=json.dumps(sf["prerequisite_courses"], ensure_ascii=False),
            ))
            session.flush()  # Offering을 attribute/classification FK insert 전에 확정
            _upsert_syllabus_attributes(session, offering_id, sf["evaluation_items"])
            _upsert_dept_classifications(session, offering_id, sf["recognized_depts"])
            review_less += 1

        session.commit()
    print(f"load 완료 (review-less catalog offering 추가: {review_less})")


def _upsert_syllabus_attributes(session: Session, offering_id: str, evaluation_items: list[dict]) -> None:
    exam_val = _exam_weight_value(evaluation_items)
    if exam_val is None:
        return

    existing = session.exec(
        select(OfferingAttribute)
        .where(OfferingAttribute.offering_id == offering_id)
        .where(OfferingAttribute.attribute_name == "exam_weight")
        .where(OfferingAttribute.source == "syllabus")
    ).first()

    if existing:
        existing.attribute_value = exam_val
        session.add(existing)
    else:
        session.add(OfferingAttribute(
            offering_id=offering_id,
            attribute_name="exam_weight",
            attribute_value=exam_val,
            source="syllabus",
        ))


def _upsert_dept_classifications(
    session: Session, offering_id: str, recognized_depts: list[dict],
) -> None:
    """recognized_depts[].course_type → OfferingDeptClassification (per-학과 이수구분).
    이수구분 코드 없는 entry(미매핑 field_gb 등)는 skip."""
    for rd in recognized_depts:
        code = (rd.get("code") or "").strip()
        name = (rd.get("name") or "").strip()
        course_type = (rd.get("course_type") or "").strip()
        if not code or not course_type:
            continue
        existing = session.exec(
            select(OfferingDeptClassification)
            .where(OfferingDeptClassification.offering_id == offering_id)
            .where(OfferingDeptClassification.dept_code == code)
        ).first()
        if existing:
            existing.dept_name = name
            existing.course_type = course_type
            session.add(existing)
        else:
            session.add(OfferingDeptClassification(
                offering_id=offering_id,
                dept_code=code,
                dept_name=name,
                course_type=course_type,
            ))


def _load_reviews(session: Session, path: Path, course_id: str, professor_id: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for r in data.get("reviews", []):
        text = (r.get("text") or "").strip()
        if not text:
            continue
        review_id = f"{path.stem}_{r['raw_index']}"
        if not session.get(Review, review_id):
            session.add(Review(
                id=review_id,
                course_id=course_id,
                professor_id=professor_id,
                term=_parse_term(r.get("semester_text", "")),
                raw_text=text,
            ))


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SourceAlignRec offline ingest — raw 데이터 적재")
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    init_db()
    load(Path(args.data_dir))


if __name__ == "__main__":
    main()
