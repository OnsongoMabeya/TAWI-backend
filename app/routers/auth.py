from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.deps import UNAUTHORIZED, CurrentSettings, DbSession
from app.models import User
from app.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.security.passwords import hash_password, verify_password
from app.security.tokens import (
    RefreshTokenError,
    create_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

CONFLICT = HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _issue_pair(db: DbSession, user: User, settings, *, ip: str | None) -> TokenPair:
    _, refresh_plain = await issue_refresh_token(db, user, settings, client_ip=ip)
    await db.commit()  # the refresh record must outlive the request
    return TokenPair(
        access_token=create_access_token(user, settings),
        refresh_token=refresh_plain,
        access_token_expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, request: Request, db: DbSession, settings: CurrentSettings
):
    existing = await db.execute(select(User.id).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise CONFLICT

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        date_of_birth=body.date_of_birth,
        display_name=body.display_name,
        consent_given_at=datetime.now(UTC) if body.consent_accepted else None,
        consent_given_by=body.consent_given_by if body.consent_accepted else None,
        data_retention_preference=body.data_retention_preference,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return AuthResponse(
        tokens=await _issue_pair(db, user, settings, ip=_client_ip(request)), user=user
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, request: Request, db: DbSession, settings: CurrentSettings):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Verify against a constant dummy hash when the email is unknown so the
    # response time does not reveal whether the account exists.
    digest = (
        user.password_hash
        if user
        else "$argon2id$v=19$m=65536,t=3,p=1$c29tZS1zdGF0aWMtc2FsdA$c29tZS1zdGF0aWMtaGFzaA"
    )
    if not verify_password(body.password, digest) or user is None:
        raise UNAUTHORIZED

    return AuthResponse(
        tokens=await _issue_pair(db, user, settings, ip=_client_ip(request)), user=user
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request, db: DbSession, settings: CurrentSettings):
    try:
        user, _, new_plain = await rotate_refresh_token(
            db, body.refresh_token, settings, client_ip=_client_ip(request)
        )
    except RefreshTokenError as exc:
        await db.rollback()
        raise UNAUTHORIZED from exc
    await db.commit()
    return TokenPair(
        access_token=create_access_token(user, settings),
        refresh_token=new_plain,
        access_token_expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: DbSession):
    await revoke_refresh_token(db, body.refresh_token)
    await db.commit()
    return None
