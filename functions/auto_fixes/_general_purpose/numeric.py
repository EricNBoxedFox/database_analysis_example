"""Generic numeric auto-fixes: sign-flip, tenfold detection, zero clamping, recalculation."""


def _fix_sign_flipped_value(value):
    if value is None:
        return None, False
    try:
        num = float(value)
    except (ValueError, TypeError):
        return value, False
    if num < 0:
        return abs(num), True
    return num, False


def _fix_tenfold_for_column(row, column, max_valid, min_valid=None):
    value = row.get(column)
    if value is None:
        return {"fixed": False, "column": column, "new_value": None, "reason": ""}

    try:
        num = float(value)
    except (ValueError, TypeError):
        return {"fixed": False, "column": column, "new_value": value, "reason": ""}

    is_tenfold = False

    if num > max_valid:
        divided = num / 10.0
        if divided <= max_valid and (min_valid is None or divided >= min_valid):
            if abs(num - divided * 10.0) < 0.01:
                is_tenfold = True

    if not is_tenfold and num > max_valid * 5:
        divided = num / 10.0
        if divided <= max_valid and (min_valid is None or divided >= min_valid):
            is_tenfold = True

    if is_tenfold:
        new_value = num / 10.0
        if column in ("unit_price", "line_total"):
            new_value = round(new_value, 2)
        elif new_value == int(new_value):
            new_value = int(new_value)
        return {
            "fixed": True, "column": column, "new_value": new_value,
            "reason": f"Tenfold value {num} divided by 10 -> {new_value}"
        }

    return {"fixed": False, "column": column, "new_value": num, "reason": ""}


def fix_unit_price_sign_flipped(row):
    val, fixed = _fix_sign_flipped_value(row.get("unit_price"))
    return {"fixed": fixed, "column": "unit_price", "new_value": val,
            "reason": f"Sign flipped {row.get('unit_price')} -> {val}" if fixed else ""}


def fix_unit_price_tenfold(row):
    return _fix_tenfold_for_column(row, "unit_price", 500, 0)


def fix_quantity_sign_flipped(row):
    val, fixed = _fix_sign_flipped_value(row.get("quantity"))
    if fixed and val is not None:
        val = int(val) if float(val).is_integer() else val
    return {"fixed": fixed, "column": "quantity", "new_value": val,
            "reason": f"Sign flipped {row.get('quantity')} -> {val}" if fixed else ""}


def fix_quantity_tenfold(row):
    return _fix_tenfold_for_column(row, "quantity", 5, 1)


def fix_quantity_zero(row):
    value = row.get("quantity")
    try:
        num = int(value)
    except (ValueError, TypeError):
        return {"fixed": False, "column": "quantity", "new_value": value, "reason": ""}
    if num == 0:
        return {"fixed": True, "column": "quantity", "new_value": 1,
                "reason": "Zero quantity set to 1"}
    return {"fixed": False, "column": "quantity", "new_value": num, "reason": ""}


def fix_stock_qty_sign_flipped(row):
    val, fixed = _fix_sign_flipped_value(row.get("stock_qty"))
    if fixed and val is not None:
        val = int(val) if float(val).is_integer() else val
    return {"fixed": fixed, "column": "stock_qty", "new_value": val,
            "reason": f"Sign flipped {row.get('stock_qty')} -> {val}" if fixed else ""}


def fix_stock_qty_tenfold(row):
    return _fix_tenfold_for_column(row, "stock_qty", 500, 0)


def fix_line_total_recalc(row):
    try:
        qty = float(row.get("quantity", 0))
        price = float(row.get("unit_price", 0))
    except (ValueError, TypeError):
        return {"fixed": False, "column": "line_total",
                "new_value": row.get("line_total"), "reason": ""}
    if qty == 0 or price == 0:
        return {"fixed": False, "column": "line_total",
                "new_value": row.get("line_total"), "reason": ""}
    expected = round(qty * price, 2)
    try:
        current = float(row.get("line_total", 0))
    except (ValueError, TypeError):
        current = None
    if current is None or abs(current - expected) > 0.011:
        return {"fixed": True, "column": "line_total", "new_value": expected,
                "reason": f"line_total recalculated: {current} -> {expected}"}
    return {"fixed": False, "column": "line_total", "new_value": current, "reason": ""}