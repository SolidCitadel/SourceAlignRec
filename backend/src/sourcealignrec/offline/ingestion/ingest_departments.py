"""학과 레지스트리 적재 — data/raw/departments/{term}.json → Department 테이블.

Usage:
    sar-ingest-departments --data-dir ./data --term 2026-1
"""
import argparse
import json
from pathlib import Path

from sqlmodel import Session

from sourcealignrec.db.models import Department
from sourcealignrec.db.session import engine, init_db


def load(data_dir: Path, term: str) -> None:
    path = data_dir / "raw" / "departments" / f"{term}.json"
    if not path.exists():
        raise FileNotFoundError(f"학과 덤프 없음: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("departments", [])
    print(f"departments: {len(rows)}  ({path.name})")

    inserted = updated = 0
    with Session(engine) as session:
        for row in rows:
            code = str(row.get("code", "")).strip()
            name = str(row.get("name", "")).strip()
            if not code or not name:
                continue
            college_name = (row.get("college_name") or "").strip() or None
            english_name = (row.get("english_name") or "").strip() or None
            existing = session.get(Department, code)
            if existing:
                existing.name = name
                existing.college_name = college_name
                existing.english_name = english_name
                session.add(existing)
                updated += 1
            else:
                session.add(Department(
                    code=code, name=name,
                    college_name=college_name, english_name=english_name,
                ))
                inserted += 1
        session.commit()
    print(f"적재 완료 — 신규 {inserted}, 갱신 {updated}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SourceAlignRec 학과 레지스트리 적재")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--term", required=True, help="학기 (예: 2026-1)")
    args = parser.parse_args()

    init_db()
    load(Path(args.data_dir), args.term)


if __name__ == "__main__":
    main()
