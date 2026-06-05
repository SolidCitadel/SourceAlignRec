"""attr 라벨링 후보 리뷰 덤프 — sar-dump-attr-candidates CLI.

기본 모드: ReviewTypeLabel에서 grading/assignment/attendance 타입 리뷰 덤프.
키워드 모드(--keyword): 희소 클래스 보강용. type label 없어도 포함.
  - attendance_leniency: 출석 관련 키워드로 너그러움 후보 탐색
  - assignment_light: 과제 적음 후보 탐색

Claude 서브에이전트가 이 파일을 읽고 attribute 라벨 JSON을 출력하면
sar-import-attr-labels로 DB에 적재한다.

출력 JSON 형식:
[
  {
    "review_id": "...",
    "text": "...",
    "type_hints": {"grading": true, "assignment": false, "attendance": true},
    "keyword_match": ["attendance_leniency"]  // keyword 모드에서만
  },
  ...
]

Usage:
    uv run sar-dump-attr-candidates --out work/attr_candidates.json
    uv run sar-dump-attr-candidates --out work/attr_candidates.json --n 300
    uv run sar-dump-attr-candidates --out work/attr_candidates.json --all
    uv run sar-dump-attr-candidates --out work/attr_kw.json --keyword attendance_leniency assignment_light
"""
from __future__ import annotations

import argparse
import json
import random

from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewAttributeLabel, ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db

KEYWORD_SETS: dict[str, list[str]] = {
    "attendance_leniency": [
        "출석 안", "출결 안", "결석해도", "출석 자유", "출석체크 안",
        "출석 상관", "출석이 없", "출석 없", "출석하지 않아도",
    ],
    "assignment_light": [
        "과제 없", "과제가 없", "과제는 없", "과제 거의", "과제가 거의",
        "과제 안", "과제가 안",
    ],
}


def run_keyword(out_path: str, targets: list[str], n: int | None, seed: int) -> None:
    with Session(engine) as session:
        labeled_ids: set[str] = set(
            session.exec(select(ReviewAttributeLabel.review_id)).all()
        )
        type_label_map: dict[str, ReviewTypeLabel] = {
            lbl.review_id: lbl
            for lbl in session.exec(select(ReviewTypeLabel)).all()
        }
        reviews = session.exec(select(Review.id, Review.raw_text)).all()

    rows = []
    for rid, text in reviews:
        if rid in labeled_ids or not text:
            continue
        matched = [t for t in targets if any(kw in text for kw in KEYWORD_SETS[t])]
        if not matched:
            continue
        entry: dict = {"review_id": rid, "text": text, "keyword_match": matched}
        tl = type_label_map.get(rid)
        if tl:
            entry["type_hints"] = {
                "grading": tl.grading,
                "assignment": tl.assignment,
                "attendance": tl.attendance,
            }
        rows.append(entry)

    if n is not None:
        rng = random.Random(seed)
        rng.shuffle(rows)
        rows = rows[:n]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"키워드 덤프 완료: {len(rows)}개 → {out_path}")
    for t in targets:
        cnt = sum(1 for r in rows if t in r["keyword_match"])
        print(f"  {t}: {cnt}개")
    print(f"  이미 라벨링 완료: {len(labeled_ids)}개 (제외됨)")


def run(out_path: str, n: int | None, seed: int, include_all: bool) -> None:
    with Session(engine) as session:
        labeled_ids: set[str] = set(
            session.exec(select(ReviewAttributeLabel.review_id)).all()
        )
        labels = session.exec(select(ReviewTypeLabel)).all()
        candidates = [
            lbl for lbl in labels
            if (lbl.grading or lbl.assignment or lbl.attendance)
            and lbl.review_id not in labeled_ids
        ]

        if not include_all and n is not None:
            rng = random.Random(seed)
            rng.shuffle(candidates)
            candidates = candidates[:n]

        review_map: dict[str, str] = {
            r.id: r.raw_text
            for r in session.exec(select(Review)).all()
        }

    rows = []
    skipped = 0
    for lbl in candidates:
        text = review_map.get(lbl.review_id)
        if not text:
            skipped += 1
            continue
        rows.append({
            "review_id": lbl.review_id,
            "text": text,
            "type_hints": {
                "grading":    lbl.grading,
                "assignment": lbl.assignment,
                "attendance": lbl.attendance,
            },
        })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"덤프 완료: {len(rows)}개 → {out_path}")
    if skipped:
        print(f"  (텍스트 없음으로 제외: {skipped}개)")
    print(f"  이미 라벨링 완료: {len(labeled_ids)}개 (제외됨)")


def main() -> None:
    parser = argparse.ArgumentParser(description="attr 라벨링 후보 리뷰 덤프")
    parser.add_argument("--out", required=True, help="출력 JSON 파일 경로")
    parser.add_argument(
        "--keyword", nargs="+", choices=list(KEYWORD_SETS.keys()), default=None,
        metavar="TARGET",
        help=f"키워드 기반 희소 클래스 보강 모드. 선택: {list(KEYWORD_SETS.keys())}",
    )
    parser.add_argument("--n", type=int, default=None, help="최대 후보 수 (기본: 전체)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="n 무시하고 전체 후보 덤프 (기본 모드 전용)")
    args = parser.parse_args()

    init_db()
    if args.keyword:
        run_keyword(args.out, args.keyword, args.n, args.seed)
    else:
        run(args.out, args.n, args.seed, args.include_all)


if __name__ == "__main__":
    main()
