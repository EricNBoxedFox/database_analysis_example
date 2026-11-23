from typing import Any


def check_enum_value(
    value: Any,
    allowed_values: list | set,
    column_name: str = "column",
    case_sensitive: bool = True
) -> dict:
    """
    Check that a value is in an allowed set of values.

    Args:
        value: Value to check.
        column_name: Name of the column for error messages.
        allowed_values: List or set of acceptable values.
        case_sensitive: If False, compare lowercased strings.

    Returns:
        {"valid": bool, "reason": str}
    """

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return {"valid": True, "reason": ""}

    check_value = str(value).strip()

    if not case_sensitive:
        check_value = check_value.lower()
        allowed_set = {str(v).lower() for v in allowed_values}
    else:
        allowed_set = set(str(v) for v in allowed_values)

    if check_value not in allowed_set:
        return {
            "valid": False,
            "reason": f"{column_name} value '{value}' is not in allowed values: {allowed_values}"
        }

    return {"valid": True, "reason": ""}
