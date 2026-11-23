import re
from typing import Any


UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

CURRENCY_PATTERN = re.compile(
    r"^[-+]?\d{1,3}(,\d{3})*(\.\d{1,2})?$|^[-+]?\d+(\.\d{1,2})?$"
)


def _clean(value: Any) -> str | None:
    """Convert to stripped string, return None for empty."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def is_valid_uuid(
    value: Any,
    column_name: str = "column"
) -> dict:
    """
    Check that a value is a valid UUID format (v1-v5 compatible pattern).

    Returns:
        {"valid": bool, "reason": str}
    """

    text = _clean(value)

    if text is None:
        return {"valid": True, "reason": ""}

    if not UUID_PATTERN.fullmatch(text):
        return {
            "valid": False,
            "reason": f"{column_name} is not a valid UUID format"
        }

    return {"valid": True, "reason": ""}


def is_valid_currency(
    value: Any,
    column_name: str = "column",
    allow_negative: bool = True
) -> dict:
    """
    Check that a value looks like a currency amount.

    Returns:
        {"valid": bool, "reason": str}
    """

    text = _clean(value)

    if text is None:
        return {"valid": True, "reason": ""}

    # Remove commas for numeric check
    cleaned = text.replace(",", "")

    try:
        num = float(cleaned)
    except ValueError:
        return {
            "valid": False,
            "reason": f"{column_name} is not a valid currency value"
        }

    if not allow_negative and num < 0:
        return {
            "valid": False,
            "reason": f"{column_name} cannot be negative"
        }

    # Check decimal places (max 2 for currency)
    if "." in cleaned:
        decimals = len(cleaned.split(".")[1])
        if decimals > 2:
            return {
                "valid": False,
                "reason": f"{column_name} has too many decimal places"
            }

    return {"valid": True, "reason": ""}


def is_valid_percentage(
    value: Any,
    column_name: str = "column",
    min_val: float = 0.0,
    max_val: float = 100.0
) -> dict:
    """
    Check that a value is a valid percentage (default range 0-100).

    Returns:
        {"valid": bool, "reason": str}
    """

    text = _clean(value)

    if text is None:
        return {"valid": True, "reason": ""}

    # Strip percent sign if present
    check_text = text.rstrip("%")

    try:
        num = float(check_text)
    except ValueError:
        return {
            "valid": False,
            "reason": f"{column_name} is not a valid percentage"
        }

    if num < min_val or num > max_val:
        return {
            "valid": False,
            "reason": f"{column_name} ({num}) is outside range [{min_val}, {max_val}]"
        }

    return {"valid": True, "reason": ""}


def is_boolean_like(
    value: Any,
    column_name: str = "column"
) -> dict:
    """
    Check that a value represents a boolean-like value.

    Accepts: true/false, yes/no, 1/0, on/off (case-insensitive).

    Returns:
        {"valid": bool, "reason": str}
    """

    if isinstance(value, bool):
        return {"valid": True, "reason": ""}

    text = _clean(value)

    if text is None:
        return {"valid": True, "reason": ""}

    lower = text.lower()

    valid_values = {"true", "false", "yes", "no", "1", "0", "on", "off"}

    if lower not in valid_values:
        return {
            "valid": False,
            "reason": f"{column_name} is not a boolean-like value"
        }

    return {"valid": True, "reason": ""}
