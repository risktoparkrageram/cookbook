import pytest

from cookbook.passwords import hash_password, verify_password


def test_a_hashed_password_verifies_and_another_does_not() -> None:
    stored = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", stored) is True
    assert verify_password("correct horse battery stapler", stored) is False


def test_hashing_the_same_password_twice_uses_different_salts() -> None:
    assert hash_password("same password") != hash_password("same password")


def test_hash_records_the_scheme_and_cost_parameters() -> None:
    assert hash_password("x").startswith("scrypt$32768$8$1$")


@pytest.mark.parametrize(
    "stored",
    ["", "plain-text-password", "bcrypt$12$abc$def$ghi$jkl", "scrypt$32768$8$1$not base64!$xyz"],
)
def test_a_malformed_stored_hash_never_matches(stored: str) -> None:
    assert verify_password("anything", stored) is False
