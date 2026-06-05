"""BERT ReviewClassifier로 전체 리뷰 추론 → ReviewClassification 저장.

Usage:
    uv run sar-classify-reviews
    uv run sar-classify-reviews --model-path models/review_classifier/bert_ax-encoder_500
    uv run sar-classify-reviews --batch-size 32 --overwrite
"""
from __future__ import annotations

import argparse

from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewClassification
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.classifier.review_classifier import BERTReviewClassifier
from sourcealignrec.offline.classifier.train_bert import LABELS

DEFAULT_MODEL_PATH = "models/review_classifier/bert_ax-encoder_950_pw"


def run(model_path: str = DEFAULT_MODEL_PATH, batch_size: int = 32, overwrite: bool = False, limit: int | None = None) -> None:
    classifier = BERTReviewClassifier(model_path, batch_size)
    print(f"device: {classifier._device}  |  model: {model_path}")

    with Session(engine) as session:
        reviews = session.exec(select(Review)).all()

        if not overwrite:
            done_ids: set[str] = set(
                session.exec(select(ReviewClassification.review_id)).all()
            )
            pending = [r for r in reviews if r.id not in done_ids]
        else:
            pending = list(reviews)

        if limit is not None:
            pending = pending[:limit]

        print(f"전체: {len(reviews)}  |  처리 대상: {len(pending)}")
        if not pending:
            print("모두 완료됨.")
            return

        saved = 0
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i + batch_size]
            scores_list = classifier.classify_batch([r.raw_text for r in batch])

            for review, scores in zip(batch, scores_list):
                is_noise = all(v < 0.5 for v in scores.values())
                session.add(ReviewClassification(
                    review_id=review.id,
                    **{f"{label}_score": scores[label] for label in LABELS},
                    is_noise=is_noise,
                    model_path=model_path,
                ))
                saved += 1

            session.commit()
            print(f"  {min(i + batch_size, len(pending))}/{len(pending)} 완료")

    print(f"\n완료: {saved}개 ReviewClassification 저장")


def main() -> None:
    parser = argparse.ArgumentParser(description="BERT ReviewClassifier 전체 추론")
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    init_db()
    run(args.model_path, args.batch_size, args.overwrite, args.limit)


if __name__ == "__main__":
    main()
