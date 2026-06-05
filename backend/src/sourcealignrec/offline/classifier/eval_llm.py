"""LLM ReviewClassifier eval — eval set 기준 macro F1 측정.

Usage:
    uv run sar-eval-llm --model groq/qwen3-32b
    uv run sar-eval-llm --model cerebras/llama3.1-8b --delay 2.0
"""
from __future__ import annotations

import argparse

import numpy as np
from sklearn.metrics import f1_score

from sourcealignrec.offline.classifier.review_classifier import LLMReviewClassifier
from sourcealignrec.offline.classifier.train_bert import LABELS, load_data


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM zero-shot ReviewClassifier eval")
    parser.add_argument("--model", default="groq/qwen3-32b")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    classifier = LLMReviewClassifier(args.model, delay=args.delay)
    print(f"모델: {args.model}")

    _, _, eval_texts, eval_labels = load_data()
    print(f"eval set: {len(eval_texts)}개")

    preds: list[list[int]] = []
    for i, text in enumerate(eval_texts, 1):
        scores = classifier.classify(text)
        preds.append([1 if scores[t] >= 0.5 else 0 for t in LABELS])
        if i % 10 == 0:
            print(f"  {i}/{len(eval_texts)} 완료")

    all_preds = np.array(preds)
    all_targets = np.array(eval_labels)
    macro_f1 = f1_score(all_targets, all_preds, average="macro", zero_division=0)
    per_label = f1_score(all_targets, all_preds, average=None, zero_division=0)

    print(f"\n{'─' * 40}")
    print(f"macro F1 : {macro_f1:.4f}")
    print("per-label:")
    for label, score in zip(LABELS, per_label):
        print(f"  {label:<12} {score:.3f}")


if __name__ == "__main__":
    main()
