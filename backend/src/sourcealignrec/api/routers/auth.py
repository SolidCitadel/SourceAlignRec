"""인증 router — api-contract/auth.md 정합 (signup/login/me)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from sourcealignrec.api.routers.timetables import DEFAULT_TIMETABLE_NAME
from sourcealignrec.db.models import Timetable, User
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["auth"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class UserOut(WireModel):
    id: str
    email: str
    school: str
    department: str
    grade: int
    admission_year: int
    name: str | None = None
    role: str


class SignupRequest(WireModel):
    email: EmailStr
    password: str = Field(min_length=8)
    school: str = Field(min_length=1)
    department: str = Field(min_length=1)
    grade: int = Field(ge=1, le=6)
    admission_year: int = Field(ge=1990, le=datetime.utcnow().year)
    name: str = Field(min_length=1)


class UserUpdate(WireModel):
    """PATCH /me 부분 수정. 제공된 필드만 반영(exclude_unset). email·role·id는 수정 불가."""
    name: str | None = Field(default=None, min_length=1)
    school: str | None = Field(default=None, min_length=1)
    department: str | None = Field(default=None, min_length=1)
    grade: int | None = Field(default=None, ge=1, le=6)
    admission_year: int | None = Field(default=None, ge=1990, le=datetime.utcnow().year)


class LoginRequest(WireModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthResponse(WireModel):
    token: str
    user: UserOut


# ── Endpoints ───────────────────────────────────────────────────────────────


def _to_user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        school=u.school,
        department=u.department,
        grade=u.grade,
        admission_year=u.admission_year,
        name=u.name,
        role=u.role,
    )


@router.post("/auth/signup", response_model=AuthResponse, status_code=201)
def signup(req: SignupRequest, session: Session = Depends(get_session)):
    normalized_email = req.email.lower()
    user = User(
        id=uuid.uuid4().hex,
        email=normalized_email,
        password_hash=hash_password(req.password),
        school=req.school,
        department=req.department,
        grade=req.grade,
        admission_year=req.admission_year,
        name=req.name,
    )
    session.add(user)
    try:
        # User FK 확보를 위해 flush — 이메일 중복은 이 시점에 IntegrityError로 잡힘.
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from None

    # 신규 user는 빈 "시안 1" 1개 동시 생성 — api-contract/timetable.md.
    session.add(
        Timetable(
            id=uuid.uuid4().hex,
            user_id=user.id,
            name=DEFAULT_TIMETABLE_NAME,
        ),
    )
    session.commit()
    session.refresh(user)
    token = create_access_token(user.id)
    return AuthResponse(token=token, user=_to_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)):
    normalized_email = req.email.lower()
    user = session.exec(select(User).where(User.email == normalized_email)).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    token = create_access_token(user.id)
    return AuthResponse(token=token, user=_to_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _to_user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    req: UserUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_user_out(user)
