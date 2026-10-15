"""Item 2.6, part 2: token issuance, refresh, rotation and revocation."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import User
from app.models.account import UserRole
from app.security.tokens import (
    RefreshTokenError,
    TokenError,
    create_access_token,
    decode_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)


def _settings(**overrides) -> Settings:
    kwargs = {"environment": "ci", "jwt_secret": "unit-test-secret", **overrides}
    return Settings(**kwargs)


def tamper_signature(token: str) -> str:
    """Flip a character from the *middle* of the signature. The last base64url 
    character's unused pad bits are ignored on decode, so editing there can 
    decode back to the same bytes — flipping mid-string cannot."""
    body, _, signature = token.rpartition(".")
    mid = len(signature) // 2
    flipped = "A" if signature[mid] != "A" else "B"
    return f"{body}.{signature[:mid]}{flipped}{signature[mid + 1:]}"


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        email="tokens@unit.test",
        password_hash="x",
        role=UserRole.LISTENER,
        date_of_birth=date(1990, 1, 1),
        display_name="Unit",
    )


def test_access_token_round_trip():
    settings = _settings()
    user = _user()
    claims = decode_access_token(create_access_token(user, settings), settings)
    assert claims.user_id == user.id
    assert claims.role == "listener"
    assert claims.expires_at > datetime.now(UTC)


def test_expired_access_token_rejected():
    settings = _settings()
    past = datetime.now(UTC) - timedelta(seconds=settings.access_token_ttl_seconds + 60)
    with pytest.raises(TokenError):
        decode_access_token(create_access_token(_user(), settings, now=past), settings)


def test_tampered_signature_rejected():
    settings = _settings()
    with pytest.raises(TokenError):
        decode_access_token(tamper_signature(create_access_token(_user(), settings)), settings)


def test_wrong_secret_rejected():
    token = create_access_token(_user(), _settings())
    with pytest.raises(TokenError):
        decode_access_token(token, _settings(jwt_secret="different-secret"))


def test_garbage_token_rejected():
    with pytest.raises(TokenError):
        decode_access_token("not.a.token", _settings())


def test_refresh_token_used_as_access_rejected():
    """A JWT whose typ is not 'access' must not open doors."""
    settings = _settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token, settings)


async def _persist_user(db: AsyncSession) -> User:
    user = _user()
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_refresh_issue_rotate_revoke(db: AsyncSession):
    settings, user = _settings(), await _persist_user(db)

    record, plaintext = await issue_refresh_token(db, user, settings)
    await db.commit()
    assert plaintext != record.token_hash  # only the hash is stored

    rotated_to, new_record, new_plain = await rotate_refresh_token(db, plaintext, settings)
    await db.commit()
    assert rotated_to.id == user.id
    assert new_record.family_id == record.family_id
    assert record.revoked_at is not None

    await revoke_refresh_token(db, new_plain)
    await db.commit()
    with pytest.raises(RefreshTokenError):
        await rotate_refresh_token(db, new_plain, settings)


@pytest.mark.asyncio
async def test_replay_of_rotated_token_revokes_whole_family(db: AsyncSession):
    """Rotation-reuse detection: re-presenting an already-rotated token nukes 
    every live token in its family (the theft signal)."""
    settings, user = _settings(), await _persist_user(db)

    _, first = await issue_refresh_token(db, user, settings)
    await db.commit()
    _, second_record, second_plain = await rotate_refresh_token(db, first, settings)
    await db.commit()

    with pytest.raises(RefreshTokenError):
        await rotate_refresh_token(db, first, settings)  # replay of rotated token
    await db.commit()

    with pytest.raises(RefreshTokenError):
        await rotate_refresh_token(db, second_plain, settings)  # live family member now dead too
    assert second_record.revoked_at is not None
