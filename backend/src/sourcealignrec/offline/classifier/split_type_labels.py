"""ReviewTypeLabel train/eval split 고정 — sar-split-type-labels CLI.

최초 1회만 실행. stratified sampling으로 eval set을 뽑아 DB에 영구 마킹.
이후 모든 학습은 split='eval' 행을 eval set으로 사용해 일관된 비교 보장.

Usage:
    uv run sar-split-type-labels --eval-size 100
    uv run sar-split-type-labels --eval-size 100 --force  # 기존 split 초기화 후 재지정
"""
from __future__ import annotations

import argparse

import numpy as np
from iterstrat.ml_stratifiers import MultilabelStratifiedShuffleSplit
from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db

LABELS = ["grading", "exam", "assignment", "attendance", "teaching", "topic", "professor"]
SEED = 42


def run(eval_size: int = 100, force: bool = False) -> None:
    with Session(engine) as session:
        already = session.exec(
            select(ReviewTypeLabel).where(ReviewTypeLabel.split != None)  # noqa: E711
        ).all()

        if already and not force:
            n_eval = sum(1 for r in already if r.split == "eval")
            n_train = sum(1 for r in already if r.split == "train")
            print(f"이미 split 지정됨: train={n_train}, eval={n_eval}")
            print("재지정하려면 --force 사용")
            return

        if already and force:
            for r in already:
                r.split = None
            session.commit()
            print("기존 split 초기화 완료")

        rows = session.exec(
            select(ReviewTypeLabel, Review.raw_text)
            .join(Review, ReviewTypeLabel.review_id == Review.id)
        ).all()

    if len(rows) < eval_size + 10:
        print(f"데이터 부족: {len(rows)}개 (eval {eval_size}개 지정 불가)")
        return

    label_matrix = np.array([[1.0 if getattr(tl, t) else 0.0 for t in LABELS] for tl, _ in rows])
    splitter = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=eval_size, random_state=SEED)
    train_idx, eval_idx = next(splitter.split(X=label_matrix, y=label_matrix))

    eval_ids = {rows[i][0].id for i in eval_idx}

    with Session(engine) as session:
        all_rows = session.exec(select(ReviewTypeLabel)).all()
        for r in all_rows:
            r.split = "eval" if r.id in eval_ids else "train"
        session.commit()

    print(f"split 완료: train={len(train_idx)}, eval={len(eval_idx)}")
    print(f"  eval set은 고정됩니다. 이후 라벨 추가분은 자동으로 train으로 들어갑니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReviewTypeLabel train/eval split 고정")
    parser.add_argument("--eval-size", type=int, default=100)
    parser.add_argument("--force", action="store_true", help="기존 split 초기화 후 재지정")
    args = parser.parse_args()

    init_db()
    run(args.eval_size, args.force)


if __name__ == "__main__":
    main()
