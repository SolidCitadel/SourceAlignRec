"""BERT multi-label ReviewClassifier 학습.

eval set 50개 고정 (stratified), BCEWithLogitsLoss, macro F1 평가.
출력 경로 컨벤션: models/review_classifier/bert_{backbone-short}_{n_train}

Usage:
    uv run sar-train-bert --output models/review_classifier/bert_ax-encoder_500
    uv run sar-train-bert --model upskyy/bge-m3-korean --fp16 --max-train 100 --output models/review_classifier/bert_bge-m3_100
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine

LABELS = ["grading", "exam", "assignment", "attendance", "teaching", "topic", "professor"]
DEFAULT_BACKBONE = "skt/A.X-Encoder-base"
SEED = 42
MAX_LENGTH = 256


class ReviewDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[list[float]], tokenizer, max_length: int = MAX_LENGTH):
        self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=max_length, return_tensors="pt")
        self.labels = torch.tensor(labels, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx):
        return {key: val[idx] for key, val in self.encodings.items()}, self.labels[idx]


def load_data() -> tuple[list[str], list[list[float]], list[str], list[list[float]]]:
    """DB에서 split 컬럼 기준으로 train/eval 로드. split=None이면 전부 train으로 사용."""
    with Session(engine) as s:
        rows = s.exec(
            select(ReviewTypeLabel, Review.raw_text)
            .join(Review, ReviewTypeLabel.review_id == Review.id)
        ).all()

    has_split = any(tl.split is not None for tl, _ in rows)
    train_texts, train_labels, eval_texts, eval_labels = [], [], [], []

    for tl, text in rows:
        label = [1.0 if getattr(tl, t) else 0.0 for t in LABELS]
        if has_split and tl.split == "eval":
            eval_texts.append(text)
            eval_labels.append(label)
        else:
            train_texts.append(text)
            train_labels.append(label)

    if has_split:
        print(f"DB split 사용: train={len(train_texts)}, eval={len(eval_texts)}")
    else:
        print(f"split 미지정 — 전체 {len(train_texts)}개를 train으로 사용 (sar-split-type-labels 실행 권장)")

    return train_texts, train_labels, eval_texts, eval_labels


def evaluate(model, loader, device) -> dict:
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for batch_inputs, batch_labels in loader:
            batch_inputs = {k: v.to(device) for k, v in batch_inputs.items()}
            logits = model(**batch_inputs).logits
            preds = (torch.sigmoid(logits) > 0.5).cpu().numpy()
            all_preds.append(preds)
            all_targets.append(batch_labels.numpy())
    all_preds = np.vstack(all_preds)
    all_targets = np.vstack(all_targets)
    macro_f1 = f1_score(all_targets, all_preds, average="macro", zero_division=0)
    per_label = f1_score(all_targets, all_preds, average=None, zero_division=0)
    return {"macro_f1": macro_f1, "per_label": dict(zip(LABELS, per_label.tolist()))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_BACKBONE, help="HuggingFace backbone model")
    parser.add_argument("--output", required=True, help="output dir, e.g. models/review_classifier/bert_ax-encoder_100")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--patience", type=int, default=3, help="early stopping patience")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--fp16", action="store_true", help="mixed precision training (for large models)")
    parser.add_argument("--max-train", type=int, default=None, help="cap train samples (e.g. 100)")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    train_texts, train_labels, eval_texts, eval_labels = load_data()

    if not eval_texts:
        print("eval set 없음 — sar-split-type-labels를 먼저 실행하세요.")
        return

    if args.max_train is not None and args.max_train < len(train_texts):
        rng = random.Random(SEED)
        indices = rng.sample(range(len(train_texts)), args.max_train)
        train_texts = [train_texts[i] for i in indices]
        train_labels = [train_labels[i] for i in indices]

    print(f"train={len(train_texts)}, eval={len(eval_texts)}")

    backbone = args.model
    tokenizer = AutoTokenizer.from_pretrained(backbone)
    train_ds = ReviewDataset(train_texts, train_labels, tokenizer)
    eval_ds = ReviewDataset(eval_texts, eval_labels, tokenizer)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    eval_loader = DataLoader(eval_ds, batch_size=args.batch_size)

    config = AutoConfig.from_pretrained(backbone, num_labels=len(LABELS), problem_type="multi_label_classification")
    if hasattr(config, "reference_compile"):
        config.reference_compile = False  # ModernBERT: Triton not available on Windows
    model = AutoModelForSequenceClassification.from_pretrained(backbone, config=config).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=total_steps // 10, num_training_steps=total_steps)
    label_matrix = torch.tensor(train_labels, dtype=torch.float32)
    pos_counts = label_matrix.sum(0).clamp(min=1)
    pos_weight = ((len(train_labels) - pos_counts) / pos_counts).to(device)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
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
                    logits = model(**batch_inputs).logits
                    loss = loss_fn(logits, batch_labels)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                logits = model(**batch_inputs).logits
                loss = loss_fn(logits, batch_labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        metrics = evaluate(model, eval_loader, device)
        print(f"epoch {epoch}/{args.epochs}  loss={avg_loss:.4f}  macro_f1={metrics['macro_f1']:.4f}")
        print(f"  per-label: {metrics['per_label']}")

        if metrics["macro_f1"] > best_f1:
            best_f1 = metrics["macro_f1"]
            no_improve = 0
            model.save_pretrained(str(output_path))
            tokenizer.save_pretrained(str(output_path))
        else:
            no_improve += 1
            if no_improve >= args.patience:
                print(f"early stopping at epoch {epoch} (patience={args.patience})")
                break

    print(f"best macro_f1={best_f1:.4f}, model saved → {output_path}")