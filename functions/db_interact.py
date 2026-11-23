import sqlite3
from pathlib import Path
from typing import Any, Optional

# ============================================================
# This is all my original code cleaned up and comments added by AI
# ============================================================

def open_db(db_path: str) -> sqlite3.Connection:
    """
    Open a connection to a SQLite database.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        sqlite3.Connection: Active database connection.
    """
    path = Path(db_path)

    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row

    # Enable foreign key constraints.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def close_db(connection: Optional[sqlite3.Connection]) -> None:
    """
    Close an SQLite database connection.
    """
    if connection is not None:
        connection.close()


def select_data(
    connection: sqlite3.Connection,
    query: str,
    params: tuple = ()
) -> list[dict]:
    """
    Execute a SELECT query and return results as dictionaries.

    Args:
        connection: Active SQLite connection.
        query: SQL SELECT statement.
        params: Query parameters.

    Returns:
        List of dictionaries containing query results.
    """
    cursor = connection.cursor()

    try:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def update_data(
    connection: sqlite3.Connection,
    query: str,
    params: tuple = ()
) -> int:
    """
    Execute an INSERT, UPDATE, or DELETE query.

    Changes are committed automatically.

    Args:
        connection: Active SQLite connection.
        query: SQL modification statement.
        params: Query parameters.

    Returns:
        Number of affected rows.
    """
    cursor = connection.cursor()

    try:
        cursor.execute(query, params)
        connection.commit()

        return cursor.rowcount

    except sqlite3.Error:
        connection.rollback()
        raise

    finally:
        cursor.close()


def merge_data(
    connection: sqlite3.Connection,
    source_table: str,
    target_table: str,
    key_column: str,
    columns: list[str]
) -> int:
    """
    Merge source table records into a target table.

    Existing records are updated using key_column.
    New records are inserted.

    Both tables must have compatible column structures.

    Args:
        connection: Active SQLite connection.
        source_table: Table containing incoming records.
        target_table: Destination table.
        key_column: Unique identifying column.
        columns: Columns to merge.

    Returns:
        Number of inserted or updated rows.
    """

    # Validate identifiers before inserting them into SQL.
    identifiers = [source_table, target_table, key_column, *columns]

    for identifier in identifiers:
        if not identifier.replace("_", "").isalnum():
            raise ValueError(f"Invalid SQL identifier: {identifier}")

    if not columns or key_column not in columns:
        raise ValueError("columns must include key_column")

    quoted_columns = ", ".join(f'"{col}"' for col in columns)

    placeholders = ", ".join("?" for _ in columns)

    update_columns = [
        col for col in columns if col != key_column
    ]

    if not update_columns:
        raise ValueError("At least one non-key column is required")

    update_clause = ", ".join(
        f'"{col}" = excluded."{col}"'
        for col in update_columns
    )

    query = f"""
        INSERT INTO "{target_table}" ({quoted_columns})
        SELECT {quoted_columns}
        FROM "{source_table}"
        WHERE true
        ON CONFLICT("{key_column}")
        DO UPDATE SET {update_clause}
    """

    cursor = connection.cursor()

    try:
        cursor.execute(query)
        affected_rows = cursor.rowcount
        connection.commit()

        return affected_rows

    except sqlite3.Error:
        connection.rollback()
        raise

    finally:
        cursor.close()
