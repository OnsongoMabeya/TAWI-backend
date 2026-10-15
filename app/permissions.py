"""Role-permission matrix (Phase 2 item 2.4).

These functions are deliberately pure — they take plain values, do no I/O, and
get their entire matrix covered by unit tests in tests/test_permissions.py,
both positive and negative cases. FastAPI dependencies in app/deps.py are thin
wrappers around them.

The PRD's three rules, verbatim:
    1. A Caregiver can read a linked child's data.
    2. A child cannot read another child's data.
    3. A Therapist can only read data explicitly shared. (Phase 2 ships the link
        as the sharing boundary explicitly scoped to the therapist; the
        shrink-to-a-subset "sharing" of Phase 8 narrows this further later.)
"""

from datetime import date

from app.models import User, UserLink
from app.models.account import LinkKind, UserRole

ADULT_AGE_YEARS = 18


def is_adult(date_of_birth: date, *, today: date | None = None) -> bool:
    """Age at `today` in whole years, calendar-correct across Feb 29."""
    today = today or date.today()
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years >= ADULT_AGE_YEARS


def can_read_own_data(requester: User, subject_id) -> bool:
    return requester.id == subject_id


def _has_active_link(
    links: list[UserLink], requester_id, listener_id, kind: LinkKind | None
) -> bool:
    return any(
        link.authorised_user_id == requester_id
        and link.listener_id == listener_id
        and (kind is None or link.kind == kind)
        for link in links
    )


def can_read_listener_sessions(
    requester: User, listener: User, links: list[UserLink], *, today: date | None = None
) -> bool:
    """Rule set for reading a listener's session list:
    - the listener themself (any age);
    - a linked caregiver of that listener (PRD: caregivers manage child accounts);
    - a linked therapist only if the listener is an adult (PRD rule 3;
        phase item 2.5: therapists link to adult users only).
    The DOB check is repeated here — fail closed even if the link table were ever corrupted."""
    if requester.id == listener.id:
        return True
    if requester.role == UserRole.CAREGIVER:
        return _has_active_link(links, requester.id, listener.id, LinkKind.CAREGIVER)
    if requester.role == UserRole.THERAPIST:
        return _has_active_link(links, requester.id, listener.id, LinkKind.THERAPIST) and is_adult(
            listener.date_of_birth, today=today
        )
    return False


def can_generate_link_code(
    user: User, grants_kind: LinkKind, *, today: date | None = None
) -> tuple[bool, str | None]:
    """Who may mint which pairing codes.
    - only listeners grant access to their own data (rules 1 and 2 + enumeration defence);
    - a minor listener may only hand out caregiver codes;
    - an adult listener may hand out caregiver or therapist codes."""
    if user.role != UserRole.LISTENER:
        return False, "only listener accounts can grant access to their data"
    if grants_kind == LinkKind.THERAPIST and not is_adult(user.date_of_birth, today=today):
        return False, "only adult listeners can invite a therapist"
    return True, None


def can_redeem_link_code(
    redeemer: User, grants_kind: LinkKind, listener: User, *, today: date | None = None
) -> tuple[bool, str | None]:
    """Re-deem checks, enforced again at the redeem endpoint — codes must
    not be a way to smuggle an invalid pairing past the generation rules."""
    expected = {LinkKind.CAREGIVER: UserRole.CAREGIVER, LinkKind.THERAPIST: UserRole.THERAPIST}[
        grants_kind
    ]
    if redeemer.role != expected:
        return False, f"this code must be redeemed by a {expected.value} account"
    if redeemer.id == listener.id:
        return False, "cannot link an account to itself"
    if listener.role != UserRole.LISTENER:
        return False, "codes can only be redeemed against listener accounts"
    if grants_kind == LinkKind.THERAPIST and not is_adult(listener.date_of_birth, today=today):
        return False, "therapist links require an adult listener"
    return True, None
