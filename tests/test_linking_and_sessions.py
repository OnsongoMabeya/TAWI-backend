"""Item 2.7: the listener → caregiver link → session-read integration scenario."""

GOOD_PASSWORD = "correct-horse-battery-99"


def _register(client, email, role, dob, **overrides):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": GOOD_PASSWORD,
            "role": role,
            "date_of_birth": dob,
            "display_name": email.split("@")[0],
            "consent_accepted": True,
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _bearer(body):
    return {"Authorization": f"Bearer {body['tokens']['access_token']}"}


def _mint_code(client, tokens, grants):
    response = client.post("/users/me/link-codes", json={"grants": grants}, headers=tokens)
    assert response.status_code == 201, response.text
    return response.json()


def _redeem(client, tokens, code):
    return client.post("/links/redeem", json={"code": code}, headers=tokens)


class TestCaregiverChildFlow:
    def test_full_scenario(self, client):
        # --- 2.7 verbatim: create Listener -> link Caregiver -> read -> unrelated cannot
        child = _register(client, "child@test.dev", "listener", "2016-03-15")
        caregiver = _register(client, "cg@test.dev", "caregiver", "1985-06-20")
        minion = _register(client, "cg-unrelated@test.dev", "caregiver", "1983-02-14")

        code = _mint_code(client, _bearer(child), "caregiver")
        redeemed = _redeem(client, _bearer(caregiver), code["code"])
        assert redeemed.status_code == 201
        assert redeemed.json()["listener_id"] == child["user"]["id"]
        assert redeemed.json()["kind"] == "caregiver"

        child_id = child["user"]["id"]
        allowed = client.get(f"/users/{child_id}/sessions", headers=_bearer(caregiver))
        assert allowed.status_code == 200
        assert allowed.json() == {"listener_id": child_id, "sessions": []}

        denied = client.get(f"/users/{child_id}/sessions", headers=_bearer(minion))
        assert denied.status_code == 404  # 404, not 403: account existence is not leakable

    def test_child_cannot_read_another_child(self, client):
        a = _register(client, "child-a@test.dev", "listener", "2016-01-01")
        b = _register(client, "child-b@test.dev", "listener", "2017-01-01")
        denied = client.get(f"/users/{a['user']['id']}/sessions", headers=_bearer(b))
        assert denied.status_code == 404

    def test_codes_are_one_time(self, client):
        child = _register(client, "child-code@test.dev", "listener", "2016-01-01")
        cg1 = _register(client, "cg1@test.dev", "caregiver", "1985-01-01")
        cg2 = _register(client, "cg2@test.dev", "caregiver", "1986-01-01")
        code = _mint_code(client, _bearer(child), "caregiver")

        assert _redeem(client, _bearer(cg1), code["code"]).status_code == 201
        assert _redeem(client, _bearer(cg2), code["code"]).status_code == 409

    def test_unknown_code_404(self, client):
        cg = _register(client, "cg-unknown@test.dev", "caregiver", "1985-01-01")
        assert _redeem(client, _bearer(cg), "ZZZZ-ZZZZ").status_code == 404

    def test_caregiver_cannot_generate_codes(self, client):
        cg = _register(client, "cg-gen@test.dev", "caregiver", "1985-01-01")
        response = client.post(
            "/users/me/link-codes", json={"grants": "caregiver"}, headers=_bearer(cg)
        )
        assert response.status_code == 403

    def test_therapist_rules(self, client):
        child = _register(client, "child-th@test.dev", "listener", "2017-01-01")
        adult = _register(client, "adult-th@test.dev", "listener", "1990-01-01")
        therapist = _register(client, "th@test.dev", "therapist", "1980-01-10")
        th_headers = _bearer(therapist)

        # minor listeners cannot mint therapist codes at all
        blocked = client.post(
            "/users/me/link-codes", json={"grants": "therapist"}, headers=_bearer(child)
        )
        assert blocked.status_code == 403

        # adult -> therapist link -> therapist reads adult's sessions
        code = _mint_code(client, _bearer(adult), "therapist")
        assert _redeem(client, th_headers, code["code"]).status_code == 201
        ok = client.get(f"/users/{adult['user']['id']}/sessions", headers=th_headers)
        assert ok.status_code == 200 and ok.json()["sessions"] == []

        # but the therapist still cannot read a random child
        denied = client.get(f"/users/{child['user']['id']}/sessions", headers=th_headers)
        assert denied.status_code == 404

    def test_malformed_code_rejected_at_422(self, client):
        cg = _register(client, "cg-mal@test.dev", "caregiver", "1985-01-01")
        assert _redeem(client, _bearer(cg), "not a code!!").status_code == 422
