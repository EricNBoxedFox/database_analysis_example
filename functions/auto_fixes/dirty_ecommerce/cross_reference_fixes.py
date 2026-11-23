from typing import Any

from functions.db_connectors import DatabaseConnection, select_data, update_data


def fix_order_country_from_customer(
    connection: DatabaseConnection,
    source_table: str,
    target_table: str = None,
    run_id: str = None,
    changelog_table: str = "change_log"
) -> dict:
    """
    Fix orders.country to match customers.country using SQL JOIN.

    Updates orders where country is placeholder/empty/mismatched.

    Returns:
        {"fixed": int, "rows_changed": int}
    """

    if target_table is None:
        target_table = source_table

    # Find orders where country doesn't match customer's country
    query = f"""
        SELECT o.order_id, o.country as order_country,
               c.country as customer_country
        FROM "{target_table}" o
        JOIN autofix_stagging_customers c ON c.customer_id = o.customer_id
        WHERE o.country <> c.country
           OR o.country IS NULL
           OR o.country IN ('', 'N/A', 'UNKNOWN', 'ERROR')
    """

    try:
        rows = select_data(connection, query)
    except Exception:
        # Fallback for non-rowid databases
        query = f"""
            SELECT o.order_id, o.country as order_country,
                   c.country as customer_country
            FROM "{target_table}" o
            JOIN autofix_stagging_customers c ON c.customer_id = o.customer_id
            WHERE o.country <> c.country
               OR o.country IS NULL
               OR o.country IN ('', 'N/A', 'UNKNOWN', 'ERROR')
        """
        rows = select_data(connection, query)

    if not rows:
        return {"fixed": 0, "rows_changed": 0}

    fixed_count = 0

    for row in rows:
        order_id = row["order_id"]
        customer_country = row["customer_country"]

        if not customer_country:
            continue

        update_query = f'UPDATE "{target_table}" SET country = ? WHERE order_id = ?'
        update_data(connection, update_query, (customer_country, order_id))
        fixed_count += 1

    return {"fixed": fixed_count, "rows_changed": fixed_count}


def fix_order_items_price_from_product(
    connection: DatabaseConnection,
    source_table: str,
    target_table: str = None,
    run_id: str = None,
    changelog_table: str = "change_log"
) -> dict:
    """
    Fix order_items.unit_price to match products.unit_price using SQL JOIN.

    Only fixes when the difference is significant (more than rounding).

    Returns:
        {"fixed": int, "rows_changed": int}
    """

    if target_table is None:
        target_table = source_table

    # Find order_items where unit_price doesn't match product's price
    query = f"""
        SELECT oi.order_item_id, oi.unit_price as item_price,
               p.unit_price as product_price
        FROM "{target_table}" oi
        JOIN autofix_stagging_products p ON p.product_id = oi.product_id
        WHERE ABS(oi.unit_price - p.unit_price) > 0.005
    """

    rows = select_data(connection, query)

    if not rows:
        return {"fixed": 0, "rows_changed": 0}

    fixed_count = 0

    for row in rows:
        item_id = row["order_item_id"]
        product_price = row["product_price"]

        if product_price is None:
            continue

        update_query = f'UPDATE "{target_table}" SET unit_price = ? WHERE order_item_id = ?'
        update_data(connection, update_query, (product_price, item_id))
        fixed_count += 1

    return {"fixed": fixed_count, "rows_changed": fixed_count}