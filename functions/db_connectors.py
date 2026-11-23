import sqlite3
from pathlib import Path
from typing import Any

# ============================================================
# This is all my original code cleaned up and comments added by AI
# ============================================================

class DatabaseConnection:
    """Wrapper for database connections with unified interface."""

    def __init__(self, connection, db_type: str):
        self.connection = connection
        self.db_type = db_type.lower()

    def execute(self, query: str, params: tuple | list | None = None):
        cursor = self.connection.cursor()

        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            return cursor
        finally:
            pass  # Cursor closed by caller or context manager

    def fetchall_dicts(self, cursor):
        """Fetch all rows as dictionaries."""

        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return [dict(zip(columns, row)) for row in rows]

    def close(self):
        self.connection.close()


def open_sqlite(db_path: str) -> DatabaseConnection:
    """Open a SQLite database connection."""

    path = Path(db_path)

    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")

    return DatabaseConnection(conn, "sqlite")


def open_mysql(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str
) -> DatabaseConnection:
    """Open a MySQL database connection."""

    try:
        import mysql.connector
    except ImportError:
        raise ImportError(
            "mysql-connector-python is required for MySQL support. "
            "Install with: pip install mysql-connector-python"
        )

    conn = mysql.connector.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )

    return DatabaseConnection(conn, "mysql")


def open_postgres(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str
) -> DatabaseConnection:
    """Open a PostgreSQL database connection."""

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        raise ImportError(
            "psycopg2 is required for PostgreSQL support. "
            "Install with: pip install psycopg2-binary"
        )

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        cursor_factory=RealDictCursor
    )

    return DatabaseConnection(conn, "postgres")


def open_db(db_config: dict) -> DatabaseConnection:
    """
    Open a database connection based on configuration.

    Args:
        db_config: Dictionary with keys:
            - type: "sqlite", "mysql", or "postgres"
            - For sqlite: path
            - For mysql/postgres: host, port, database, user, password

    Returns:
        DatabaseConnection instance.
    """

    db_type = db_config.get("type", "").lower()

    if db_type == "sqlite":
        return open_sqlite(db_config["path"])

    elif db_type == "mysql":
        return open_mysql(
            host=db_config["host"],
            port=int(db_config.get("port", 3306)),
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"]
        )

    elif db_type == "postgres":
        return open_postgres(
            host=db_config["host"],
            port=int(db_config.get("port", 5432)),
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"]
        )

    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def close_db(connection: DatabaseConnection | None) -> None:
    """Close a database connection."""

    if connection is not None:
        connection.close()


def select_data(
    connection: DatabaseConnection,
    query: str,
    params: tuple | list | None = None
) -> list[dict]:
    """Execute a SELECT query and return results as dictionaries."""

    cursor = connection.execute(query, params)

    try:
        if connection.db_type == "sqlite":
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return [dict(zip(columns, row)) for row in rows]
        elif connection.db_type == "postgres":
            # RealDictCursor already returns dicts
            return list(cursor.fetchall())
        else:
            # MySQL - fetch as dicts
            return cursor.fetchall()
    finally:
        cursor.close()


def update_data(
    connection: DatabaseConnection,
    query: str,
    params: tuple | list | None = None
) -> int:
    """Execute an INSERT, UPDATE, or DELETE query."""

    cursor = connection.execute(query, params)

    try:
        connection.connection.commit()
        return cursor.rowcount
    except Exception:
        connection.connection.rollback()
        raise
    finally:
        cursor.close()


def merge_data_sqlite(
    connection: DatabaseConnection,
    source_table: str,
    target_table: str,
    key_column: str,
    columns: list[str]
) -> int:
    """Merge using SQLite INSERT ... ON CONFLICT."""

    identifiers = [source_table, target_table, key_column, *columns]

    for identifier in identifiers:
        if not identifier.replace("_", "").isalnum():
            raise ValueError(f"Invalid SQL identifier: {identifier}")

    if not columns or key_column not in columns:
        raise ValueError("columns must include key_column")

    quoted_columns = ", ".join(f'"{col}"' for col in columns)

    update_columns = [col for col in columns if col != key_column]

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

    cursor = connection.execute(query)

    try:
        affected_rows = cursor.rowcount
        connection.connection.commit()
        return affected_rows
    except Exception:
        connection.connection.rollback()
        raise
    finally:
        cursor.close()


def merge_data_generic(
    connection: DatabaseConnection,
    source_table: str,
    target_table: str,
    key_column: str,
    columns: list[str]
) -> int:
    """
    Merge using row-by-row upsert for non-SQLite databases.

    Returns number of rows inserted or updated.
    """

    if not columns or key_column not in columns:
        raise ValueError("columns must include key_column")

    update_columns = [col for col in columns if col != key_column]

    if not update_columns:
        raise ValueError("At least one non-key column is required")

    quoted_source = f'"{source_table}"'
    quoted_target = f'"{target_table}"'
    quoted_key = f'"{key_column}"'

    # Get all rows from source
    select_query = f"SELECT {', '.join(f'{c}' for c in columns)} FROM {quoted_source}"
    source_rows = select_data(connection, select_query)

    if not source_rows:
        return 0

    total_affected = 0

    if connection.db_type == "mysql":
        # MySQL uses INSERT ... ON DUPLICATE KEY UPDATE with VALUES()
        quoted_columns = ", ".join(f'`{col}`' for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_clause = ", ".join(
            f'`{col}` = VALUES(`{col}`)'
            for col in update_columns
        )

        merge_query = f"""
            INSERT INTO `{target_table}` ({quoted_columns})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause}
        """

        cursor = connection.execute(merge_query)

        try:
            for row in source_rows:
                params = tuple(row[col] for col in columns)
                cursor.execute(merge_query, params)

            connection.connection.commit()
            total_affected = cursor.rowcount
        except Exception:
            connection.connection.rollback()
            raise
        finally:
            cursor.close()

    elif connection.db_type == "postgres":
        # PostgreSQL uses INSERT ... ON CONFLICT
        quoted_columns_pg = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_clause = ", ".join(
            f'"{col}" = EXCLUDED."{col}"'
            for col in update_columns
        )

        merge_query = f"""
            INSERT INTO "{target_table}" ({quoted_columns_pg})
            VALUES ({placeholders})
            ON CONFLICT ("{key_column}")
            DO UPDATE SET {update_clause}
        """

        cursor = connection.execute(merge_query)

        try:
            for row in source_rows:
                params = tuple(row[col] for col in columns)
                cursor.execute(merge_query, params)

            connection.connection.commit()
            total_affected = cursor.rowcount
        except Exception:
            connection.connection.rollback()
            raise
        finally:
            cursor.close()

    else:
        raise ValueError(f"Merge not supported for database type: {connection.db_type}")

    return total_affected


def merge_data(
    connection: DatabaseConnection,
    source_table: str,
    target_table: str,
    key_column: str,
    columns: list[str]
) -> int:
    """Merge data using the appropriate method for the database type."""

    if connection.db_type == "sqlite":
        return merge_data_sqlite(connection, source_table, target_table, key_column, columns)
    else:
        return merge_data_generic(connection, source_table, target_table, key_column, columns)


def get_table_schema(
    connection: DatabaseConnection,
    table_name: str
) -> list[dict]:
    """Get column information for a table."""

    if connection.db_type == "sqlite":
        query = f'PRAGMA table_info("{table_name}")'
        rows = select_data(connection, query)
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "default_value": row["dflt_value"]
            }
            for row in rows
        ]

    elif connection.db_type == "mysql":
        query = f"""
            SELECT COLUMN_NAME as name, DATA_TYPE as type, IS_NULLABLE, COLUMN_DEFAULT as default_value
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """
        rows = select_data(connection, query, (table_name,))
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "notnull": row["IS_NULLABLE"] == "NO",
                "default_value": row["default_value"]
            }
            for row in rows
        ]

    elif connection.db_type == "postgres":
        query = f"""
            SELECT column_name as name, data_type as type, is_nullable, column_default as default_value
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """
        rows = select_data(connection, query, (table_name,))
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "notnull": row["is_nullable"] == "NO",
                "default_value": row["default_value"]
            }
            for row in rows
        ]

    else:
        raise ValueError(f"Schema inspection not supported for: {connection.db_type}")


def ensure_table_exists(
    connection: DatabaseConnection,
    table_name: str,
    create_sql: str
) -> None:
    """Create a table if it does not exist."""

    if connection.db_type == "sqlite":
        query = f'CREATE TABLE IF NOT EXISTS "{table_name}" (...)'
        # Use provided SQL with IF NOT EXISTS prepended if needed
        if "IF NOT EXISTS" not in create_sql.upper():
            parts = create_sql.split("(", 1)
            query = f"{parts[0].strip()} IF NOT EXISTS {parts[1]}"
        else:
            query = create_sql

        connection.execute(query)
        connection.connection.commit()

    elif connection.db_type in ("mysql", "postgres"):
        if "IF NOT EXISTS" not in create_sql.upper():
            parts = create_sql.split("CREATE TABLE", 1)
            query = f"{parts[0].strip()} CREATE TABLE IF NOT EXISTS{parts[1]}"
        else:
            query = create_sql

        connection.execute(query)
        connection.connection.commit()
