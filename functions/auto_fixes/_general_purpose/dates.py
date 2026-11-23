"""Generic date auto-fixes: sentinel date clearing (nullable columns only)."""

SENTINEL_VALUES = {"1900-01-01", "2099-12-31", "0000-00-00"}


def fix_sentinel_dates(row, date_columns=None):
    if date_columns is None:
        date_columns = ["birth_date", "signup_date"]
    changes = {}
    for col in date_columns:
        value = str(row.get(col, "")).strip()
        if value in SENTINEL_VALUES:
            changes[col] = None
    if changes:
        return {"fixed": True, "changes": changes,
                "reason": f"Sentinel dates cleared: {list(changes.keys())}"}
    return {"fixed": False, "changes": {}, "reason": ""}