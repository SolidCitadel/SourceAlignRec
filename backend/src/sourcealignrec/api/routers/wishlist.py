"""Wishlist router — api-contract/wishlist.md 정합."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from sourcealignrec.api._offering_view import (
    OfferingSummaryOut,
    offering_exists,
    summaries_by_ids,
)
from sourcealignrec.api._schemas import WireModel
from sourcealignrec.api._security import get_current_user, get_user_dept_code
from sourcealignrec.db.models import User, WishlistItem
from sourcealignrec.db.session import get_session

router = APIRouter(tags=["wishlist"])


# ── Wire schemas ────────────────────────────────────────────────────────────


class WishlistResponse(WireModel):
    items: list[OfferingSummaryOut]


class WishlistAddRequest(WireModel):
    offering_id: str


class WishlistItemResponse(WireModel):
    item: OfferingSummaryOut


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/wishlist", response_model=WishlistResponse)
def list_wishlist(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    rows = session.exec(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at)
    ).all()
    by_id = summaries_by_ids(session, [r.offering_id for r in rows], dept_code)
    # offering이 사라진 row(드물지만 ingestion 재적재 시 가능)는 누락.
    items = [by_id[r.offering_id] for r in rows if r.offering_id in by_id]
    return WishlistResponse(items=items)


@router.post("/wishlist", response_model=WishlistItemResponse)
def add_wishlist(
    req: WishlistAddRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dept_code: str | None = Depends(get_user_dept_code),
):
    if not offering_exists(session, req.offering_id):
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")

    existing = session.exec(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .where(WishlistItem.offering_id == req.offering_id)
    ).first()
    if existing is None:
        session.add(WishlistItem(user_id=user.id, offering_id=req.offering_id))
        session.commit()

    summary = summaries_by_ids(session, [req.offering_id], dept_code)[req.offering_id]
    return WishlistItemResponse(item=summary)


@router.delete("/wishlist/{offering_id}", status_code=204)
def remove_wishlist(
    offering_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    existing = session.exec(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .where(WishlistItem.offering_id == offering_id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.commit()
    return None
