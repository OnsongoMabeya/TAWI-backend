import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentSettings, CurrentUser, DbSession, require_can_read_listener
from app.models import LinkCode, Session, User, UserLink
from app.permissions import can_generate_link_code, can_redeem_link_code
from app.schemas import (
    LinkCodeRequest,
    LinkCodeResponse,
    LinkRedeemedResponse,
    RedeemLinkCodeRequest,
    SessionListResponse,
    SessionSummary,
    UserProfile,
)
from app.security.tokens import hash_pairing_code

router = APIRouter(tags=["users"])

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/I/O/1 — codes are read aloud/typed


@router.get("/users/me", response_model=UserProfile)
async def me(user: CurrentUser):
    return user


@router.post(
    "/users/me/link-codes",
    response_model=LinkCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_link_code(
    body: LinkCodeRequest, user: CurrentUser, db: DbSession, settings: CurrentSettings
):
    """A listener mints a one-time pairing code to show (or read) to whoever 
    is meant to gain access. The plaintext code is returned once and never stored."""
    allowed, reason = can_generate_link_code(user, body.grants)
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)

    halves = [
        "".join(secrets.choice(ALPHABET) for _ in range(4)),
        "".join(secrets.choice(ALPHABET) for _ in range(4)),
    ]
    code = "-".join(halves)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.pairing_code_ttl_seconds)
    db.add(
        LinkCode(
            code_hash=hash_pairing_code(code),
            grants_kind=body.grants,
            created_by_id=user.id,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return LinkCodeResponse(code=code, grants=body.grants, expires_at=expires_at)


@router.post(
    "/links/redeem", response_model=LinkRedeemedResponse, status_code=status.HTTP_201_CREATED
)
async def redeem_link_code(body: RedeemLinkCodeRequest, requester: CurrentUser, db: DbSession):
    code_hash = hash_pairing_code(body.code)
    result = await db.execute(
        select(LinkCode).where(LinkCode.code_hash == code_hash).with_for_update()
    )
    code = result.scalar_one_or_none()
    if code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown code")

    if code.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "code already redeemed")
    if code.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "code expired")

    listener = await db.get(User, code.created_by_id)
    if listener is None:
        raise HTTPException(status.HTTP_410_GONE, "code expired")

    allowed, reason = can_redeem_link_code(requester, code.grants_kind, listener)
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)

    existing = await db.execute(
        select(UserLink.id).where(
            UserLink.listener_id == listener.id,
            UserLink.authorised_user_id == requester.id,
            UserLink.kind == code.grants_kind,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this link already exists")

    link = UserLink(
        listener_id=listener.id,
        authorised_user_id=requester.id,
        kind=code.grants_kind,
    )
    code.redeemed_by_id = requester.id
    code.redeemed_at = datetime.now(UTC)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return LinkRedeemedResponse(listener_id=listener.id, kind=link.kind, created_at=link.created_at)


@router.get("/users/{listener_id}/sessions", response_model=SessionListResponse)
async def list_listener_sessions(
    db: DbSession,
    listener: Annotated[User, Depends(require_can_read_listener)],
):
    """A listener's session history, readable only via the permission matrix 
    (see app/permissions.py). Unauthorised requesters get 404, not 403, so the
    existence of an account is not leakable. Sessions are only ever populated 
    by later phases; the list is empty in Phase 2, but the access control is real."""
    result = await db.execute(
        select(Session)
        .where(Session.owner_id == listener.id, Session.deleted_at.is_(None))
        .order_by(Session.recorded_at.desc().nulls_last(), Session.created_at.desc())
    )
    sessions = [SessionSummary.model_validate(s) for s in result.scalars()]
    return SessionListResponse(listener_id=listener.id, sessions=sessions)
