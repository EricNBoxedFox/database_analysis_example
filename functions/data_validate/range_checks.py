from datetime import date, datetime
from typing import Any


def check_numeric_range(
    value: Any,
    column_name: str = "column",
    min_val: float | None = None,
    max_val: float | None = None,
    inclusive_min: bool = True,
    inclusive_max: bool = True
) -> dict:
    """
    Check that a numeric value falls within a range.

    Returns:
        {"valid": bool, "reason": str}
    """

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return {"valid": True, "reason": ""}

    try:
        num = float(value)
    except (ValueError, TypeError):
        return {
            "valid": False,
            "reason": f"{column_name} is not numeric: {value}"
        }

    if min_val is not None:
        if inclusive_min and num < min_val:
            return {
                "valid": False,
                "reason": f"{column_name} ({num}) is below minimum ({min_val})"
            }
        if not inclusive_min and num <= min_val:
            return {
                "valid": False,
                "reason": f"{column_name} ({num}) must be greater than {min_val}"
            }

    if max_val is not None:
        if inclusive_max and num > max_val:
            return {
                "valid": False,
                "reason": f"{column_name} ({num}) exceeds maximum ({max_val})"
            }
        if not inclusive_max and num >= max_val:
            return {
                "valid": False,
                "reason": f"{column_name} ({num}) must be less than {max_val}"
            }

    return {"valid": True, "reason": ""}


def check_date_range(
    value: Any,
    column_name: str = "column",
    min_date: str | date | None = None,
    max_date: str | date | None = None,
    date_format: str = "%Y-%m-%d"
) -> dict:
    """
    Check that a date value falls within a range.

    Args:
        value: Date string or date object to check.
        column_name: Name of the column for error messages.
        min_date: Minimum allowed date (string in date_format, date object, or "today").
        max_date: Maximum allowed date (string in date_format, date object, or "today").
        date_format: Format string for parsing date strings.

    Returns:
        {"valid": bool, "reason": str}
    """

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return {"valid": True, "reason": ""}

    try:
        if isinstance(value, date):
            check_date = value
        else:
            check_date = datetime.strptime(str(value).strip(), date_format).date()
    except ValueError:
        return {
            "valid": False,
            "reason": f"{column_name} is not a valid date ({date_format}): {value}"
        }

    if min_date is not None:
        if min_date == "today":
            lower = date.today()
        elif isinstance(min_date, str):
            lower = datetime.strptime(min_date, date_format).date()
        else:
            lower = min_date

        if check_date < lower:
            return {
                "valid": False,
                "reason": f"{column_name} ({check_date}) is before minimum ({lower})"
            }

    if max_date is not None:
        if max_date == "today":
            upper = date.today()
        elif isinstance(max_date, str):
            upper = datetime.strptime(max_date, date_format).date()
        else:
            upper = max_date

        if check_date > upper:
            return {
                "valid": False,
                "reason": f"{column_name} ({check_date}) is after maximum ({upper})"
            }

    return {"valid": True, "reason": ""}


def check_string_length(
    value: Any,
    column_name: str = "column",
    min_len: int | None = None,
    max_len: int | None = None
) -> dict:
    """
    Check that a string's length falls within bounds.

    Returns:
        {"valid": bool, "reason": str}
    """

    if value is None:
        return {"valid": True, "reason": ""}

    text = str(value).strip()

    if not text:
        return {"valid": True, "reason": ""}

    length = len(text)

    if min_len is not None and length < min_len:
        return {
            "valid": False,
            "reason": f"{column_name} length ({length}) is below minimum ({min_len})"
        }

    if max_len is not None and length > max_len:
        return {
            "valid": False,
            "reason": f"{column_name} length ({length}) exceeds maximum ({max_len})"
        }

    return {"valid": True, "reason": ""}
