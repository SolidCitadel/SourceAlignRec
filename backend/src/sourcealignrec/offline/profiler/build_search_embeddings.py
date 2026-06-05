"""벤치마크 ablation용 검색 변종 임베딩 빌더.

System A는 강의계획서 텍스트, System B는 강의계획서 + 대표 리뷰 raw concat을 검색
인덱스로 쓴다. 두 변종 모두 OfferingSearchEmbedding 테이블에 (offering_id, variant)
키로 저장한다.

C/D는 OfferingProfile.embedding을 그대로 쓰므로 본 CLI 대상이 아니다.

임베딩은 core.embedder(in-process) 단일 정본 — sar-embed-reviews / sar-build-profiles와
동일 임베딩 공간이 자동 보장됨.

Usage:
    uv run sar-build-search-embeddings --variant syllabus
    uv run sar-build-search-embeddings --variant syllabus_repreview
    uv run sar-build-search-embeddings --variant syllabus --overwrite
"""
from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from sourcealignrec.core import embedder
from sourcealignrec.db.models import (
    Offering,
    OfferingSearchEmbedding,
    RepresentativeReview,
    Review,
)
from sourcealignrec.db.session import engine, init_db

REP_REVIEW_K = 10  # rank 1..K (selector와 동일)
VARIANTS = ("syllabus", "syllabus_repreview")


def _build_syllabus_text(offering: Offering) -> str:
    """Offering의 강의계획서 텍스트를 검색용으로 직렬화.

    syllabus_text가 있으면 그대로 사용(legacy ingestion 경로). 없으면 구조화 필드를
    사람이 읽을 만한 한국어 블록으로 합친다.
    """
    if offering.syllabus_text:
        return offering.syllabus_text

    parts: list[str] = []
    if offering.course_overview:
        parts.append(f"[수업 개요]\n{offering.course_overview}")
    if offering.learning_objectives:
        parts.append(f"[학습 목표]\n{offering.learning_objectives}")

    weekly = json.loads(offering.weekly_topics or "[]")
    if weekly:
        parts.append("[주차별 주제] " + " / ".join(str(t) for t in weekly))

    eval_items = json.loads(offering.evaluation_items or "[]")
    if eval_items:
        eval_parts = []
        for e in eval_items:
            if isinstance(e, dict) and "item" in e and "ratio" in e:
                note = f" ({e['note']})" if e.get("note") else ""
                eval_parts.append(f"{e['item']} {e['ratio']}%{note}")
        if eval_parts:
            parts.append("[평가 항목] " + ", ".join(eval_parts))

    instr = json.loads(offering.instruction_type_ratios or "[]")
    if instr:
        instr_parts = []
        for it in instr:
            if isinstance(it, dict) and "type" in it and "ratio_pct" in it:
                instr_parts.append(f"{it['type']} {it['ratio_pct']}%")
        if instr_parts:
            parts.append("[수업 형태] " + ", ".join(instr_parts))

    prereqs = json.loads(offering.prerequisite_courses or "[]")
    if prereqs:
        prereq_parts = []
        for p in prereqs:
            if isinstance(p, dict) and "name" in p:
                label = "필수" if p.get("required") else "권장"
                prereq_parts.append(f"{p['name']}({label})")
        if prereq_parts:
            parts.append("[선수과목] " + ", ".join(prereq_parts))

    return "\n\n".join(parts)


def _load_rep_reviews(session: Session) -> dict[tuple[str, str], list[str]]:
    rows = session.exec(
        select(
            RepresentativeReview.course_id,
            RepresentativeReview.professor_id,
            Review.raw_text,
            RepresentativeReview.rank,
        )
        .join(Review, RepresentativeReview.review_id == Review.id)
        .where(RepresentativeReview.rank <= REP_REVIEW_K)
        .order_by(
            RepresentativeReview.course_id,
            RepresentativeReview.professor_id,
            RepresentativeReview.rank,
        )
    ).all()
    out: dict[tuple[str, str], list[str]] = {}
    for course_id, professor_id, raw_text, _ in rows:
        out.setdefault((course_id, professor_id), []).append(raw_text)
    return out


def _build_text(
    variant: str,
    offering: Offering,
    rep_reviews: dict[tuple[str, str], list[str]],
) -> str:
    syllabus = _build_syllabus_text(offering)
    if variant == "syllabus":
        return syllabus
    if variant == "syllabus_repreview":
        reviews = rep_reviews.get((offering.course_id, offering.professor_id), [])
        if not reviews:
            return syllabus
        review_block = "\n".join(f"- {r}" for r in reviews)
        return f"{syllabus}\n\n[수강생 강의평]\n{review_block}"
    raise ValueError(f"unknown variant: {variant}")


def _embed(text: str) -> list[float]:
    return embedder.embed(text)


def run(variant: str, overwrite: bool) -> None:
    if variant not in VARIANTS:
        raise SystemExit(f"variant는 {VARIANTS} 중 하나여야 함")

    print(f"variant: {variant}  |  임베딩: {embedder.MODEL_NAME}")

    with Session(engine) as session:
        existing_ids = set(
            session.exec(
                select(OfferingSearchEmbedding.offering_id).where(
                    OfferingSearchEmbedding.variant == variant
                )
            ).all()
        )
        if overwrite and existing_ids:
            existing_rows = session.exec(
                select(OfferingSearchEmbedding).where(
                    OfferingSearchEmbedding.variant == variant
                )
            ).all()
            for row in existing_rows:
                session.delete(row)
            session.commit()
            print(f"기존 {variant} 임베딩 {len(existing_ids)}개 삭제 완료")
            existing_ids = set()

        offerings = session.exec(select(Offering)).all()
        targets = [o for o in offerings if o.id not in existing_ids]
        print(f"처리 대상 Offering: {len(targets)}개 (skip={len(existing_ids)})")

        rep_reviews = _load_rep_reviews(session) if variant == "syllabus_repreview" else {}

        saved = 0
        for i, offering in enumerate(targets, 1):
            text = _build_text(variant, offering, rep_reviews)
            if not text.strip():
                print(f"  [{i}/{len(targets)}] {offering.id} - 빈 텍스트, 건너뜀")
                continue
            try:
                embedding = _embed(text)
            except Exception as e:
                print(f"  [{i}/{len(targets)}] {offering.id} 임베딩 오류 (건너뜀): {e}")
                continue

            session.add(OfferingSearchEmbedding(
                offering_id=offering.id,
                variant=variant,
                embedding=embedding,
            ))
            saved += 1
            if saved % 20 == 0:
                session.commit()
                print(f"  {i}/{len(targets)} 완료")

        session.commit()
        print(f"\n완료: {variant} 임베딩 {saved}개 저장")


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 변종 임베딩 빌더 (System A/B용)")
    parser.add_argument("--variant", required=True, choices=VARIANTS,
                        help="syllabus (System A) | syllabus_repreview (System B)")
    parser.add_argument("--overwrite", action="store_true",
                        help=f"기존 (offering, {VARIANTS}) 임베딩 삭제 후 재생성")
    args = parser.parse_args()

    init_db()
    run(args.variant, args.overwrite)


if __name__ == "__main__":
    main()
