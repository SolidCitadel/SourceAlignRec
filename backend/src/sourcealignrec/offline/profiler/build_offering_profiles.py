"""Offering별 강의계획서 + 대표 리뷰 → LLM 요약 → OfferingProfile 저장.

- 대표 리뷰 있음: 강의계획서 + Course 대표 리뷰 → LLM 요약
- 대표 리뷰 없음: 강의계획서 + Professor 대표 리뷰 → LLM 요약 (타 과목 강의평으로 보완)
이 문서가 pgvector 유사도 검색의 기준이자 Online 단계에서 LLM에게 전달되는 컨텍스트다.

임베딩은 core.embedder(in-process) 단일 정본 — sar-embed-reviews와 동일 임베딩 공간이 자동 보장됨.

Usage:
    uv run sar-build-profiles --model groq/qwen3-32b
    uv run sar-build-profiles --model groq/qwen3-32b --sample 5
    uv run sar-build-profiles --model groq/qwen3-32b --overwrite
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from sourcealignrec.core import embedder
from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.db.models import (
    Course, Offering, OfferingProfile,
    Professor, ProfessorRepresentativeReview,
    RepresentativeReview, Review,
)
from sourcealignrec.db.session import engine, init_db

REQUIRED_FIELDS = ["topic", "format", "evaluation", "reviews_summary", "caveats"]

SYSTEM_PROMPT = """\
당신은 한국 대학 강의 정보를 학생에게 제공하는 전문가입니다. 한 과목의 강의계획서와 수강생 강의평을 보고, 수강을 고려하는 학생이 결정에 필요한 핵심 정보를 정리합니다.

## 출력 형식 (JSON 객체, 다른 텍스트 없이 JSON만)

{
  "topic": "무엇을 배우는 과목인지, 선수지식. 도메인 기술 키워드는 강의계획서 원본 표현 그대로. 1-3문장.",
  "format": "강의 진행 방식 (강의식·실습·팀프로젝트 비중 등), 수업 구성. 평가 비중 작성 금지. 1-3문장.",
  "evaluation": "평가 항목과 비율(수치 그대로), 과제·시험 부담. 강의 진행 방식 작성 금지. 1-3문장.",
  "reviews_summary": "위 3개 필드에 통합되지 않은 정성적 강의평(교수 강의력·분위기·소통·학습 부담 체감 등). 핵심 주장은 '원문에 가까운 표현'으로 인용해 포함(예: '교수님이 직접 코드 리뷰를 해준다', '출석이 사실상 전부다'). 강의평 없으면 빈 문자열.",
  "caveats": "강의계획서와 실제가 명백히 충돌할 때만. \\"강의계획서에는 X라고 하지만 실제로는 Y\\"의 비교 형식. 일치·단순 보충은 caveats 아님. 충돌 없으면 빈 문자열."
}

## 강의평 활용 원칙

- 강의계획서에 없는 보충 정보(예: 실제 학습 비중·과제 양 체감)는 해당 출력 필드(topic/format/evaluation)에 source 표시 없이 자연스럽게 통합.
- 정성적 정보(교수 강의력·분위기·만족도)만 reviews_summary로.
- 강의계획서와 명백히 충돌할 때만 caveats로 명시 비교.

## 문체·표현 규칙 (모든 profile 일관)

- 합쇼체 (-습니다/-ㅂ니다 종결): "다룹니다", "구성됩니다", "평가됩니다"
- 각 필드 1-3 짧은 문장. 줄바꿈 없이.
- 수치(평가 비율 등)는 강의계획서 원본 그대로 유지. 반올림·축약 금지.
- 사실 기반. 추측·주관적 평가 표현(매우·정말·아주 등) 금지.
- 분반(같은 과목 다른 교수)이면 evaluation·reviews_summary·caveats에 이 분반 고유 특성 명확히.
- 강의평이 없으면 reviews_summary, caveats는 빈 문자열("").

## 출력 예시 (참고용 — 실제 입력 데이터에 맞게 작성)

{
  "topic": "관계형 데이터베이스의 설계와 구현을 학습하는 과목입니다. ER 모델, 관계 대수, SQL, 정규화 이론, 트랜잭션 관리를 다루며, 분산 시스템·클라우드 컴퓨팅 등 후속 과목의 기반이 됩니다.",
  "format": "강의식 60%, SQL 실습 40%로 구성됩니다. 매주 실습 과제가 주어지며, 학기 말 팀 프로젝트로 데이터베이스 설계·구현을 수행합니다.",
  "evaluation": "중간고사 30%, 기말고사 30%, 과제 25%, 팀프로젝트 15%로 평가됩니다. 강의평에 따르면 시험은 SQL 쿼리 작성과 정규화 문제 중심으로 출제됩니다.",
  "reviews_summary": "'SQL을 직접 짜보는 실습이 많아 손에 익는다'는 평이 다수이며, '과제가 매주 나오지만 따라가면 시험 대비가 된다'는 의견도 많습니다. '교수님 질문 응답이 빠르고 친절하다'는 평가도 있습니다.",
  "caveats": "강의계획서에는 출석이 5%라고 하지만 실제로는 결석 누적 시 감점 폭이 크다는 강의평이 다수 있습니다."
}

JSON만 출력. 코드블록·설명·마크다운 없음.\
"""


def _check_quality(profile_dict: dict, has_reviews: bool) -> list[str]:
    """JSON schema 품질 체크. 문제 항목 리스트 반환 (빈 리스트면 통과)."""
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in profile_dict:
            issues.append(f"{field} 필드 누락")
            continue
        if not isinstance(profile_dict[field], str):
            issues.append(f"{field} 타입 오류 (str 필요, {type(profile_dict[field]).__name__} 받음)")
    # 필수 본문(topic/format/evaluation)은 비어있으면 안 됨
    for field in ("topic", "format", "evaluation"):
        if profile_dict.get(field, "").strip() == "":
            issues.append(f"{field} 비어있음 (필수)")
    if has_reviews and profile_dict.get("reviews_summary", "").strip() == "":
        issues.append("reviews_summary 비어있음 (강의평 있음에도)")
    return issues


def _assemble_text(profile_dict: dict, course_name: str, professor_name: str | None, term: str) -> str:
    """JSON dict + 메타 → 임베딩·LLM 컨텍스트용 자연어 텍스트.

    헤더에 과목명·교수명·학기를 prominent하게 두어 분반 변별 신호를 강화.
    빈 필드(reviews_summary, caveats)는 섹션 자체를 생략.
    """
    prof_part = f"{professor_name}, " if professor_name else ""
    parts = [f"[과목] {course_name} ({prof_part}{term})", ""]
    section_map = [
        ("[과목 특성]", "topic"),
        ("[수업 방식]", "format"),
        ("[평가/부담]", "evaluation"),
        ("[수강 후기]", "reviews_summary"),
        ("[주의사항]", "caveats"),
    ]
    for header, key in section_map:
        value = (profile_dict.get(key) or "").strip()
        if not value:
            continue
        parts.append(header)
        parts.append(value)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _build_context(
    offering: Offering,
    course: Course,
    professor: Professor | None,
    reviews: list[str],
    professor_fallback: bool = False,
) -> str:
    """입력을 source(과목 정보 / 강의계획서 / 강의평) 단위로 그루핑."""
    parts: list[str] = []

    # === 과목 정보 (메타) ===
    parts.append("# 과목 정보")
    parts.append(f"- 과목명: {course.name}")
    if professor:
        parts.append(f"- 교강사: {professor.name}")
    parts.append(f"- 학기: {offering.term}")

    # === 강의계획서 (구조화 필드 묶음) ===
    syllabus_lines: list[str] = []

    if offering.course_overview:
        syllabus_lines.append(f"[수업 개요]\n{offering.course_overview}")

    if offering.learning_objectives:
        syllabus_lines.append(f"[학습 목표]\n{offering.learning_objectives}")

    prereqs = json.loads(offering.prerequisite_courses or "[]")
    if prereqs:
        prereq_parts = []
        for p in prereqs:
            if isinstance(p, dict) and "name" in p:
                label = "필수" if p.get("required") else "권장"
                prereq_parts.append(f"{p['name']}({label})")
        if prereq_parts:
            syllabus_lines.append(f"[선수과목] {', '.join(prereq_parts)}")

    weekly = json.loads(offering.weekly_topics or "[]")
    if weekly:
        topics_str = " / ".join(str(t) for t in weekly)
        syllabus_lines.append(f"[주차별 주제] {topics_str}")

    instr = json.loads(offering.instruction_type_ratios or "[]")
    if instr:
        instr_parts = []
        for it in instr:
            if isinstance(it, dict) and "type" in it and "ratio_pct" in it:
                instr_parts.append(f"{it['type']} {it['ratio_pct']}%")
        if instr_parts:
            syllabus_lines.append(f"[수업 형태] {', '.join(instr_parts)}")

    eval_items = json.loads(offering.evaluation_items or "[]")
    if eval_items:
        eval_parts = []
        for e in eval_items:
            if isinstance(e, dict) and "item" in e and "ratio" in e:
                note = f" ({e['note']})" if e.get("note") else ""
                eval_parts.append(f"{e['item']} {e['ratio']}%{note}")
        if eval_parts:
            syllabus_lines.append(f"[평가 항목] {', '.join(eval_parts)}")

    if syllabus_lines:
        parts.append("\n# 강의계획서")
        parts.extend(syllabus_lines)

    # === 강의평 ===
    if reviews:
        if professor_fallback:
            parts.append("\n# 강의평 (※ 이 교수의 타 과목 강의평 — 이 과목 직접 강의평 없음)")
        else:
            parts.append("\n# 강의평")
        for r in reviews:
            parts.append(f"- {r}")

    return "\n".join(parts)


def _call_llm(context: str, model_id: str) -> dict:
    """LLM에 JSON 응답 요청 → dict로 파싱. 실패 시 ValueError."""
    response = get_pool().chat(
        model_id,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    text = (response.choices[0].message.content or "").strip()
    # thinking 모델의 <think>...</think> 블록 제거
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
    # 코드 펜스(```json ... ```)가 들어오면 제거
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM JSON 파싱 실패: {e}. 원문(앞 200자): {text[:200]}") from e


def _call_embed(text: str) -> list[float]:
    return embedder.embed(text)


def run(
    model_id: str,
    overwrite: bool = False,
    sample: int | None = None,
) -> None:
    print(f"LLM: {model_id}  |  임베딩: {embedder.MODEL_NAME}")

    with Session(engine) as session:
        if overwrite:
            existing = session.exec(select(OfferingProfile)).all()
            for s in existing:
                session.delete(s)
            session.commit()
            print("기존 OfferingProfile 삭제 완료")
            done_ids: set[str] = set()
        else:
            done_ids = set(session.exec(select(OfferingProfile.offering_id)).all())

        offerings = session.exec(select(Offering)).all()
        offerings = [o for o in offerings if o.id not in done_ids]
        if sample is not None:
            offerings = offerings[:sample]
        print(f"처리 대상 Offering: {len(offerings)}개{f' (sample={sample})' if sample else ''}")

        course_map: dict[str, Course] = {
            c.id: c for c in session.exec(select(Course)).all()
        }
        prof_map: dict[str, Professor] = {
            p.id: p for p in session.exec(select(Professor)).all()
        }
        rep_rows = session.exec(
            select(RepresentativeReview.course_id, RepresentativeReview.professor_id,
                   Review.raw_text, RepresentativeReview.rank)
            .join(Review, RepresentativeReview.review_id == Review.id)
            .order_by(RepresentativeReview.course_id, RepresentativeReview.professor_id,
                      RepresentativeReview.rank)
        ).all()

        rep_reviews: dict[tuple[str, str], list[str]] = {}
        for course_id, professor_id, raw_text, _ in rep_rows:
            key = (course_id, professor_id)
            rep_reviews.setdefault(key, []).append(raw_text)

        prof_rep_rows = session.exec(
            select(ProfessorRepresentativeReview.professor_id, Review.raw_text,
                   ProfessorRepresentativeReview.rank)
            .join(Review, ProfessorRepresentativeReview.review_id == Review.id)
            .order_by(ProfessorRepresentativeReview.professor_id,
                      ProfessorRepresentativeReview.rank)
        ).all()

        prof_rep_reviews: dict[str, list[str]] = {}
        for professor_id, raw_text, _ in prof_rep_rows:
            prof_rep_reviews.setdefault(professor_id, []).append(raw_text)

        saved = 0
        for i, offering in enumerate(offerings, 1):
            course = course_map.get(offering.course_id)
            professor = prof_map.get(offering.professor_id)
            if not course:
                print(f"  [{i}/{len(offerings)}] {offering.id} - Course 없음. 건너뜀.")
                continue

            course_reviews = rep_reviews.get((offering.course_id, offering.professor_id), [])
            professor_fallback = not course_reviews
            reviews = course_reviews if course_reviews else prof_rep_reviews.get(offering.professor_id, [])
            context = _build_context(offering, course, professor, reviews, professor_fallback)

            try:
                profile_dict = _call_llm(context, model_id)
                profile_text = _assemble_text(
                    profile_dict,
                    course_name=course.name,
                    professor_name=professor.name if professor else None,
                    term=offering.term,
                )
                embedding = _call_embed(profile_text)
            except Exception as e:
                print(f"  [{i}/{len(offerings)}] {offering.id} 오류 (건너뜀): {e}")
                continue

            issues = _check_quality(profile_dict, bool(reviews))
            if issues:
                print(f"  [{i}/{len(offerings)}] {offering.id} 품질 경고: {', '.join(issues)}")

            profile_json_str = json.dumps(profile_dict, ensure_ascii=False)
            # api-contract/offerings.md §1 reviewCount: profile 산출에 사용된 전체 리뷰 수.
            review_count = session.exec(
                select(func.count()).select_from(Review)
                .where(Review.course_id == offering.course_id)
                .where(Review.professor_id == offering.professor_id)
            ).one()
            updated_at = datetime.utcnow()

            existing = session.get(OfferingProfile, offering.id)
            if existing:
                existing.profile_json = profile_json_str
                existing.profile_text = profile_text
                existing.embedding = embedding
                existing.review_count = review_count
                existing.profile_updated_at = updated_at
                session.add(existing)
            else:
                session.add(OfferingProfile(
                    offering_id=offering.id,
                    profile_json=profile_json_str,
                    profile_text=profile_text,
                    embedding=embedding,
                    review_count=review_count,
                    profile_updated_at=updated_at,
                ))
            saved += 1

            if saved % 20 == 0:
                session.commit()
                print(f"  {i}/{len(offerings)} 완료")

        session.commit()
        print(f"\n완료: {saved}개 Offering Profile 저장")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offering Profile 생성 + 임베딩")
    parser.add_argument("--model", required=True, help="model-pool model_id (family: llm)")
    parser.add_argument("--sample", type=int, default=None, help="처리할 Offering 수 제한 (spot-check용)")
    parser.add_argument("--overwrite", action="store_true", help="기존 OfferingProfile 삭제 후 재생성")
    args = parser.parse_args()

    init_db()
    run(args.model, args.overwrite, args.sample)


if __name__ == "__main__":
    main()
