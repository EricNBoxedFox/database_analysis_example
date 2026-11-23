from datetime import datetime
from typing import Any


def _parse_date(value: Any, fmt: str = "%Y-%m-%d") -> datetime | None:
    """Parse a date string, returning None for empty values."""

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None

    try:
        return datetime.strptime(str(value).strip(), fmt)
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    """Convert to float, returning None for empty values."""

    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def line_total_matches_calculation(
    row: dict,
    quantity_column: str = "quantity",
    price_column: str = "unit_price",
    total_column: str = "line_total",
    tolerance: float = 0.01
) -> dict:
    """
    Check that line_total equals quantity * unit_price within tolerance.

    Returns:
        {"valid": bool, "reason": str}
    """

    qty = _to_float(row.get(quantity_column))
    price = _to_float(row.get(price_column))
    total = _to_float(row.get(total_column))

    if qty is None or price is None or total is None:
        return {"valid": True, "reason": ""}

    expected = qty * price

    if abs(total - expected) > tolerance:
        return {
            "valid": False,
            "reason": (
                f"{total_column} ({total}) does not match "
                f"{quantity_column} x {price_column} ({expected:.2f})"
            )
        }

    return {"valid": True, "reason": ""}

# ============================================================
# Borrowed and modified from old store hosting code. I haven't validated this on anything modern.
# Had a customer who insisted on doing manual shipping entries so I used this to validate their entries.
# ============================================================
def ship_date_after_order_date(
    row: dict,
    order_date_column: str = "order_date",
    ship_date_column: str = "ship_date"
) -> dict:
    """
    Check that ship_date is after (or equal to) order_date when present.

    Returns:
        {"valid": bool, "reason": str}
    """

    order_dt = _parse_date(row.get(order_date_column))
    ship_dt = _parse_date(row.get(ship_date_column))

    if ship_dt is None:
        return {"valid": True, "reason": ""}

    if order_dt is None:
        return {
            "valid": False,
            "reason": f"{order_date_column} is missing but {ship_date_column} is set"
        }

    if ship_dt < order_dt:
        return {
            "valid": False,
            "reason": (
                f"{ship_date_column} ({ship_dt.date()}) is before "
                f"{order_date_column} ({order_dt.date()})"
            )
        }

    return {"valid": True, "reason": ""}


def delivered_requires_ship_date(
    row: dict,
    status_column: str = "status",
    ship_date_column: str = "ship_date",
    statuses_requiring_ship: list[str] | None = None
) -> dict:
    """
    Check that orders with certain statuses have a ship_date.

    Returns:
        {"valid": bool, "reason": str}
    """

    if statuses_requiring_ship is None:
        statuses_requiring_ship = ["shipped", "delivered"]

    status = row.get(status_column)

    if not status or str(status).strip().lower() not in [s.lower() for s in statuses_requiring_ship]:
        return {"valid": True, "reason": ""}

    ship_dt = _parse_date(row.get(ship_date_column))

    if ship_dt is None:
        return {
            "valid": False,
            "reason": (
                f"{status_column} is '{status}' but {ship_date_column} is empty"
            )
        }

    return {"valid": True, "reason": ""}


def end_date_after_start_date(
    row: dict,
    start_column: str = "start_date",
    end_column: str = "end_date"
) -> dict:
    """
    Check that end_date is after (or equal to) start_date when both are present.

    Returns:
        {"valid": bool, "reason": str}
    """

    start_dt = _parse_date(row.get(start_column))
    end_dt = _parse_date(row.get(end_column))

    if start_dt is None or end_dt is None:
        return {"valid": True, "reason": ""}

    if end_dt < start_dt:
        return {
            "valid": False,
            "reason": (
                f"{end_column} ({end_dt.date()}) is before "
                f"{start_column} ({start_dt.date()})"
            )
        }

    return {"valid": True, "reason": ""}
