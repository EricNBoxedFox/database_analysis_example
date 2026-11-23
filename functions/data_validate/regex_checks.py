import re
from datetime import datetime
from ipaddress import ip_address
from typing import Optional


# ============================================================
# Regex. Remeber! https://regex101.com/ for testing!!! I should make my own tester someday too.
# ============================================================

EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

PHONE_10_PATTERN = re.compile(
    r"^\d{10}$"
)

PHONE_11_PATTERN = re.compile(
    r"^1\d{10}$"
)

CANADIAN_POSTAL_PATTERN = re.compile(
    r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d$",
    re.IGNORECASE
)

US_ZIP_PATTERN = re.compile(
    r"^\d{5}(-\d{4})?$"
)

URL_PATTERN = re.compile(
    r"^(https?://)?([\w-]+\.)+[a-zA-Z]{2,}(:\d+)?(/.*)?$",
    re.IGNORECASE
)

USERNAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9_]{3,20}$"
)

PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
)

NUMERIC_PATTERN = re.compile(
    r"^-?\d+(\.\d+)?$"
)

ALPHA_PATTERN = re.compile(
    r"^[a-zA-Z]+$"
)

ALPHANUMERIC_PATTERN = re.compile(
    r"^[a-zA-Z0-9]+$"
)


# ============================================================
# Str cleaner
# ============================================================

def _clean(value: object) -> Optional[str]:
    """
    Convert input to a stripped string.

    Returns None for None or empty values.
    """
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


# ============================================================
# Email validation.
# ============================================================

def is_valid_email(value: object) -> bool:
    """
    Validate an email address.

    Example:
        is_valid_email("john@example.com") -> True
    """
    value = _clean(value)

    if not value:
        return False

    return bool(EMAIL_PATTERN.fullmatch(value))


# ============================================================
# TN/phone validation, borrowed from old web hosting storefront side hustle
# ============================================================

def is_valid_phone(
    value: object,
    digits: str = "both"
) -> bool:
    """
    Validate a phone number.

    Args:
        value: Phone number to validate.
        digits:
            "10"   -> Exactly 10 digits.
            "11"   -> Exactly 11 digits beginning with 1.
            "both" -> Accept either format (default).

    Spaces, parentheses, hyphens and periods are ignored.

    Examples:
        is_valid_phone("4035551234") -> True
        is_valid_phone("14035551234") -> True
        is_valid_phone("403-555-1234") -> True
        is_valid_phone("4035551234", digits="10") -> True
    """

    value = _clean(value)

    if not value:
        return False

    if digits not in ("10", "11", "both"):
        raise ValueError("digits must be '10', '11', or 'both'")

    # Remove common phone formatting characters.
    cleaned = re.sub(r"[\s().-]", "", value)

    # Reject anything that isn't a digit after formatting removal.
    if not cleaned.isdigit():
        return False

    if digits == "10":
        return bool(PHONE_10_PATTERN.fullmatch(cleaned))

    if digits == "11":
        return bool(PHONE_11_PATTERN.fullmatch(cleaned))

    return (
        bool(PHONE_10_PATTERN.fullmatch(cleaned))
        or bool(PHONE_11_PATTERN.fullmatch(cleaned))
    )


# ============================================================
# postal code / zip code va;idation, borrowed from old web hosting storefront side hustle
# ============================================================

def is_valid_postal_code(value: object) -> bool:
    """
    Validate a Canadian postal code.

    Examples:
        A1A 1A1 -> True
        A1A1A1  -> True
    """
    value = _clean(value)

    if not value:
        return False

    return bool(CANADIAN_POSTAL_PATTERN.fullmatch(value))


def is_valid_zip_code(value: object) -> bool:
    """
    Validate a US ZIP code.

    Examples:
        90210       -> True
        90210-1234  -> True
    """
    value = _clean(value)

    if not value:
        return False

    return bool(US_ZIP_PATTERN.fullmatch(value))


# ============================================================
# URL VALIDATION
# ============================================================

def is_valid_url(value: object) -> bool:
    """
    Basic URL format validation.

    Accepts URLs with or without http:// or https://.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(URL_PATTERN.fullmatch(value))


# ============================================================
# IP ADDRESS VALIDATION
# ============================================================

def is_valid_ip(value: object) -> bool:
    """
    Validate IPv4 or IPv6 addresses.
    """
    value = _clean(value)

    if not value:
        return False

    try:
        ip_address(value)
        return True
    except ValueError:
        return False


# ============================================================
# DATE VALIDATION
# ============================================================

def is_valid_date(
    value: object,
    date_format: str = "%Y-%m-%d"
) -> bool:
    """
    Validate a date against a specified format.

    Default format: YYYY-MM-DD

    Examples:
        is_valid_date("2026-11-22") -> True
        is_valid_date("22/11/2026", "%d/%m/%Y") -> True
    """
    value = _clean(value)

    if not value:
        return False

    try:
        datetime.strptime(value, date_format)
        return True
    except ValueError:
        return False


# ============================================================
# valid username check (This is really old, was used when I ran private game servers)
# ============================================================

def is_valid_username(value: object) -> bool:
    """
    Username must:
        - Be 3-20 characters.
        - Contain only letters, numbers, and underscores.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(USERNAME_PATTERN.fullmatch(value))


# ============================================================
# strong password check (This is really old, was used when I ran private game servers)
# ============================================================

def is_valid_password(value: object) -> bool:
    """
    Password must:
        - Have at least 8 characters.
        - Have at least one uppercase letter.
        - Have at least one lowercase letter.
        - Have at least one number.
        - Have at least one special character.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(PASSWORD_PATTERN.fullmatch(value))


# ============================================================
# Generic str checks, useful for checking if invalid mix of characters is present.
# ============================================================

def is_numeric(value: object) -> bool:
    """
    Validate integer or decimal numeric strings.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(NUMERIC_PATTERN.fullmatch(value))


def is_alpha(value: object) -> bool:
    """
    Validate strings containing only letters.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(ALPHA_PATTERN.fullmatch(value))


def is_alphanumeric(value: object) -> bool:
    """
    Validate strings containing only letters and numbers.
    """
    value = _clean(value)

    if not value:
        return False

    return bool(ALPHANUMERIC_PATTERN.fullmatch(value))
