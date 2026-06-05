"""BERT multi-head AttributeExtractor 학습.

학습 데이터: ReviewAttribute (LLM 추출 결과). sar-extract-attrs로 먼저 생성 필요.
미추출 리뷰는 전 속성 "없음" (class 0) 처리.
CrossEntropyLoss per head (head별 class 수는 ATTR_VALUES 기준), eval: per-attribute macro F1 (없음 클래스 포함).

출력: models/attr_extractor/{output}/model.pt

Usage:
    uv run sar-train-attr --output models/attr_extractor/bert_ax-encoder
    uv run sar-train-attr --model upskyy/bge-m3-korean --output models/attr_extractor/bert_bge-m3 --fp16
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewAttribute, ReviewAttributeLabel, ReviewClassification
from sourcealignrec.db.session import engine
from sourcealignrec.offline.extractor.attribute_extractor import (
    ATTR_NAMES, ATTR_VALUES, BERTMultiHeadAttributeModel, MAX_LENGTH,
    DEFAULT_ENCODER,
)

# 분류기 타입 → 해당 head 학습에 사용할 리뷰 결정
ATTR_TO_TYPE: dict[str, str] = {
    "grading_leniency":      "grading",
    "assignment_load":       "assignment",
    "team_project":          "assignment",
    "attendance_strictness": "attendance",
}
CLASSIFICATION_THRESHOLD = 0.5

EVAL_SIZE = 0.15
SEED = 42


class AttrDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[list[int]], tokenizer):
        self.encodings = tokenizer(
            texts, truncation=True, padding=True,
            max_length=MAX_LENGTH, return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx):
        return {k: v[idx] for k, v in self.encodings.items()}, self.labels[idx]


def load_data_from_labels() -> tuple[list[str], list[list[int]]]:
    """ReviewAttributeLabel (Claude 고품질 라벨) 기반 학습 데이터."""
    with Session(engine) as session:
        label_rows = session.exec(select(ReviewAttributeLabel)).all()
        review_map: dict[str, str] = {
            r.id: r.raw_text
            for r in session.exec(select(Review)).all()
        }

    attr_fields = ["grading_leniency", "assignment_load", "team_project", "attendance_strictness"]
    texts, labels = [], []
    skipped = 0
    for lbl in label_rows:
        text = review_map.get(lbl.review_id)
        if not text:
            skipped += 1
            continue
        row_labels: list[int] = []
        for attr in ATTR_NAMES:
            value = getattr(lbl, attr, "없음") or "없음"
            values = ATTR_VALUES[attr]
            idx = values.index(value) if value in values else 0
            row_labels.append(idx)
        texts.append(text)
        labels.append(row_labels)

    if skipped:
        print(f"  (텍스트 없음으로 제외: {skipped}개)")

    print(f"loaded {len(texts)} samples from ReviewAttributeLabel")
    for attr in attr_fields:
        count = sum(1 for lbl in label_rows if getattr(lbl, attr, "없음") != "없음")
        print(f"  {attr}: {count}개 유효 라벨")
    return texts, labels


def load_data() -> tuple[list[str], list[list[int]]]:
    """ReviewAttribute + ReviewClassification 기반 학습 데이터 구성.

    type별 스코핑: grading head는 grading-type 리뷰만, assignment head(s)는 assignment-type 리뷰만,
    attendance head는 attendance-type 리뷰만 유효 학습 샘플로 사용.
    타입 미해당 리뷰는 해당 head 학습에서 제외 (노이즈 억제).
    """
    with Session(engine) as session:
        attrs = session.exec(select(ReviewAttribute)).all()
        reviews = session.exec(select(Review.id, Review.raw_text)).all()
        classifications = session.exec(select(ReviewClassification)).all()

    review_map: dict[str, str] = {rid: text for rid, text in reviews}

    clf_map: dict[str, ReviewClassification] = {rc.review_id: rc for rc in classifications}

    attr_by_review: dict[str, dict[str, str]] = {}
    for ra in attrs:
        if ra.review_id not in attr_by_review:
            attr_by_review[ra.review_id] = {}
        attr_by_review[ra.review_id][ra.attribute_name] = ra.attribute_value

    # type별 유효 review_id 집합 (해당 타입 p-score >= threshold)
    # assignment_load와 team_project는 동일하게 assignment-type 리뷰를 사용
    eligible_by_attr: dict[str, set[str]] = {}
    for attr, type_name in ATTR_TO_TYPE.items():
        score_field = f"{type_name}_score"
        eligible_by_attr[attr] = {
            rid for rid, rc in clf_map.items()
            if getattr(rc, score_field, 0.0) >= CLASSIFICATION_THRESHOLD
        }

    # 하나라도 유효한 attr가 있는 리뷰만 포함
    eligible_reviews = {
        rid for attr_set in eligible_by_attr.values() for rid in attr_set
    } & set(review_map.keys())

    texts, labels = [], []
    for review_id in eligible_reviews:
        text = review_map[review_id]
        row_attrs = attr_by_review.get(review_id, {})
        row_labels: list[int] = []
        for attr in ATTR_NAMES:
            if review_id in eligible_by_attr[attr]:
                value = row_attrs.get(attr, "없음")
            else:
                value = "없음"  # 해당 type 미해당 리뷰 → 이 head 학습에서 없음 고정
            values = ATTR_VALUES[attr]
            idx = values.index(value) if value in values else 0
            row_labels.append(idx)
        texts.append(text)
        labels.append(row_labels)

    print(f"loaded {len(texts)} samples ({len(attr_by_review)} with extracted attrs)")
    for attr in ATTR_NAMES:
        print(f"  {attr}: {len(eligible_by_attr[attr])} eligible reviews")
    return texts, labels


def evaluate(model: BERTMultiHeadAttributeModel, loader: DataLoader, device: torch.device) -> dict:
    model.eval()
    all_preds: list[list[int]] = [[] for _ in ATTR_NAMES]
    all_targets: list[list[int]] = [[] for _ in ATTR_NAMES]

    with torch.no_grad():
        for batch_inputs, batch_labels in loader:
            batch_inputs = {k: v.to(device) for k, v in batch_inputs.items()}
            logits_list = model(**batch_inputs)
            for i, logits in enumerate(logits_list):
                preds = logits.argmax(dim=1).cpu().tolist()
                targets = batch_labels[:, i].tolist()
                all_preds[i].extend(preds)
                all_targets[i].extend(targets)

    per_attr: dict[str, float] = {}
    for i, attr in enumerate(ATTR_NAMES):
        per_attr[attr] = f1_score(all_targets[i], all_preds[i], average="macro", zero_division=0)
    macro = float(np.mean(list(per_attr.values())))
    return {"macro_f1": macro, "per_attr": per_attr}


def main() -> None:
    parser = argparse.ArgumentParser(description="AttributeExtractor BERT 학습")
    parser.add_argument("--model", default=DEFAULT_ENCODER)
    parser.add_argument("--output", required=True, help="출력 경로 (model.pt 저장)")
    parser.add_argument("--source", choices=["labels", "extracted"], default="labels",
                        help="학습 데이터 소스: labels=ReviewAttributeLabel(기본), extracted=ReviewAttribute(레거시)")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--patience", type=int, default=3, help="early stopping patience")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--fp16", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    texts, labels = load_data_from_labels() if args.source == "labels" else load_data()

    train_texts, eval_texts, train_labels, eval_labels = train_test_split(
        texts, labels, test_size=EVAL_SIZE, random_state=SEED,
    )
    print(f"train={len(train_texts)}, eval={len(eval_texts)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    train_ds = AttrDataset(train_texts, train_labels, tokenizer)
    eval_ds = AttrDataset(eval_texts, eval_labels, tokenizer)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    eval_loader = DataLoader(eval_ds, batch_size=args.batch_size)

    model = BERTMultiHeadAttributeModel(args.model).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=total_steps // 10, num_training_steps=total_steps,
    )
    # class_weight: minority class 패널티 보정
    loss_fns = []
    train_label_arr = np.array(train_labels)
    for i, attr in enumerate(ATTR_NAMES):
        n_classes = len(ATTR_VALUES[attr])
        col = train_label_arr[:, i]
        classes = np.arange(n_classes)
        weights = compute_class_weight("balanced", classes=classes, y=col)
        w = torch.tensor(weights, dtype=torch.float).to(device)
        loss_fns.append(nn.CrossEntropyLoss(weight=w))
        print(f"  {attr} weights: {dict(zip(ATTR_VALUES[attr], weights.round(2)))}")
    scaler = torch.cuda.amp.GradScaler() if args.fp16 and device.type == "cuda" else None

    best_f1 = 0.0
    no_improve = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for batch_inputs, batch_labels in train_loader:
            batch_inputs = {k: v.to(device) for k, v in batch_inputs.items()}
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad()

            if scaler:
                with torch.cuda.amp.autocast():
                    logits_list = model(**batch_inputs)
                    loss = sum(loss_fns[i](logits_list[i], batch_labels[:, i]) for i in range(len(ATTR_NAMES)))
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                logits_list = model(**batch_inputs)
                loss = sum(loss_fns[i](logits_list[i], batch_labels[:, i]) for i in range(len(ATTR_NAMES)))
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

            scheduler.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        metrics = evaluate(model, eval_loader, device)
        print(f"epoch {epoch}/{args.epochs}  loss={avg_loss:.4f}  macro_f1={metrics['macro_f1']:.4f}")
        print(f"  per-attr: {metrics['per_attr']}")

        if metrics["macro_f1"] > best_f1:
            best_f1 = metrics["macro_f1"]
            no_improve = 0
            torch.save(model.state_dict(), output_path / "model.pt")
        else:
            no_improve += 1
            if no_improve >= args.patience:
                print(f"early stopping (patience={args.patience})")
                break

    print(f"best macro_f1={best_f1:.4f}, model saved → {output_path}")


if __name__ == "__main__":
    main()
