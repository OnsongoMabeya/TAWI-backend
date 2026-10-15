"""Item 2.6, part 1: password hashing."""

import re

import pytest

from app.security.passwords import (
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)


def test_round_trip():
    digest = hash_password("correct-horse-battery-99")
    assert verify_password("correct-horse-battery-99", digest)
    assert not verify_password("correct-horse-battery-98", digest)


def test_same_password_hashes_differ():
    assert hash_password("same") != hash_password("same")


def test_hash_is_argon2id_with_expected_parameters():
    digest = hash_password("parameters")
    parsed = re.fullmatch(r"\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$.+", digest)
    assert parsed is not None
    memory, time_cost, parallelism = (int(g) for g in parsed.groups())
    assert memory == 64 * 1024
    assert time_cost == 3
    assert parallelism == 1


def test_current_hash_needs_no_rehash():
    assert not needs_rehash(hash_password("current"))


def test_weaker_hash_is_flagged_for_rehash():
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash("weak")
    assert needs_rehash(weak)
    assert verify_password("weak", weak)  # still verifiable, so users log in and get upgraded


def test_bad_hash_strings_fail_closed():
    assert not verify_password("any", "not-a-hash")
    assert not verify_password("any", "")


@pytest.mark.parametrize(
    "password,violated",
    [
        ("short", True),
        ("a" * 11, True),
        ("a" * 12, True),  # long enough but no digit
        ("123456789012", True),  # digits only
        ("lettersanddigit1", False),
        ("correct-horse-battery-99", False),
        ("            ", True),  # whitespace only
        ("a1" * 65, True),  # over max length
    ],
)
def test_strength_rules(password, violated):
    assert bool(validate_password_strength(password)) is violated
