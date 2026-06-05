"""User에게 operator(admin) 권한 부여/회수.

admin 대시보드(`/admin`)는 `role == 'admin'` User만 접근 가능. 가입 시 default는
'student'이므로, 운영자 계정은 본 CLI로 일회성 승격한다.

Usage:
    uv run sar-grant-admin <email>            # admin 부여
    uv run sar-grant-admin <email> --revoke   # student로 회수
"""
from __future__ import annotations

import argparse
import sys

from sqlmodel import Session, select

from sourcealignrec.db.models import User
from sourcealignrec.db.session import engine, init_db


def set_role(email: str, role: str) -> User:
    normalized = email.lower()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == normalized)).first()
        if user is None:
            raise SystemExit(f"[error] 가입된 사용자가 없습니다: {normalized}")
        user.role = role
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description="User admin 권한 부여/회수")
    parser.add_argument("email", help="대상 사용자 이메일")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="admin 권한 회수 (role을 student로)",
    )
    args = parser.parse_args()

    init_db()
    role = "student" if args.revoke else "admin"
    user = set_role(args.email, role)
    print(f"[ok] {user.email} → role={user.role}", file=sys.stderr)


if __name__ == "__main__":
    main()
