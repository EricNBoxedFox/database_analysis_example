import json
from datetime import datetime
from pathlib import Path
from typing import Any

from functions.db_connectors import (
    DatabaseConnection,
    select_data,
    update_data,
)


CHANGE_LOG_CREATE_SQL = """
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    row_key TEXT,
    before_state TEXT,
    after_state TEXT,
    reason TEXT
)
"""


def generate_run_id() -> str:
    """Generate a unique run identifier."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}"


def ensure_changelog_table(
    connection: DatabaseConnection,
    table_name: str = "change_log"
) -> None:
    """Create the change_log table if it does not exist."""

    # Check if table exists first
    try:
        if connection.db_type == "sqlite":
            query = 'SELECT name FROM sqlite_master WHERE type="table" AND name=?'
            result = select_data(connection, query, (table_name,))
        elif connection.db_type in ("mysql", "postgres"):
            query = f"""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = {
                    'DATABASE()' if connection.db_type == 'mysql' else "'public'"
                }
                AND table_name = %s
            """
            result = select_data(connection, query, (table_name,))
        else:
            raise ValueError(f"Unsupported DB type: {connection.db_type}")

        if not result:
            _create_changelog_table(connection, table_name)

    except Exception:
        # Table might not exist or other error - try to create it
        _create_changelog_table(connection, table_name)


def _create_changelog_table(
    connection: DatabaseConnection,
    table_name: str
) -> None:
    """Create the change_log table."""

    sql = CHANGE_LOG_CREATE_SQL.replace("change_log", table_name)

    if "IF NOT EXISTS" not in sql.upper():
        parts = sql.split("CREATE TABLE", 1)
        sql = f"{parts[0].strip()} CREATE TABLE IF NOT EXISTS{parts[1]}"

    update_data(connection, sql)


def log_change(
    connection: DatabaseConnection,
    run_id: str,
    table_name: str,
    operation: str,
    row_key: Any,
    before_state: dict | None = None,
    after_state: dict | None = None,
    reason: str = ""
) -> None:
    """Log a single change to the database changelog."""

    if connection.db_type == "sqlite":
        query = f"""
            INSERT INTO "{table_name}"
            (run_id, timestamp, table_name, operation, row_key, before_state, after_state, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            run_id,
            datetime.now().isoformat(),
            table_name,
            operation,
            str(row_key),
            json.dumps(before_state) if before_state else None,
            json.dumps(after_state) if after_state else None,
            reason
        )
    else:
        query = f"""
            INSERT INTO "{table_name}"
            (run_id, timestamp, table_name, operation, row_key, before_state, after_state, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            run_id,
            datetime.now().isoformat(),
            table_name,
            operation,
            str(row_key),
            json.dumps(before_state) if before_state else None,
            json.dumps(after_state) if after_state else None,
            reason
        )

    update_data(connection, query, params)


def log_merge_changes(
    connection: DatabaseConnection,
    run_id: str,
    source_table: str,
    target_table: str,
    key_column: str,
    columns: list[str],
    reason: str = "",
    changelog_table: str = "change_log"
) -> dict:
    """
    Log all changes that will occur during a merge operation.

    Captures before/after state for each row being inserted or updated.

    Returns:
        {"inserted": int, "updated": int}
    """

    # Get all source rows
    select_query = f'SELECT {", ".join(columns)} FROM "{source_table}"'
    source_rows = select_data(connection, select_query)

    if not source_rows:
        return {"inserted": 0, "updated": 0}

    inserted = 0
    updated = 0

    for row in source_rows:
        key_value = row[key_column]

        # Check if row exists in target
        where_clause = f'"{key_column}" = ?' if connection.db_type == "sqlite" else f'"{key_column}" = %s'
        existing = select_data(connection, f'SELECT * FROM "{target_table}" WHERE {where_clause}', (key_value,))

        before_state = dict(existing[0]) if existing else None

        if before_state is None:
            # Insert
            log_change(
                connection=connection,
                run_id=run_id,
                table_name=changelog_table,
                operation="insert",
                row_key=key_value,
                after_state={col: row[col] for col in columns},
                reason=reason
            )
            inserted += 1
        else:
            # Check if values actually changed
            changes = {}

            for col in columns:
                if col == key_column:
                    continue

                old_val = before_state.get(col)
                new_val = row.get(col)

                if old_val != new_val:
                    changes[col] = {"old": old_val, "new": new_val}

            if changes:
                log_change(
                    connection=connection,
                    run_id=run_id,
                    table_name=changelog_table,
                    operation="update",
                    row_key=key_value,
                    before_state={col: before_state.get(col) for col in columns},
                    after_state={col: row[col] for col in columns},
                    reason=reason
                )
                updated += 1

    return {"inserted": inserted, "updated": updated}


def write_json_changelog(
    output_dir: str,
    run_id: str,
    report_data: dict
) -> str:
    """Write changelog data to a JSON file."""

    path = Path(output_dir)

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    filepath = path / f"{run_id}.json"

    with open(filepath, "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    return str(filepath)


def create_changelog_summary(
    run_id: str,
    task_name: str,
    table_results: dict,
    validation_results: dict,
    ai_findings: list | None = None
) -> dict:
    """Create a structured changelog summary for JSON output."""

    return {
        "run_id": run_id,
        "task_name": task_name,
        "timestamp": datetime.now().isoformat(),
        "validation_summary": validation_results,
        "table_operations": table_results,
        "ai_findings": ai_findings or [],
        "status": "completed"
    }
