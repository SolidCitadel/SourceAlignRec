"""LLM / BERT AttributeExtractor → ReviewAttribute 저장 + OfferingAttribute 집계.

Usage:
    uv run sar-extract-attrs --impl llm --model groq/qwen3-32b
    uv run sar-extract-attrs --impl bert --model-path models/attr_extractor/bert_ax-encoder
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlmodel import Session, select

from sourcealignrec.db.models import (
    Offering,
    OfferingAttribute,
    Review,
    ReviewAttribute,
    ReviewAttributeExtraction,
    ReviewClassification,
)
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.candidates import eligible_attrs as _eligible_attrs  # 후보 정의 단일 출처
from sourcealignrec.offline.extractor.attribute_extractor import (
    DEFAULT_BERT_MODEL_PATH,
    AttributeExtractor,
    BERTAttributeExtractor,
    LLMAttributeExtractor,
)


def run(
    impl: str,
    model_id: str | None = None,
    model_path: str | None = None,
    threshold: float = 0.5,
    delay: float = 1.0,
    overwrite_attr: bool = False,
) -> None:
    extractor: AttributeExtractor
    if impl == "llm":
        if not model_id:
            raise ValueError("--impl llm 사용 시 --model 필요")
        extractor = LLMAttributeExtractor(model_id, delay)
        extractor_tag = f"llm:{model_id}"
    else:
        bert = BERTAttributeExtractor(model_path or DEFAULT_BERT_MODEL_PATH)
        extractor = bert
        extractor_tag = f"bert:{bert.model_path}"

    print(f"impl: {impl}  |  extractor: {extractor_tag}  |  threshold: {threshold}")

    with Session(engine) as session:
        rows = session.exec(
            select(ReviewClassification, Review.course_id, Review.professor_id, Review.raw_text)
            .join(Review, ReviewClassification.review_id == Review.id)
            .where(ReviewClassification.is_noise == False)  # noqa: E712
        ).all()

        if not rows:
            print("ReviewClassification 데이터 없음. sar-classify를 먼저 실행하세요.")
            return

        relevant = [
            (rc, course_id, professor_id, raw_text)
            for rc, course_id, professor_id, raw_text in rows
            if _eligible_attrs(rc, threshold)
        ]
        print(f"추출 대상: {len(relevant)}개 리뷰")

        if overwrite_attr:
            for r in session.exec(select(ReviewAttribute)).all():
                session.delete(r)
            for mk in session.exec(select(ReviewAttributeExtraction)).all():
                session.delete(mk)
            session.commit()

        # 처리 여부 정본 = 마커(ReviewAttributeExtraction). 결과 0건 후보도 마커가 있으면 처리됨.
        done_review_ids: set[str] = (
            {str(r) for r in session.exec(select(ReviewAttributeExtraction.review_id)).all()}
            if not overwrite_attr else set()
        )

        attr_votes: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        saved_review_attrs = 0

        for i, (rc, course_id, professor_id, raw_text) in enumerate(relevant, 1):
            if rc.review_id in done_review_ids:
                attr_votes_from_db = session.exec(
                    select(ReviewAttribute)
                    .where(ReviewAttribute.review_id == rc.review_id)
                ).all()
                for ra in attr_votes_from_db:
                    attr_votes[(course_id, professor_id)][ra.attribute_name].append(ra.attribute_value)
                continue

            eligible = _eligible_attrs(rc, threshold)
            try:
                result = extractor.extract(raw_text, target_attrs=sorted(eligible))
            except Exception as e:
                print(f"  [{i}/{len(relevant)}] 오류 (건너뜀): {e}")
                continue

            for attr_name, value in result.items():
                session.add(ReviewAttribute(
                    review_id=rc.review_id,
                    attribute_name=attr_name,
                    attribute_value=value,
                    extractor=extractor_tag,
                    extracted_at=datetime.now(UTC),
                ))
                attr_votes[(course_id, professor_id)][attr_name].append(value)
                saved_review_attrs += 1

            # 처리 마커 — 결과가 비어도 기록(처리됨 ≠ 결과 있음).
            session.add(ReviewAttributeExtraction(
                review_id=rc.review_id,
                extracted_at=datetime.now(UTC),
                extractor=extractor_tag,
            ))

            if i % 50 == 0:
                session.commit()
                print(f"  {i}/{len(relevant)} 완료")

        session.commit()
        print(f"ReviewAttribute 저장: {saved_review_attrs}개")

        _aggregate(session, attr_votes)


def _aggregate(session: Session, attr_votes: dict[tuple[str, str], dict[str, list[str]]]) -> None:
    """다수결로 Attribute 대표값 선정 → OfferingAttribute 저장."""
    offerings = session.exec(select(Offering)).all()
    saved = 0
    for offering in offerings:
        key = (offering.course_id, offering.professor_id)
        for attr_name, values in attr_votes.get(key, {}).items():
            if not values:
                continue
            winner = Counter(values).most_common(1)[0][0]
            existing = session.exec(
                select(OfferingAttribute)
                .where(OfferingAttribute.offering_id == offering.id)
                .where(OfferingAttribute.attribute_name == attr_name)
                .where(OfferingAttribute.source == "review")
            ).first()
            if existing:
                existing.attribute_value = winner
                session.add(existing)
            else:
                session.add(OfferingAttribute(
                    offering_id=offering.id,
                    attribute_name=attr_name,
                    attribute_value=winner,
                    source="review",
                ))
            saved += 1

    session.commit()
    print(f"OfferingAttribute 집계 완료: {saved}개 저장/갱신")


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute 추출 → ReviewAttribute + OfferingAttribute 저장")
    parser.add_argument("--impl", choices=["llm", "bert"], default="bert")
    parser.add_argument("--model", default=None, help="LLM model_id (--impl llm 필수)")
    parser.add_argument("--model-path", default=None, help="BERT 모델 경로 (--impl bert 필수)")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--overwrite-attr", action="store_true", help="기존 ReviewAttribute 삭제 후 재추출")
    args = parser.parse_args()

    init_db()
    run(args.impl, args.model, args.model_path, args.threshold, args.delay, args.overwrite_attr)


if __name__ == "__main__":
    main()
