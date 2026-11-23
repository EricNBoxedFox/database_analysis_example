"""Generic text auto-fixes: placeholder email/country, placeholder clearing, missing values."""

import re

PLACEHOLDER_VALUES = {"", "N/A", "UNKNOWN", "ERROR", "null", "None", "NULL"}


def fix_placeholder_email(row):
    email = str(row.get("email", "")).strip()
    customer_id = row.get("customer_id")
    name = str(row.get("full_name", "")).strip()

    if email not in PLACEHOLDER_VALUES and "@" in email and "." in email.split("@")[-1]:
        return {"fixed": False, "column": "email", "new_value": email, "reason": ""}

    clean = re.sub(r"^(Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s*", "", name, flags=re.IGNORECASE)
    clean = re.sub(r"\s+(MD|PhD|Jr\.|Sr\.|II|III)$", "", clean, flags=re.IGNORECASE)
    clean = clean.strip().lower().replace(" ", ".").replace("-", "")
    clean = re.sub(r"[^a-z0-9.]", "", clean)

    if not clean:
        clean = "customer"

    new_email = f"{clean}{customer_id}@example.com"
    return {"fixed": True, "column": "email", "new_value": new_email,
            "reason": f"Placeholder email '{email}' replaced with {new_email}"}


def fix_placeholder_country(row):
    country = str(row.get("country", "")).strip()
    city = str(row.get("city", "")).strip()

    if country not in PLACEHOLDER_VALUES:
        return {"fixed": False, "column": "country", "new_value": country, "reason": ""}

    city_country_map = {
        "Houston": "United States", "New York": "United States",
        "Los Angeles": "United States", "Seattle": "United States",
        "Chicago": "United States", "London": "United Kingdom",
        "Leeds": "United Kingdom", "Paris": "France",
        "Marseille": "France", "Berlin": "Germany",
        "Hamburg": "Germany", "Frankfurt": "Germany",
        "Cologne": "Germany", "Calgary": "Canada",
        "Vancouver": "Canada", "Rotterdam": "Netherlands",
        "Madrid": "Spain", "Seville": "Spain",
        "Rome": "Italy", "Milan": "Italy",
        "Sydney": "Australia", "Brisbane": "Australia",
        "Melbourne": "Australia",
    }

    if city in city_country_map:
        new_country = city_country_map[city]
        return {"fixed": True, "column": "country", "new_value": new_country,
                "reason": f"Country derived from city {city}: {new_country}"}

    return {"fixed": False, "column": "country", "new_value": country,
            "reason": f"Cannot fix country: no mapping for city '{city}'"}


def fix_invalid_emails(row):
    # Alias for fix_placeholder_email for backward compatibility
    return fix_placeholder_email(row)


def fix_missing_values(row, column_defaults=None):
    if column_defaults is None:
        column_defaults = {}
    changes = {}
    for col, default_val in column_defaults.items():
        value = row.get(col)
        if value is None or (isinstance(value, str) and value.strip() in PLACEHOLDER_VALUES):
            changes[col] = default_val
    if changes:
        return {"fixed": True, "changes": changes,
                "reason": f"Missing values filled: {list(changes.keys())}"}
    return {"fixed": False, "changes": {}, "reason": ""}