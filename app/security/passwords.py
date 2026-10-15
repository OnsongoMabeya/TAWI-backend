from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

# OWASP-recommended argon2id parameters. Kept explicitly (not library defaults)
# so the values are visible and unit-tested — see tests/test_passwords.py.
Hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def hash_password(password: str) -> str:
    return Hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return Hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        # Wrong password, malformed PHC string, parameters argon2 won't accept —
        # every failure mode is "does not verify", never an exception to the caller.
        # (InvalidHashError subclasses ValueError, not Argon2Error.)
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash was made with weaker parameters than current."""
    return Hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> list[str]:
    """Return a list of violations; empty list means acceptable."""
    violations: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        violations.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        violations.append(f"must be at most {MAX_PASSWORD_LENGTH} characters")
    elif not password.strip():
        violations.append("must not be blank")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        violations.append("must contain at least one letter and one digit")
    return violations
