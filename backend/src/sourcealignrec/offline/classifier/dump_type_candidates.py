"""타입 라벨링 후보 리뷰 덤프 — sar-dump-type-candidates CLI.

ReviewTypeLabel이 없는 리뷰를 JSON으로 덤프.
서브에이전트가 이 파일을 읽고 타입 라벨을 달아 output JSON을 생성하면
sar-import-type-labels로 DB에 적재한다.

출력 JSON 형식:
[
  {"review_id": "...", "text": "..."},
  ...
]

Usage:
    uv run sar-dump-type-candidates --out backend/work/type_candidates.json
    uv run sar-dump-type-candidates --out backend/work/type_candidates.json --n 500
"""
from __future__ import annotations

import argparse
import json
import random

from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db


def run(out_path: str, n: int | None, seed: int) -> None:
    with Session(engine) as session:
        labeled_ids: set[str] = set(
            session.exec(select(ReviewTypeLabel.review_id)).all()
        )
        all_reviews = session.exec(select(Review)).all()

    candidates = [r for r in all_reviews if r.id not in labeled_ids]

    rng = random.Random(seed)
    rng.shuffle(candidates)
    if n is not None:
        candidates = candidates[:n]

    rows = [{"review_id": r.id, "text": r.raw_text} for r in candidates if r.raw_text]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"덤프 완료: {len(rows)}개 → {out_path}")
    print(f"  전체 리뷰: {len(all_reviews)}  |  이미 라벨링: {len(labeled_ids)}  |  후보: {len(candidates)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="타입 라벨링 후보 리뷰 덤프")
    parser.add_argument("--out", required=True, help="출력 JSON 파일 경로")
    parser.add_argument("--n", type=int, default=None, help="최대 후보 수 (기본: 전체)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    init_db()
    run(args.out, args.n, args.seed)


if __name__ == "__main__":
    main()
