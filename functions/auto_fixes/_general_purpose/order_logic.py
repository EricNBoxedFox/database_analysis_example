"""Generic order logic auto-fixes: impossible status/date combos, sentinel order dates."""


def fix_impossible_status_dates(row):
    status = str(row.get("status", "")).strip().lower()
    ship_date = row.get("ship_date")
    ship_empty = ship_date is None or (isinstance(ship_date, str) and ship_date.strip() == "")
    if status in ("delivered", "shipped") and ship_empty:
        return {"fixed": True, "changes": {"status": "pending"},
                "reason": f"Status '{status}' changed to 'pending' (no ship_date)"}
    return {"fixed": False, "changes": {}, "reason": ""}


def fix_sentinel_order_dates(row):
    changes = {}
    for col in ["order_date", "ship_date"]:
        val = str(row.get(col, "")).strip()
        if val in ("1900-01-01", "2099-12-31", "0000-00-00", "2100-02-23"):
            changes[col] = None
    if changes:
        return {"fixed": True, "changes": changes,
                "reason": f"Sentinel dates cleared: {list(changes.keys())}"}
    return {"fixed": False, "changes": {}, "reason": ""}