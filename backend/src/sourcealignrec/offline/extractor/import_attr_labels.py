"""attr 라벨 JSON → ReviewAttributeLabel DB 적재 — sar-import-attr-labels CLI.

입력 JSON 형식 (Claude 서브에이전트 출력):
[
  {
    "review_id": "...",
    "grading_leniency": "너그러움",
    "assignment_load": "없음",
    "team_project": "없음",
    "attendance_strictness": "없음"
  },
  ...
]

없음 = 해당 속성 신호 없음. 모든 속성은 반드시 포함 (누락 시 없음 처리).

Usage:
    uv run sar-import-attr-labels --file work/attr_labels.json
    uv run sar-import-attr-labels --file work/attr_labels.json --labeler claude-opus-4-7
    uv run sar-import-attr-labels --file work/attr_labels.json --dry-run
"""
from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from sourcealignrec.db.models import ReviewAttributeLabel
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.extractor.attribute_extractor import ATTR_VALUES

VALID: dict[str, set[str]] = {k: set(v) for k, v in ATTR_VALUES.items()}


def _validate(row: dict) -> tuple[bool, str]:
    for attr, valid_vals in VALID.items():
        val = row.get(attr, "없음") or "없음"
        if val not in valid_vals:
            return False, f"{attr}={val!r} 유효하지 않음 (허용: {sorted(valid_vals)})"
    return True, ""


def run(file_path: str, labeler: str, dry_run: bool, overwrite: bool) -> None:
    with open(file_path, encoding="utf-8") as f:
        rows: list[dict] = json.load(f)

    print(f"입력: {len(rows)}개  |  dry_run={dry_run}  |  labeler={labeler}")

    with Session(engine) as session:
        existing: set[str] = set(
            session.exec(select(ReviewAttributeLabel.review_id)).all()
        )

        added = skipped = invalid = overwritten = 0
        for row in rows:
            review_id = row.get("review_id")
            if not review_id:
                print(f"  [경고] review_id 없음, 스킵: {row}")
                invalid += 1
                continue

            ok, msg = _validate(row)
            if not ok:
                print(f"  [경고] {review_id} 유효성 오류 ({msg}), 스킵")
                invalid += 1
                continue

            if review_id in existing:
                if not overwrite:
                    skipped += 1
                    continue
                old = session.exec(
                    select(ReviewAttributeLabel).where(
                        ReviewAttributeLabel.review_id == review_id
                    )
                ).first()
                if old:
                    session.delete(old)
                    session.flush()
                overwritten += 1

            lbl = ReviewAttributeLabel(
                review_id=review_id,
                grading_leniency=row.get("grading_leniency") or "없음",
                assignment_load=row.get("assignment_load") or "없음",
                team_project=row.get("team_project") or "없음",
                attendance_strictness=row.get("attendance_strictness") or "없음",
                labeler=labeler,
            )
            if not dry_run:
                session.add(lbl)
            added += 1

        if not dry_run:
            session.commit()

    action = "(dry-run)" if dry_run else "완료"
    print(f"{action}: 추가={added}  덮어쓰기={overwritten}  스킵(중복)={skipped}  오류={invalid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="attr 라벨 JSON → DB 적재")
    parser.add_argument("--file", required=True, help="입력 JSON 파일")
    parser.add_argument("--labeler", default="claude-sonnet-4-6")
    parser.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 검증만")
    parser.add_argument("--overwrite", action="store_true", help="이미 있는 review_id 덮어쓰기")
    args = parser.parse_args()

    init_db()
    run(args.file, args.labeler, args.dry_run, args.overwrite)


if __name__ == "__main__":
    main()
