import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import RefreshToken, User

ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """Any access-token problem that should surface to the client as a 401."""


class RefreshTokenError(Exception):
    """Any refresh-token problem; reuse of a rotated token revokes its family."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    role: str
    expires_at: datetime
    jti: str


def create_access_token(user: User, settings: Settings, *, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "typ": ACCESS_TOKEN_TYPE,
        "role": user.role,
        "jti": uuid.uuid4().hex,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    """Strict validation: signature, expiry, token type, subject shape. This is
    the function item 2.8's sweep exercises."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("wrong token type")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
        jti = str(payload["jti"])
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("malformed claims") from exc
    return AccessTokenClaims(
        user_id=user_id, role=str(payload.get("role", "")), expires_at=expires_at, jti=jti
    )


def generate_refresh_token() -> str:
    """Opaque, URL-safe, high-entropy refresh token. Never a JWT — JWT refresh 
    tokens can't be revoked without a denylist, and we want plain revocation."""
    return secrets.token_urlsafe(48)  # 384 bits of entropy


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_pairing_code(code: str) -> str:
    """Pairing codes get the same treatment as refresh tokens: stored hashed, 
    so the codes table is useless to anyone who reads it."""
    return hash_token(code.upper().strip())


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


async def issue_refresh_token(
    db: AsyncSession,
    user: User,
    settings: Settings,
    *,
    family_id: uuid.UUID | None = None,
    client_ip: str | None = None,
) -> tuple[RefreshToken, str]:
    """Store (hashed) and return one refresh token plus its plaintext."""
    plaintext = generate_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_token(plaintext),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        created_ip=client_ip,
    )
    db.add(record)
    await db.flush()
    return record, plaintext


async def rotate_refresh_token(
    db: AsyncSession, presented: str, settings: Settings, *, client_ip: str | None = None
) -> tuple[User, RefreshToken, str]:
    """Validate a presented refresh token and rotate it.

    Raises RefreshTokenError for every failure mode. Reuse of an already-rotated 
    token revokes the whole family — that is the theft-detection signal."""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(presented))
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise RefreshTokenError("unknown refresh token")

    now = datetime.now(UTC)
    if record.revoked_at is not None:
        family = await db.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None)
            )
        )
        for sibling in family.scalars():
            sibling.revoked_at = now
        raise RefreshTokenError("refresh token reuse detected; family revoked")

    if record.expires_at <= now:
        raise RefreshTokenError("refresh token expired")

    user = await db.get(User, record.user_id)
    if user is None:
        raise RefreshTokenError("refresh token belongs to a user that no longer exists")

    record.revoked_at = now
    new_record, plaintext = await issue_refresh_token(
        db, user, settings, family_id=record.family_id, client_ip=client_ip
    )
    return user, new_record, plaintext


async def revoke_refresh_token(db: AsyncSession, presented: str) -> None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(presented))
    )
    if (record := result.scalar_one_or_none()) is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
