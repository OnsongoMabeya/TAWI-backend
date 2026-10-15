"""Integration: register / login / refresh / logout over HTTP against real Postgres."""

GOOD_PASSWORD = "correct-horse-battery-99"


def _register(client, email, role="listener", dob="1990-05-01", **overrides):
    body = {
        "email": email,
        "password": GOOD_PASSWORD,
        "role": role,
        "date_of_birth": dob,
        "display_name": email.split("@")[0],
        "consent_accepted": True,
        **overrides,
    }
    response = client.post("/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email, password=GOOD_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_login_me_refresh_logout(client):
    body = _register(client, "flow@test.dev")
    assert body["user"]["email"] == "flow@test.dev"
    assert body["user"]["consent_given_at"] is not None
    assert body["user"]["consent_given_by"] == "self"
    assert body["tokens"]["token_type"] == "bearer"

    token = body["tokens"]["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "flow@test.dev"

    rotated = client.post("/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != body["tokens"]["refresh_token"]

    out = client.post("/auth/logout", json={"refresh_token": rotated.json()["refresh_token"]})
    assert out.status_code == 204
    assert (
        client.post(
            "/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}
        ).status_code
        == 401
    )


def test_duplicate_email_conflict_and_case_insensitive(client):
    _register(client, "Case@Test.dev")
    dupe = client.post(
        "/auth/register",
        json={
            "email": "case@test.dev",
            "password": GOOD_PASSWORD,
            "role": "listener",
            "date_of_birth": "1990-05-01",
            "display_name": "dupe",
            "consent_accepted": True,
        },
    )
    assert dupe.status_code == 409


def test_login_unknown_email_and_wrong_password_are_indistinguishable(client):
    _register(client, "known@test.dev")
    unknown = _login(client, "unknown@test.dev")
    wrong = _login(client, "known@test.dev", password="totally-wrong-1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_underage_caregiver_rejected(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "minor-cg@test.dev",
            "password": GOOD_PASSWORD,
            "role": "caregiver",
            "date_of_birth": "2015-01-01",
            "display_name": "minor",
            "consent_accepted": True,
        },
    )
    assert response.status_code == 422


def test_weak_password_rejected(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "weak@test.dev",
            "password": "short1",
            "role": "listener",
            "date_of_birth": "1990-01-01",
            "display_name": "w",
            "consent_accepted": True,
        },
    )
    assert response.status_code == 422
