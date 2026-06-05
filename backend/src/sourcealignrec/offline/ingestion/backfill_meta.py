"""기존 Offering row의 notice + meetings_json 백필.

ingest는 멱등(기존 row skip)이라 단순 재실행으로는 새 필드 채워지지 않음. 본 스크립트는
review-mappings/parsed의 최신 mapping_file을 읽어 모든 row를 다시 순회하며 매칭되는
Offering row의 `notice`/`meetings_json`만 UPDATE한다. 다른 필드는 건드리지 않음.

Usage:
    uv run sar-backfill-meta --data-dir ./data
    uv run sar-backfill-meta --data-dir ./data --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlmodel import Session

from sourcealignrec.db.models import Offering
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.ingestion.ingest import _parse_category
from sourcealignrec.offline.ingestion.syllabus_parser import load_syllabus
from sourcealignrec.offline.ingestion.time_place_parser import parse_time_place


def _to_syllabus_code(course_code: str) -> str:
    """parsed의 course_code(`EE210-02`) → syllabus_course_code 형식(`EE21002`).

    ingest.py와 정합 — Offering.id는 syllabus_course_code + term으로 생성됨.
    대시가 없는 형식이면 그대로 반환.
    """
    return course_code.replace("-", "") if "-" in course_code else course_code


def backfill(data_dir: Path, dry_run: bool = False) -> dict:
    """course list parsed file에 있는 note + time_place로 기존 Offering row UPDATE.

    parsed file 선택 이유: note/time_place는 parsed(course list raw)에만 있음.
    linked file은 syllabus↔review 매칭용이라 해당 필드 없음.
    """
    mapping_files = sorted((data_dir / "raw/review-mappings/parsed").glob("*.json"))
    if not mapping_files:
        raise FileNotFoundError("review-mappings/parsed 파일 없음")
    mapping_file = mapping_files[-1]
    parsed = json.loads(mapping_file.read_text(encoding="utf-8"))
    term = parsed.get("term")
    rows = parsed["rows"]

    if not term:
        raise ValueError(f"{mapping_file.name}: top-level term 없음")

    syllabi_dir = data_dir / "raw/syllabi"

    stats = {
        "seen": 0, "matched": 0,
        "notice_set": 0, "meetings_set": 0, "online_set": 0, "depts_set": 0,
        "credits_set": 0, "course_type_set": 0, "syllabus_url_set": 0,
        "no_offering": 0,
    }
    with Session(engine) as session:
        for row in rows:
            stats["seen"] += 1
            course_code = row.get("course_code")
            if not course_code:
                continue
            sylcode = _to_syllabus_code(course_code)
            offering_id = f"{sylcode}_{term}"
            offering = session.get(Offering, offering_id)
            if offering is None:
                stats["no_offering"] += 1
                continue

            stats["matched"] += 1
            changed = False

            note = (row.get("note") or "").strip() or None
            if note != offering.notice:
                offering.notice = note
                changed = True
                stats["notice_set"] += 1

            tp_raw = row.get("time_place") or ""
            meetings = parse_time_place(tp_raw)
            meetings_json = json.dumps(meetings, ensure_ascii=False)
            if meetings_json != (offering.meetings_json or "[]"):
                offering.meetings_json = meetings_json
                changed = True
                stats["meetings_set"] += 1

            is_online = "온라인" in tp_raw
            if is_online != bool(offering.is_online):
                offering.is_online = is_online
                changed = True
                stats["online_set"] += 1

            sf = load_syllabus(syllabi_dir / f"{sylcode}_{term}.json")
            recognized = sf["recognized_depts"] if sf else []
            depts_json = json.dumps(recognized, ensure_ascii=False)
            if depts_json != (offering.recognized_depts_json or "[]"):
                offering.recognized_depts_json = depts_json
                changed = True
                stats["depts_set"] += 1

            new_url = sf["syllabus_url"] if sf else None
            if new_url and new_url != offering.syllabus_url:
                offering.syllabus_url = new_url
                changed = True
                stats["syllabus_url_set"] += 1

            # mapping credit/category primary (종합정보시스템 학사 정량). 기존 NULL/diff면 update.
            try:
                new_credits: int | None = int(row.get("credit"))
            except (TypeError, ValueError):
                new_credits = offering.credits
            if new_credits is not None and new_credits != offering.credits:
                offering.credits = new_credits
                changed = True
                stats["credits_set"] += 1

            new_ct = _parse_category(row.get("category"))
            if new_ct and new_ct != offering.course_type:
                offering.course_type = new_ct
                changed = True
                stats["course_type_set"] += 1

            if changed and not dry_run:
                session.add(offering)
        if not dry_run:
            session.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="기존 Offering row notice + meetings 백필")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 통계만 출력")
    args = parser.parse_args()

    init_db()
    stats = backfill(Path(args.data_dir), dry_run=args.dry_run)
    mode = "[dry-run] " if args.dry_run else ""
    print(f"{mode}backfill stats: {stats}")


if __name__ == "__main__":
    main()
