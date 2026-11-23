from typing import Any


def _to_float(value: Any) -> float | None:
    """Convert to float, returning None for non-numeric values."""

    if value is None:
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def detect_outliers_zscore(
    values: list[Any],
    column_name: str = "column",
    threshold: float = 3.0
) -> dict:
    """
    Detect outliers using z-score method.

    Args:
        values: List of numeric values to analyze.
        column_name: Name of the column for reporting.
        threshold: Z-score threshold for outlier detection (default 3).

    Returns:
        {
            "valid": bool,
            "reason": str,
            "outlier_count": int,
            "outliers": list[{"index": int, "value": float, "z_score": float}]
        }
    """

    numeric_values = []

    for i, v in enumerate(values):
        f = _to_float(v)
        if f is not None:
            numeric_values.append((i, f))

    if len(numeric_values) < 3:
        return {
            "valid": True,
            "reason": "",
            "outlier_count": 0,
            "outliers": []
        }

    n = len(numeric_values)
    mean = sum(v for _, v in numeric_values) / n

    variance = sum((v - mean) ** 2 for _, v in numeric_values) / n
    std_dev = variance ** 0.5

    if std_dev == 0:
        return {
            "valid": True,
            "reason": "",
            "outlier_count": 0,
            "outliers": []
        }

    outliers = []

    for idx, val in numeric_values:
        z_score = (val - mean) / std_dev

        if abs(z_score) > threshold:
            outliers.append({
                "index": idx,
                "value": val,
                "z_score": round(z_score, 4)
            })

    return {
        "valid": len(outliers) == 0,
        "reason": (
            f"{column_name} has {len(outliers)} outlier(s) "
            f"(z-score > {threshold})"
            if outliers
            else ""
        ),
        "outlier_count": len(outliers),
        "outliers": outliers
    }


def detect_outliers_iqr(
    values: list[Any],
    column_name: str = "column",
    multiplier: float = 1.5
) -> dict:
    """
    Detect outliers using Interquartile Range (IQR) method.

    Args:
        values: List of numeric values to analyze.
        column_name: Name of the column for reporting.
        multiplier: IQR multiplier for outlier bounds (default 1.5).

    Returns:
        {
            "valid": bool,
            "reason": str,
            "outlier_count": int,
            "outliers": list[{"index": int, "value": float}],
            "bounds": {"lower": float, "upper": float}
        }
    """

    numeric_values = []

    for i, v in enumerate(values):
        f = _to_float(v)
        if f is not None:
            numeric_values.append((i, f))

    if len(numeric_values) < 4:
        return {
            "valid": True,
            "reason": "",
            "outlier_count": 0,
            "outliers": [],
            "bounds": {"lower": None, "upper": None}
        }

    sorted_vals = sorted(v for _, v in numeric_values)
    n = len(sorted_vals)

    def percentile(data, p):
        k = (len(data) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        d = k - f
        return data[f] + d * (data[c] - data[f])

    q1 = percentile(sorted_vals, 25)
    q3 = percentile(sorted_vals, 75)
    iqr = q3 - q1

    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr

    outliers = []

    for idx, val in numeric_values:
        if val < lower_bound or val > upper_bound:
            outliers.append({
                "index": idx,
                "value": val
            })

    return {
        "valid": len(outliers) == 0,
        "reason": (
            f"{column_name} has {len(outliers)} outlier(s) "
            f"(IQR bounds: [{lower_bound:.2f}, {upper_bound:.2f}])"
            if outliers
            else ""
        ),
        "outlier_count": len(outliers),
        "outliers": outliers,
        "bounds": {
            "lower": round(lower_bound, 4),
            "upper": round(upper_bound, 4)
        }
    }
