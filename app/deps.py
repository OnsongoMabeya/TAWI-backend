import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User, UserLink
from app.permissions import can_read_listener_sessions
from app.security.tokens import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
    settings: CurrentSettings,
) -> User:
    """Resolve the bearer token to a live user. Every 401 takes this one path 
    so expired, forged, mistyped and absent tokens are indistinguishable."""
    if credentials is None:
        raise UNAUTHORIZED
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise UNAUTHORIZED from exc
    user = await db.get(User, claims.user_id)
    if user is None:
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_can_read_listener(
    listener_id: uuid.UUID, requester: CurrentUser, db: DbSession
) -> User:
    """Protects /users/{listener_id}/... routes. Returns 404 (not 403) when the 
    requester has no rights, so the existence of the target account is not leakable."""
    listener = await db.get(User, listener_id)
    if listener is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    links: list[UserLink] = []
    if requester.id != listener_id:
        result = await db.execute(
            select(UserLink).where(
                UserLink.listener_id == listener_id,
                UserLink.authorised_user_id == requester.id,
            )
        )
        links = list(result.scalars())

    if not can_read_listener_sessions(requester, listener, links):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return listener
