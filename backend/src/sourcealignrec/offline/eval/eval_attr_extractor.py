"""AttributeExtractor eval — ReviewAttributeLabel.split='eval' 기준 macro F1 측정.

eval split(SEED=42, 98개)에 LLM 또는 BERT를 실행해 per-attribute macro F1를 측정한다.
결과는 BenchmarkRun/BenchmarkResult(target=attr_eval_split)에 저장 → 중단 후 재실행 가능.

※ 이 스크립트는 eval split(학습 모니터링용 랜덤 holdout)을 대상으로 한다.
   엣지케이스 역량 측정은 sar-benchmark-attr-extraction 을 사용한다.

Usage:
    uv run sar-eval-attr --model groq/qwen3-32b
    uv run sar-eval-attr --model groq/gpt-oss-120b --delay 8
    uv run sar-eval-attr --variant bert --model-path models/attr_extractor/roberta_large --encoder klue/roberta-large
    uv run sar-eval-attr --show-run <run_id>
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import numpy as np
from sklearn.metrics import f1_score
from sqlmodel import Session, select

from sourcealignrec.db.models import BenchmarkCase, BenchmarkResult, BenchmarkRun, Review, ReviewAttributeLabel
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.extractor.attribute_extractor import (
    ATTR_NAMES, ATTR_VALUES, BERTAttributeExtractor, DEFAULT_BERT_MODEL_PATH,
    DEFAULT_ENCODER, LLMAttributeExtractor,
)

TARGET = "attr_eval_split"


def _compute_f1(run_id: int, session: Session) -> None:
    run = session.get(BenchmarkRun, run_id)
    results = session.exec(
        select(BenchmarkResult).where(BenchmarkResult.run_id == run_id)
    ).all()
    label_map = {
        lbl.review_id: lbl
        for lbl in session.exec(
            select(ReviewAttributeLabel).where(ReviewAttributeLabel.split == "eval")
        ).all()
    }

    all_preds: list[list[int]] = [[] for _ in ATTR_NAMES]
    all_targets: list[list[int]] = [[] for _ in ATTR_NAMES]
    for res in results:
        lbl = label_map.get(res.case_id)
        if not lbl:
            continue
        pred_dict = json.loads(res.pred_attrs or "{}")
        for j, attr in enumerate(ATTR_NAMES):
            gold_val = getattr(lbl, attr, "없음") or "없음"
            pred_val = pred_dict.get(attr, "없음") or "없음"
            values = ATTR_VALUES[attr]
            all_targets[j].append(values.index(gold_val) if gold_val in values else 0)
            all_preds[j].append(values.index(pred_val) if pred_val in values else 0)

    per_attr = {
        attr: f1_score(all_targets[j], all_preds[j], average="macro", zero_division=0)
        for j, attr in enumerate(ATTR_NAMES)
    }
    macro = float(np.mean(list(per_attr.values())))
    print(f"run_id={run_id}  model={run.model_id}  samples={len(results)}")
    print(f"macro_f1={macro:.4f}")
    for attr, f1 in per_attr.items():
        print(f"  {attr}: {f1:.4f}")


def _seed_eval_cases(session: Session, eval_items: list, review_map: dict) -> None:
    existing = set(
        session.exec(
            select(BenchmarkCase.case_id).where(BenchmarkCase.target == TARGET)
        ).all()
    )
    added = 0
    for review_id, gold in eval_items:
        if review_id in existing:
            continue
        gold_attrs = [{"name": k, "value": v} for k, v in gold.items() if v != "없음"]
        session.add(BenchmarkCase(
            case_id=review_id,
            target=TARGET,
            review_id=review_id,
            review_text=review_map.get(review_id, ""),
            gold_classification="valid",
            gold_attrs=json.dumps(gold_attrs, ensure_ascii=False),
            coverage_tag="eval_split",
        ))
        added += 1
    if added:
        session.commit()
        print(f"  eval split BenchmarkCase 시딩: {added}개")


def run(
    model_id: str,
    impl_variant: str,
    delay: float,
    model_path: str,
    encoder_name: str,
) -> None:
    if impl_variant == "bert":
        extractor = BERTAttributeExtractor(model_path=model_path, encoder_name=encoder_name)
    else:
        extractor = LLMAttributeExtractor(model_id, delay=0.0)

    with Session(engine) as session:
        eval_items = [
            (lbl.review_id, {a: getattr(lbl, a, "없음") for a in ATTR_NAMES})
            for lbl in session.exec(
                select(ReviewAttributeLabel)
                .where(ReviewAttributeLabel.split == "eval")
                .order_by(ReviewAttributeLabel.review_id)
            ).all()
        ]
        review_map = {r.id: r.raw_text for r in session.exec(select(Review)).all()}
        _seed_eval_cases(session, eval_items, review_map)

        existing_run = session.exec(
            select(BenchmarkRun)
            .where(BenchmarkRun.target == TARGET)
            .where(BenchmarkRun.model_id == model_id)
            .order_by(BenchmarkRun.run_id.desc())
        ).first()

        if existing_run:
            run_id = existing_run.run_id
            done_ids: set[str] = set(
                session.exec(
                    select(BenchmarkResult.case_id)
                    .where(BenchmarkResult.run_id == run_id)
                ).all()
            )
            print(f"기존 run_id={run_id} 재사용. 완료={len(done_ids)}, 잔여={len(eval_items)-len(done_ids)}")
        else:
            run_obj = BenchmarkRun(
                target=TARGET,
                model_id=model_id,
                impl_variant=impl_variant,
                created_at=datetime.utcnow(),
            )
            session.add(run_obj)
            session.flush()
            run_id = run_obj.run_id
            session.commit()
            done_ids = set()
            print(f"새 run_id={run_id}. 총 {len(eval_items)}개 실행")

    to_run = [(rid, gold) for rid, gold in eval_items if rid not in done_ids]
    print(f"실행 대상: {len(to_run)}개")

    for pos, (review_id, _) in enumerate(to_run):
        text = review_map.get(review_id, "")
        pred_dict: dict | None = None
        if text:
            try:
                pred_dict = extractor.extract(text)
            except Exception as e:
                print(f"  [{pos+1}/{len(to_run)}] {review_id} 오류: {e}")

        if pred_dict is not None:
            with Session(engine) as session:
                session.add(BenchmarkResult(
                    run_id=run_id,
                    case_id=review_id,
                    pred_attrs=json.dumps(pred_dict, ensure_ascii=False),
                    pred_classification="valid",
                    clf_correct=False,
                    prompt_tokens=0,
                    completion_tokens=0,
                    latency_ms=0,
                ))
                session.commit()

        if (pos + 1) % 10 == 0:
            print(f"  {pos+1}/{len(to_run)} done")

        if impl_variant != "bert" and pos < len(to_run) - 1:
            time.sleep(delay)

    print(f"\nmodel={model_id}")
    with Session(engine) as session:
        _compute_f1(run_id, session)


def main() -> None:
    parser = argparse.ArgumentParser(description="AttributeExtractor eval (eval split)")
    parser.add_argument("--model", default=None, help="LLM: model-pool.yaml model_id")
    parser.add_argument("--variant", default="llm_zero_shot", choices=["llm_zero_shot", "bert"])
    parser.add_argument("--delay", type=float, default=8.0)
    parser.add_argument("--model-path", default=DEFAULT_BERT_MODEL_PATH,
                        help="BERT 전용: model.pt가 있는 디렉터리")
    parser.add_argument("--encoder", default=DEFAULT_ENCODER,
                        help="BERT 전용: HuggingFace encoder 이름")
    parser.add_argument("--show-run", type=int, default=None)
    args = parser.parse_args()

    init_db()

    if args.show_run:
        with Session(engine) as session:
            _compute_f1(args.show_run, session)
        return

    if args.variant == "bert":
        model_id = f"bert:{args.model_path}"
    else:
        if not args.model:
            parser.error("--model 필요 (llm_zero_shot variant)")
        model_id = args.model

    run(model_id, args.variant, args.delay, args.model_path, args.encoder)


if __name__ == "__main__":
    main()
