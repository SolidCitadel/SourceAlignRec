"""타입 라벨 JSON → ReviewTypeLabel DB 적재 — sar-import-type-labels CLI.

입력 JSON 형식 (서브에이전트 출력):
[
  {
    "review_id": "...",
    "grading": false,
    "exam": false,
    "assignment": true,
    "attendance": false,
    "teaching": true,
    "topic": false,
    "professor": false
  },
  ...
]

Usage:
    uv run sar-import-type-labels --file work/type_labels.json
    uv run sar-import-type-labels --file work/type_labels.json --dry-run
"""
from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from sourcealignrec.db.models import ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db

FIELDS = ["grading", "exam", "assignment", "attendance", "teaching", "topic", "professor"]


def run(file_path: str, labeler: str, dry_run: bool, overwrite: bool) -> None:
    with open(file_path, encoding="utf-8") as f:
        rows: list[dict] = json.load(f)

    print(f"입력: {len(rows)}개  |  dry_run={dry_run}  |  labeler={labeler}")

    with Session(engine) as session:
        existing: set[str] = set(
            session.exec(select(ReviewTypeLabel.review_id)).all()
        )

        added = skipped = invalid = overwritten = 0
        for row in rows:
            review_id = row.get("review_id")
            if not review_id:
                print(f"  [경고] review_id 없음, 스킵: {row}")
                invalid += 1
                continue

            # 모든 타입 필드가 bool인지 확인
            bad = [f for f in FIELDS if not isinstance(row.get(f), bool)]
            if bad:
                print(f"  [경고] {review_id} 필드 오류 ({bad}), 스킵")
                invalid += 1
                continue

            if review_id in existing:
                if not overwrite:
                    skipped += 1
                    continue
                old = session.exec(
                    select(ReviewTypeLabel).where(ReviewTypeLabel.review_id == review_id)
                ).first()
                if old:
                    session.delete(old)
                    session.flush()
                overwritten += 1

            is_noise = not any(row.get(f, False) for f in FIELDS)
            lbl = ReviewTypeLabel(
                review_id=review_id,
                source="llm",
                labeler=labeler,
                is_noise=is_noise,
                **{f: bool(row.get(f, False)) for f in FIELDS},
            )
            if not dry_run:
                session.add(lbl)
            added += 1

        if not dry_run:
            session.commit()

    action = "(dry-run)" if dry_run else "완료"
    print(f"{action}: 추가={added}  덮어쓰기={overwritten}  스킵(중복)={skipped}  오류={invalid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="타입 라벨 JSON → DB 적재")
    parser.add_argument("--file", required=True, help="입력 JSON 파일")
    parser.add_argument("--labeler", default="claude-sonnet-4-6")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    init_db()
    run(args.file, args.labeler, args.dry_run, args.overwrite)


if __name__ == "__main__":
    main()
