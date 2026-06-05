"""SetFit multi-label ReviewClassifier 학습.

DB의 review_label (source=llm or human) 을 사용해 upskyy/bge-m3-korean 를 fine-tune.
eval set 50개 고정 (stratified), 나머지를 train으로 사용.
학습 완료 후 모델을 로컬 경로에 저장.

Usage:
    uv run sar-train
    uv run sar-train --output models/setfit_500 --epochs 3
    uv run sar-train --max-train 100 --output models/setfit_100
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from datasets import Dataset
from iterstrat.ml_stratifiers import MultilabelStratifiedShuffleSplit
from setfit import SetFitModel, Trainer, TrainingArguments
from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine

LABELS = ["grading", "exam", "assignment", "attendance", "teaching", "topic", "professor"]
EVAL_SIZE = 50
SEED = 42


def load_dataset() -> Dataset:
    with Session(engine) as s:
        rows = s.exec(
            select(ReviewTypeLabel, Review.raw_text)
            .join(Review, ReviewTypeLabel.review_id == Review.id)
            .where(ReviewTypeLabel.is_noise == False)  # noqa: E712
        ).all()

    texts, labels = [], []
    for rl, text in rows:
        texts.append(text)
        labels.append([1.0 if getattr(rl, t) else 0.0 for t in LABELS])

    print(f"loaded {len(texts)} samples")
    return Dataset.from_dict({"text": texts, "label": labels})


def stratified_split(dataset: Dataset, eval_size: int = EVAL_SIZE) -> tuple[Dataset, Dataset]:
    label_matrix = np.array(dataset["label"])
    splitter = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=eval_size, random_state=SEED)
    train_idx, eval_idx = next(splitter.split(X=label_matrix, y=label_matrix))
    return dataset.select(train_idx.tolist()), dataset.select(eval_idx.tolist())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="models/review_classifier")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-train", type=int, default=None, help="cap train samples (e.g. 100 for few-shot condition)")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset()
    train_ds, eval_ds = stratified_split(dataset, eval_size=EVAL_SIZE)

    if args.max_train is not None and args.max_train < len(train_ds):
        rng = random.Random(SEED)
        indices = rng.sample(range(len(train_ds)), args.max_train)
        train_ds = train_ds.select(indices)

    print(f"train={len(train_ds)}, eval={len(eval_ds)}")

    model = SetFitModel.from_pretrained(
        "jhgan/ko-sroberta-multitask",
        multi_target_strategy="one-vs-rest",
        labels=LABELS,
    )

    training_args = TrainingArguments(
        output_dir=str(output_path),
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        seed=SEED,
        use_amp=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        metric="f1",
        metric_kwargs={"average": "macro"},
    )

    trainer.train()

    metrics = trainer.evaluate()
    print("eval metrics:", metrics)

    model.save_pretrained(str(output_path))
    print(f"model saved → {output_path}")
