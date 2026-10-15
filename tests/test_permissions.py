"""Item 2.4 + 2.6: the role-permission matrix, positive AND negative cases."""

import uuid
from datetime import date

import pytest

from app.models import User, UserLink
from app.models.account import LinkKind, UserRole
from app.permissions import (
    can_generate_link_code,
    can_read_listener_sessions,
    can_redeem_link_code,
    is_adult,
)

ADULT_DOB = date(1990, 6, 1)
MINOR_DOB = date(2015, 6, 1)


def make_user(role: UserRole, dob: date | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role.value}+{uuid.uuid4().hex[:6]}@unit.test",
        password_hash="x",
        role=role,
        date_of_birth=dob or (ADULT_DOB if role != UserRole.LISTENER else ADULT_DOB),
        display_name=f"unit-{role.value}",
    )


def link(listener: User, other: User, kind: LinkKind) -> UserLink:
    return UserLink(listener_id=listener.id, authorised_user_id=other.id, kind=kind)


class TestIsAdult:
    @pytest.mark.parametrize(
        "dob,expected",
        [
            (date(2008, 10, 13), True),  # exactly 18 today
            (date(2008, 10, 14), False),  # birthday tomorrow
            (date(1970, 1, 1), True),
            (date(2010, 1, 1), False),
        ],
    )
    def test_boundaries(self, dob, expected):
        assert is_adult(dob, today=date(2026, 10, 13)) is expected


class TestSessionReadMatrix:
    """The PRD's three rules, plus the age rule for therapists."""

    def test_listener_reads_own_sessions(self):
        listener = make_user(UserRole.LISTENER, MINOR_DOB)
        assert can_read_listener_sessions(listener, listener, [])

    def test_child_cannot_read_other_child(self):
        a, b = make_user(UserRole.LISTENER, MINOR_DOB), make_user(UserRole.LISTENER, MINOR_DOB)
        assert not can_read_listener_sessions(a, b, [])

    def test_linked_caregiver_reads_child_sessions(self):
        child, cg = make_user(UserRole.LISTENER, MINOR_DOB), make_user(UserRole.CAREGIVER)
        assert can_read_listener_sessions(cg, child, [link(child, cg, LinkKind.CAREGIVER)])

    def test_unlinked_caregiver_cannot(self):
        child, cg = make_user(UserRole.LISTENER, MINOR_DOB), make_user(UserRole.CAREGIVER)
        assert not can_read_listener_sessions(cg, child, [])

    def test_caregiver_with_wrong_kind_link_cannot(self):
        child, cg = make_user(UserRole.LISTENER, MINOR_DOB), make_user(UserRole.CAREGIVER)
        assert not can_read_listener_sessions(cg, child, [link(child, cg, LinkKind.THERAPIST)])

    def test_linked_therapist_reads_adult_sessions(self):
        adult, th = make_user(UserRole.LISTENER, ADULT_DOB), make_user(UserRole.THERAPIST)
        assert can_read_listener_sessions(th, adult, [link(adult, th, LinkKind.THERAPIST)])

    def test_unlinked_therapist_cannot(self):
        adult, th = make_user(UserRole.LISTENER, ADULT_DOB), make_user(UserRole.THERAPIST)
        assert not can_read_listener_sessions(th, adult, [])

    def test_therapist_never_reads_minor_sessions(self):
        """Fail closed: even a (corruptly created) therapist link to a child is denied."""
        child, th = make_user(UserRole.LISTENER, MINOR_DOB), make_user(UserRole.THERAPIST)
        forged = link(child, th, LinkKind.THERAPIST)
        assert not can_read_listener_sessions(th, child, [forged])

    def test_link_to_different_listener_does_not_help(self):
        victim = make_user(UserRole.LISTENER, MINOR_DOB)
        other = make_user(UserRole.LISTENER, MINOR_DOB)
        cg = make_user(UserRole.CAREGIVER)
        assert not can_read_listener_sessions(cg, victim, [link(other, cg, LinkKind.CAREGIVER)])


class TestCodeGenerationMatrix:
    def test_adult_listener_can_generate_both_kinds(self):
        adult = make_user(UserRole.LISTENER, ADULT_DOB)
        for kind in (LinkKind.CAREGIVER, LinkKind.THERAPIST):
            allowed, _ = can_generate_link_code(adult, kind)
            assert allowed

    def test_minor_listener_only_caregiver(self):
        minor = make_user(UserRole.LISTENER, MINOR_DOB)
        assert can_generate_link_code(minor, LinkKind.CAREGIVER)[0]
        allowed, reason = can_generate_link_code(minor, LinkKind.THERAPIST)
        assert not allowed and "adult" in reason

    def test_non_listeners_cannot_generate(self):
        for role in (UserRole.CAREGIVER, UserRole.THERAPIST):
            allowed, _ = can_generate_link_code(make_user(role), LinkKind.CAREGIVER)
            assert not allowed


class TestRedeemMatrix:
    def test_caregiver_redeems_caregiver_code(self):
        child = make_user(UserRole.LISTENER, MINOR_DOB)
        allowed, _ = can_redeem_link_code(make_user(UserRole.CAREGIVER), LinkKind.CAREGIVER, child)
        assert allowed

    def test_wrong_role_redeemer_rejected(self):
        child = make_user(UserRole.LISTENER, MINOR_DOB)
        allowed, _ = can_redeem_link_code(make_user(UserRole.THERAPIST), LinkKind.CAREGIVER, child)
        assert not allowed

    def test_listener_cannot_redeem(self):
        child = make_user(UserRole.LISTENER, MINOR_DOB)
        allowed, _ = can_redeem_link_code(make_user(UserRole.LISTENER), LinkKind.CAREGIVER, child)
        assert not allowed

    def test_therapist_cannot_redeem_for_minor(self):
        child = make_user(UserRole.LISTENER, MINOR_DOB)
        allowed, _ = can_redeem_link_code(make_user(UserRole.THERAPIST), LinkKind.THERAPIST, child)
        assert not allowed

    def test_therapist_redeems_for_adult(self):
        adult = make_user(UserRole.LISTENER, ADULT_DOB)
        allowed, _ = can_redeem_link_code(make_user(UserRole.THERAPIST), LinkKind.THERAPIST, adult)
        assert allowed

    def test_cannot_link_account_to_itself(self):
        cg = make_user(UserRole.CAREGIVER)
        allowed, _ = can_redeem_link_code(cg, LinkKind.CAREGIVER, cg)
        assert not allowed
