"""Item 2.8: expired/invalid tokens are rejected on EVERY protected route."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.config import get_settings

GOOD_PASSWORD = "correct-horse-battery-99"


def _register(client, email):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": GOOD_PASSWORD,
            "role": "listener",
            "date_of_birth": "1990-05-01",
            "display_name": "sweep",
            "consent_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


PROTECTED_ROUTES = [
    ("GET", "/users/me", None),
    ("POST", "/users/me/link-codes", {"grants": "caregiver"}),
    ("POST", "/links/redeem", {"code": "ZZZZ-ZZZZ"}),
]
# /users/{listener_id}/sessions is added dynamically below, with the shipping id.


def _variants(client, tokens):
    """Six ways a presented credential can be bad."""
    settings = get_settings()
    good_access = tokens["tokens"]["access_token"]

    now = datetime.now(UTC)

    def mint(**overrides):
        payload = {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "role": "listener",
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(seconds=30)).timestamp()),
            **overrides,
        }
        return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    expired = mint(sub=str(uuid.UUID(tokens["user"]["id"])))
    body_part, _, signature = good_access.rpartition(".")
    # Mid-string edit: the tail char's unused pad bits are ignored on decode.
    mid = len(signature) // 2
    flipped = "A" if signature[mid] != "A" else "B"
    tampered = f"{body_part}.{signature[:mid]}{flipped}{signature[mid + 1:]}"
    wrong_secret_mint = {
        "sub": tokens["user"]["id"],
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    forged = pyjwt.encode(wrong_secret_mint, "attacker-secret", algorithm="HS256")
    wrong_typ = mint(
        sub=tokens["user"]["id"], typ="refresh", exp=int((now + timedelta(minutes=5)).timestamp())
    )
    ghost_user = mint(sub=str(uuid.uuid4()), exp=int((now + timedelta(minutes=5)).timestamp()))

    return {
        "expired": expired,
        "tampered signature": tampered,
        "forged with wrong secret": forged,
        "typ=refresh presented as access": wrong_typ,
        "token for a deleted/unknown user": ghost_user,
    }

@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_no_token_401(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers}

@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES + [("GET", "sessions", None)])
@pytest.mark.parametrize(
    "variant",
    [
        "expired",
        "tampered signature",
        "forged with wrong secret",
        "typ=refresh presented as access",
        "token for a deleted/unknown user",
    ],
)

def test_bad_tokens_401(client, variant, method, path, body):
    tokens = _register(client, f"{variant.replace(' ', '-')[:20]}-{uuid.uuid4().hex[:6]}@sweep.dev")
    if path == "sessions":
        path = f"/users/{tokens['user']['id']}/sessions"
    headers = {"Authorization": f"Bearer {_variants(client, tokens)[variant]}"}
    response = client.request(method, path, json=body, headers=headers)
    assert response.status_code == 401

def test_not_bearer_scheme_401(client):
    tokens = _register(client, f"scheme-{uuid.uuid4().hex[:6]}@sweep.dev")
    bad = client.get("/users/me", headers={"Authorization": tokens["tokens"]["access_token"]})
    assert bad.status_code in (401, 403)
