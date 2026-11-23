from typing import Any


def _is_empty(value: Any) -> bool:
    """Check if a value is considered empty."""

    if value is None:
        return True

    if isinstance(value, str) and value.strip() == "":
        return True

    return False


def is_required(
    value: Any,
    column_name: str = "column"
) -> dict:
    """
    Check that a required field has a non-empty value.

    Returns:
        {"valid": bool, "reason": str}
    """

    if _is_empty(value):
        return {
            "valid": False,
            "reason": f"{column_name} is required but empty"
        }

    return {"valid": True, "reason": ""}


def is_not_null(
    value: Any,
    column_name: str = "column",
    allow_empty_string: bool = False
) -> dict:
    """
    Check that a field is not null. Empty strings may be allowed.

    Args:
        value: Value to check.
        column_name: Name of the column for error messages.
        allow_empty_string: If True, empty string passes (only None fails).

    Returns:
        {"valid": bool, "reason": str}
    """

    if value is None:
        return {
            "valid": False,
            "reason": f"{column_name} must not be null"
        }

    if not allow_empty_string and isinstance(value, str) and value.strip() == "":
        return {
            "valid": False,
            "reason": f"{column_name} is empty"
        }

    return {"valid": True, "reason": ""}
