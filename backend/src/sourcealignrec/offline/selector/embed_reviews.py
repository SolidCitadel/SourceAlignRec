"""리뷰 텍스트 임베딩 → Review.embedding 저장.

임베딩은 core.embedder(in-process) 정본 사용 — model-pool 임베딩 경로 폐기(rate limit 없음).

Usage:
    uv run sar-embed-reviews
    uv run sar-embed-reviews --overwrite
    uv run sar-embed-reviews --only-labeled
"""
from __future__ import annotations

import argparse

from sqlmodel import Session, select

from sourcealignrec.core import embedder
from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db


def run(batch_size: int = 100, overwrite: bool = False, only_labeled: bool = False) -> None:
    print(f"임베딩: {embedder.MODEL_NAME}  |  batch_size: {batch_size}  |  only_labeled: {only_labeled}")

    with Session(engine) as session:
        if only_labeled:
            labeled_ids = set(
                session.exec(select(ReviewTypeLabel.review_id)).all()
            )
            base = select(Review).where(Review.id.in_(labeled_ids))
        else:
            base = select(Review)

        if overwrite:
            reviews = session.exec(base).all()
        else:
            reviews = session.exec(
                base.where(Review.embedding == None)  # noqa: E711
            ).all()

        print(f"처리 대상: {len(reviews)}개 리뷰")
        if not reviews:
            print("모두 완료됨.")
            return

        saved = 0
        for i in range(0, len(reviews), batch_size):
            batch = reviews[i:i + batch_size]
            embeddings = embedder.embed_many([r.raw_text for r in batch])
            for review, emb in zip(batch, embeddings):
                review.embedding = emb
                session.add(review)
            session.commit()
            saved += len(batch)
            print(f"  {saved}/{len(reviews)} 완료")

    print(f"\n완료: {saved}개 Review.embedding 저장")


def main() -> None:
    parser = argparse.ArgumentParser(description="리뷰 임베딩 저장")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--only-labeled", action="store_true",
                        help="ReviewTypeLabel이 있는 리뷰만 임베딩 (gold label 모드용)")
    args = parser.parse_args()

    init_db()
    run(args.batch_size, args.overwrite, args.only_labeled)


if __name__ == "__main__":
    main()
