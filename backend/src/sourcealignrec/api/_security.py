"""JWT + 비밀번호 helper. api-contract/_common.md §2 정합 (HS256, sar_jwt_secret, 7일)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from sourcealignrec.core.config import settings
from sourcealignrec.db.models import User
from sourcealignrec.db.session import get_session

_JWT_ALG = "HS256"
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.sar_jwt_ttl_days),
    }
    return jwt.encode(payload, settings.sar_jwt_secret, algorithm=_JWT_ALG)


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.sar_jwt_secret, algorithms=[_JWT_ALG])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="인증이 만료되었습니다.") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="인증 토큰이 유효하지 않습니다.") from e
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="인증 토큰이 유효하지 않습니다.")
    return sub


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    """Authorization: Bearer <token> 검증 후 User 반환. 미인증/만료 시 401."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    user_id = _decode_token(creds.credentials)
    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="인증 토큰이 유효하지 않습니다.")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """operator 전용 endpoint 게이트. role != 'admin'이면 403."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="운영자 권한이 필요합니다.")
    return user


def get_user_dept_code(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> str | None:
    """본인 학과(User.department) → Department.code. 이수구분 표시 렌즈용. 미해결 시 None."""
    from sourcealignrec.online import dept_lens
    return dept_lens.resolve_department_code(session, user.department)
