import json
from datetime import datetime
from pathlib import Path
from typing import Any

import csv

from functions.config_loader import (
    load_env,
    get_smtp_config,
    get_pgp_config,
    get_email_recipients,
    get_ai_config,
)
from functions.db_connectors import (
    open_db,
    close_db,
    select_data,
    merge_data,
    DatabaseConnection,
)
from functions.data_validate.regex_checks import (
    is_valid_email,
    is_valid_phone,
    is_valid_date,
    is_numeric,
    is_alpha,
    is_alphanumeric,
)
from functions.data_validate.null_check import is_required, is_not_null
from functions.data_validate.range_checks import (
    check_numeric_range,
    check_date_range,
    check_string_length,
)
from functions.data_validate.enum_checks import check_enum_value
from functions.data_validate.cross_field_checks import (
    line_total_matches_calculation,
    ship_date_after_order_date,
    delivered_requires_ship_date,
    end_date_after_start_date,
)
from functions.data_validate.format_checks import (
    is_valid_uuid,
    is_valid_currency,
    is_valid_percentage,
    is_boolean_like,
)
from functions.data_validate.statistical_checks import (
    detect_outliers_zscore,
    detect_outliers_iqr,
)
from functions.changelog import (
    generate_run_id,
    ensure_changelog_table,
    log_merge_changes,
    write_json_changelog,
    create_changelog_summary,
)
from functions.auto_fix_runner import (
    create_autofix_tables,
    drop_autofix_tables,
    apply_auto_fixes,
    get_autofix_table_name,
    run_cross_reference_fixes,
)
from functions.ai_analysis import run_ai_analysis
from functions.email_alert import send_email


# Map check types to their handler functions
SINGLE_VALUE_CHECKS = {
    "required": is_required,
    "not_null": is_not_null,
    "is_valid_email": is_valid_email,
    "is_valid_phone": is_valid_phone,
    "is_valid_date": is_valid_date,
    "is_numeric": is_numeric,
    "is_alpha": is_alpha,
    "is_alphanumeric": is_alphanumeric,
    "is_valid_uuid": is_valid_uuid,
    "is_valid_currency": is_valid_currency,
    "is_valid_percentage": is_valid_percentage,
    "is_boolean_like": is_boolean_like,
}

ROW_CHECKS = {
    "line_total_matches_calculation": line_total_matches_calculation,
    "ship_date_after_order_date": ship_date_after_order_date,
    "delivered_requires_ship_date": delivered_requires_ship_date,
    "end_date_after_start_date": end_date_after_start_date,
}


def _run_single_value_check(check_config: dict, value: Any) -> dict:
    """Run a check on a single column value."""

    check_type = check_config.get("type", "") or check_config.get("function", "")
    column_name = check_config.get("column", "unknown")

    if check_type in ("required",):
        return is_required(value, column_name)

    if check_type in ("not_null",):
        allow_empty = check_config.get("allow_empty_string", False)
        return is_not_null(value, column_name, allow_empty)

    if check_type == "regex":
        func_name = check_config.get("function", "")
        handler = SINGLE_VALUE_CHECKS.get(func_name)

        if not handler:
            return {"valid": True, "reason": f"Unknown regex function: {func_name}"}

        result = handler(value)

        if isinstance(result, bool):
            valid = result
        else:
            valid = result.get("valid", result)

        return {
            "valid": valid,
            "reason": f"{column_name} failed {func_name}" if not valid else ""
        }

    if check_type == "range":
        min_val = check_config.get("min")
        max_val = check_config.get("max")
        return check_numeric_range(value, column_name, min_val, max_val)

    if check_type == "date_range":
        min_date = check_config.get("min_date")
        max_date = check_config.get("max_date")
        date_format = check_config.get("date_format", "%Y-%m-%d")
        return check_date_range(value, column_name, min_date, max_date, date_format)

    if check_type == "string_length":
        min_len = check_config.get("min_length")
        max_len = check_config.get("max_length")
        return check_string_length(value, column_name, min_len, max_len)

    if check_type == "enum":
        allowed = check_config.get("allowed_values", [])
        case_sensitive = check_config.get("case_sensitive", True)
        return check_enum_value(value, allowed, column_name, case_sensitive)

    if check_type == "format":
        func_name = check_config.get("function", "")
        handler = SINGLE_VALUE_CHECKS.get(func_name)

        if not handler:
            return {"valid": True, "reason": f"Unknown format function: {func_name}"}

        result = handler(value, column_name)

        if isinstance(result, bool):
            return {"valid": result, "reason": ""}

        return result

    # Try as a direct function name
    handler = SINGLE_VALUE_CHECKS.get(check_type)

    if handler:
        result = handler(value, column_name)

        if isinstance(result, bool):
            return {"valid": result, "reason": ""}

        return result

    return {
        "valid": True,
        "reason": f"Unknown check type: {check_type}"
    }


def _run_row_check(check_config: dict, row: dict) -> dict:
    """Run a cross-field check on an entire row."""

    func_name = check_config.get("function", "") or check_config.get("type", "")
    handler = ROW_CHECKS.get(func_name)

    if not handler:
        return {"valid": True, "reason": f"Unknown row check: {func_name}"}

    # Pass column mappings from config if provided
    kwargs = {}

    for key in ["quantity_column", "price_column", "total_column",
                "order_date_column", "ship_date_column", "status_column",
                "start_column", "end_column", "tolerance"]:
        if key in check_config:
            kwargs[key] = check_config[key]

    return handler(row, **kwargs)


def validate_table(
    connection: DatabaseConnection,
    table_config: dict
) -> dict:
    """
    Run all configured checks on a staging table.

    Returns validation results with severity breakdowns.
    """

    staging_table = table_config["staging_table"]
    checks = table_config.get("checks", [])

    # Fetch all rows from staging table
    rows = select_data(connection, f'SELECT * FROM "{staging_table}"')

    total_rows = len(rows)
    critical_errors = []
    warnings = []
    info_findings = []

    for row_idx, row in enumerate(rows):
        for check in checks:
            severity = check.get("severity", "warning")

            # Determine if this is a single-value or row-level check
            if "function" in check and check["function"] in ROW_CHECKS:
                result = _run_row_check(check, row)
            elif "type" in check and check["type"] in ROW_CHECKS:
                result = _run_row_check(check, row)
            else:
                column_name = check.get("column", "")
                value = row.get(column_name)
                result = _run_single_value_check(check, value)

            if not result.get("valid", True):
                finding = {
                    "row_index": row_idx,
                    "row_key": dict(row),
                    "check_type": check.get("type") or check.get("function"),
                    "severity": severity,
                    "reason": result.get("reason", "")
                }

                if severity == "critical":
                    critical_errors.append(finding)
                elif severity == "info":
                    info_findings.append(finding)
                else:
                    warnings.append(finding)

    return {
        "table": staging_table,
        "total_rows": total_rows,
        "critical_count": len(critical_errors),
        "warning_count": len(warnings),
        "info_count": len(info_findings),
        "has_critical_errors": len(critical_errors) > 0,
        "critical_errors": critical_errors,
        "warnings": warnings,
        "info_findings": info_findings
    }


def run_task(task_config: dict) -> dict:
    """Run a single validation task from tasks.json."""

    load_env()

    run_id = generate_run_id()
    task_name = task_config.get("name", "unnamed_task")

    print(f"Starting validation run: {run_id}")
    print(f"Task: {task_name}")

    # Parse database configuration
    db_source = task_config.get("database")
    db_type = task_config.get("db_type", "sqlite")

    if isinstance(db_source, str):
        # Legacy format - just a path string
        db_config = {"type": db_type, "path": db_source}
    elif isinstance(db_source, dict):
        db_config = db_source
    else:
        raise ValueError("database must be a path string or config dict")

    if db_config.get("type") is None:
        db_config["type"] = db_type

    # Open database connection
    connection = open_db(db_config)

    try:
        # Ensure changelog table exists
        changelog_config = task_config.get("changelog", {})
        changelog_table = changelog_config.get("db_table", "change_log")

        if changelog_config.get("enabled", True):
            ensure_changelog_table(connection, changelog_table)

        tables_config = task_config.get("tables", {})
        merge_order = task_config.get("merge_order", list(tables_config.keys()))

        all_validation_results = {}
        table_operation_results = {}
        has_blocking_errors = False

        # Phase 1: Create autofix staging tables (clone from staging)
        print("\n--- Auto-Fix Table Creation ---")
        autofix_tables = create_autofix_tables(connection, tables_config)

        for table_key, autofix_table in autofix_tables.items():
            print(f"  Cloned {tables_config[table_key]['staging_table']} -> {autofix_table}")

        # Phase 2: Apply auto-fixes to autofix staging tables
        print("\n--- Auto-Fix Application ---")

        for table_key in merge_order:
            if table_key not in tables_config:
                continue

            table_cfg = tables_config[table_key]
            autofix_table = autofix_tables[table_key]
            fix_names = table_cfg.get("auto_fixes", [])

            if not fix_names:
                print(f"  {table_key}: no auto-fixes configured")
                continue

            print(f"  {table_key}: applying {len(fix_names)} fix(es)...")

            # Determine key column
            key_column = table_cfg.get("key_column", "id")

            changelog_table = changelog_config.get("db_table", "change_log")

            fix_result = apply_auto_fixes(
                connection=connection,
                staging_table=table_cfg["staging_table"],
                autofix_table=autofix_table,
                fix_names=fix_names,
                run_id=run_id,
                key_column=key_column,
                changelog_table=changelog_table
            )

            print(f"    Fixes applied: {fix_result['fixes_applied']}, "
                  f"Rows changed: {fix_result['rows_changed']}")

        # Phase 2b: Cross-reference (SQL join-based) fixes
        print("\n--- Cross-Reference Fixes ---")
        xref_results = run_cross_reference_fixes(
            connection=connection,
            tables_config=tables_config,
            autofix_tables=autofix_tables,
            run_id=run_id,
            changelog_table=changelog_table
        )
        for fix_name, result in xref_results.items():
            print(f"  {fix_name}: {result['fixed']} rows fixed")

        # Phase 3: Validate autofix tables
        print("\n--- Validation Phase (on autofix tables) ---")

        for table_key in merge_order:
            if table_key not in tables_config:
                continue

            table_cfg = dict(tables_config[table_key])
            autofix_table = autofix_tables[table_key]

            # Point validation at the autofix table
            table_cfg["staging_table"] = autofix_table

            print(f"\nValidating {autofix_table}...")

            result = validate_table(connection, table_cfg)
            all_validation_results[table_key] = result

            print(f"  Rows: {result['total_rows']}, "
                  f"Critical: {result['critical_count']}, "
                  f"Warnings: {result['warning_count']}")

            if result["has_critical_errors"]:
                has_blocking_errors = True
                print(f"  BLOCKING: Critical errors found for {table_key}")

        # Phase 3b: Log critical errors and generate CSV attachments
        print("\n--- Critical Errors Summary ---")
        critical_error_csv_paths = []

        for table_key in merge_order:
            if table_key not in tables_config:
                continue

            result = all_validation_results.get(table_key, {})
            critical_errors = result.get("critical_errors", [])

            if not critical_errors:
                print(f"  {table_key}: 0 critical errors")
                continue

            # Log per-error summary (compact)
            print(f"  {table_key}: {len(critical_errors)} critical errors")

            for ce in critical_errors[:5]:
                row_key = ce.get("row_key", {})
                key_str = ", ".join(f"{k}={v}" for k, v in list(row_key.items())[:3])
                print(f"      row {ce.get('row_index', '?')} ({key_str}): {ce.get('reason', '')[:80]}")

            if len(critical_errors) > 5:
                print(f"      ... {len(critical_errors) - 5} more")

            # Generate CSV if < 100 critical errors for this table
            if len(critical_errors) < 100:
                csv_filename = f"critical_errors_{run_id}_{table_key}.csv"
                csv_path = Path("outputs") / csv_filename
                Path("outputs").mkdir(parents=True, exist_ok=True)

                # Determine columns from first row's row_key
                if critical_errors:
                    sample_row = critical_errors[0].get("row_key", {})
                    fieldnames = list(sample_row.keys()) + ["check_type", "severity", "reason"]

                    with open(csv_path, "w", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        for ce in critical_errors:
                            row = dict(ce.get("row_key", {}))
                            row["check_type"] = ce.get("check_type", "")
                            row["severity"] = ce.get("severity", "")
                            row["reason"] = ce.get("reason", "")
                            writer.writerow(row)

                    critical_error_csv_paths.append(str(csv_path))
                    print(f"  -> CSV written: {csv_path}")

        # If 100+ errors, log a note
        for table_key in merge_order:
            if table_key not in tables_config:
                continue
            result = all_validation_results.get(table_key, {})
            if len(result.get("critical_errors", [])) >= 100:
                print(f"  {table_key}: {len(result['critical_errors'])}+ errors (CSV not generated, exceeded 100 limit)")

        print("--- End Critical Errors ---\n")

        # Phase 2: AI Analysis (if enabled)
        ai_findings = []

        if task_config.get("ai_analysis", {}).get("enabled", False):
            print("\n--- AI Analysis Phase ---")

            ai_config = get_ai_config(task_config["ai_analysis"])

            # Build schema info
            schema_info = {}

            for table_key, table_cfg in tables_config.items():
                staging_table = table_cfg["staging_table"]
                columns = table_cfg.get("columns", [])

                if not columns:
                    sample_row = select_data(connection, f'SELECT * FROM "{staging_table}" LIMIT 1')
                    columns = list(sample_row[0].keys()) if sample_row else []

                schema_info[staging_table] = columns

            # Collect sample data (limited for token efficiency)
            sample_size = ai_config.get("sample_size", 50)
            all_samples = []

            for table_key, table_cfg in tables_config.items():
                staging_table = table_cfg["staging_table"]
                samples = select_data(
                    connection,
                    f'SELECT * FROM "{staging_table}" LIMIT ?',
                    (sample_size,)
                ) if connection.db_type == "sqlite" else select_data(
                    connection,
                    f'SELECT * FROM "{staging_table}" LIMIT %s',
                    (sample_size,)
                )
                all_samples.extend(samples[:10])

            # Build validation summary for AI
            validation_summary = {}

            for table_key, result in all_validation_results.items():
                validation_summary[table_key] = {
                    "total_rows": result["total_rows"],
                    "critical_count": result["critical_count"],
                    "warning_count": result["warning_count"]
                }

            # Get details from task config or AI config
            table_details = task_config.get("ai_analysis", {}).get("details", "")

            try:
                ai_findings = run_ai_analysis(
                    ai_config=ai_config,
                    schema_info=schema_info,
                    validation_summary=validation_summary,
                    sample_data=all_samples[:20],
                    table_details=table_details
                )
                print(f"AI analysis complete. Findings: {len(ai_findings)}")

            except Exception as e:
                print(f"AI analysis failed (non-blocking): {e}")

        # Phase 3: Merge tables (if no blocking errors)
        print("\n--- Merge Phase ---")

        for table_key in merge_order:
            if table_key not in tables_config:
                continue

            table_cfg = tables_config[table_key]
            autofix_table = autofix_tables[table_key]
            target_table = table_cfg["target_table"]
            key_column = table_cfg["key_column"]
            columns = table_cfg.get("columns", [])

            # Check if this table has blocking errors
            table_result = all_validation_results.get(table_key, {})

            if table_result.get("has_critical_errors", False):
                print(f"\nSkipping merge for {table_key}: critical validation errors")
                table_operation_results[table_key] = {
                    "status": "skipped",
                    "reason": "critical_validation_errors"
                }
                continue

            # Get columns if not specified
            if not columns:
                sample_row = select_data(connection, f'SELECT * FROM "{autofix_table}" LIMIT 1')
                columns = list(sample_row[0].keys()) if sample_row else []

            # Log changes before merge
            insert_count = 0
            update_count = 0

            if changelog_config.get("enabled", True):
                print(f"\nLogging changes for {table_key}...")
                change_counts = log_merge_changes(
                    connection=connection,
                    run_id=run_id,
                    source_table=autofix_table,
                    target_table=target_table,
                    key_column=key_column,
                    columns=columns,
                    reason=f"validation_run: {task_name}",
                    changelog_table=changelog_config.get("db_table", "change_log")
                )
                insert_count = change_counts["inserted"]
                update_count = change_counts["updated"]

            # Perform merge from autofix table to production
            print(f"Merging {autofix_table} -> {target_table}...")
            try:
                affected_rows = merge_data(
                    connection=connection,
                    source_table=autofix_table,
                    target_table=target_table,
                    key_column=key_column,
                    columns=columns
                )
            except Exception as e:
                print(f"  Merge failed: {e}")
                table_operation_results[table_key] = {
                    "status": "failed",
                    "reason": str(e)
                }
                continue

            table_operation_results[table_key] = {
                "status": "completed",
                "affected_rows": affected_rows,
                "logged_inserts": insert_count,
                "logged_updates": update_count
            }

            print(f"  Affected rows: {affected_rows}")

        # Phase 4: Generate report
        print("\n--- Report Generation ---")

        reporting_config = task_config.get("reporting", {})
        output_path = reporting_config.get("output_path", "outputs/validation_report.json")

        validation_summary_for_changelog = {}

        for table_key, result in all_validation_results.items():
            validation_summary_for_changelog[table_key] = {
                "total_rows": result["total_rows"],
                "critical_count": result["critical_count"],
                "warning_count": result["warning_count"],
                "info_count": result.get("info_count", 0),
                "has_critical_errors": result["has_critical_errors"]
            }

        changelog_summary = create_changelog_summary(
            run_id=run_id,
            task_name=task_name,
            table_results=table_operation_results,
            validation_results=validation_summary_for_changelog,
            ai_findings=ai_findings
        )

        # Write JSON report
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(changelog_summary, f, indent=2, default=str)

        print(f"Report written to {output_path}")

        # Write changelog JSON if enabled
        if changelog_config.get("enabled", True):
            json_dir = changelog_config.get("json_dir", "logs/changelogs/")
            changelog_file = write_json_changelog(json_dir, run_id, changelog_summary)
            print(f"Changelog written to {changelog_file}")

        # Phase 5: Email notification (if enabled and configured)
        # Email is sent regardless of errors (number of critical errors doesn't gate sending)
        email_enabled = reporting_config.get("email_on_complete", False)
        local_only = reporting_config.get("local_only", False)

        if email_enabled and not local_only:
            print("\n--- Sending Email Notification ---")

            try:
                smtp_cfg = get_smtp_config()
                pgp_cfg = get_pgp_config()
                recipients = get_email_recipients()

                all_recipients = (
                    recipients.get("to", []) +
                    recipients.get("cc", []) +
                    recipients.get("bcc", [])
                )

                if not all_recipients:
                    print("No email recipients configured. Skipping email.")
                else:
                    # Build report body
                    # Only count critical errors that remain after auto-fixes
                    total_critical = sum(
                        r["critical_count"] for r in validation_summary_for_changelog.values()
                    )
                    total_warnings = sum(
                        r["warning_count"] for r in validation_summary_for_changelog.values()
                    )

                    # Force urgent if configured (for testing or manual override)
                    force_urgent = reporting_config.get("force_urgent", False)

                    is_urgent = force_urgent or (total_critical > 0)

                    # Subject prefix for urgent emails
                    subject_prefix = "[URGENT] " if is_urgent else ""

                    body_lines = [
                        f"Validation Run: {run_id}",
                        f"Task: {task_name}",
                        f"",
                        f"Summary:",
                        f"- Critical errors (remaining after fixes): {total_critical}",
                        f"- Warnings: {total_warnings}",
                        f"- AI findings: {len(ai_findings)}",
                        f"",
                    ]

                    if is_urgent:
                        body_lines.insert(2, "WARNING: Critical errors detected. This email is marked URGENT.")

                    for table_key, result in validation_summary_for_changelog.items():
                        body_lines.append(f"{table_key}:")
                        body_lines.append(f"  - Rows: {result['total_rows']}")
                        body_lines.append(f"  - Critical (remaining): {result['critical_count']}")
                        body_lines.append(f"  - Warnings: {result['warning_count']}")

                    for table_key, op_result in table_operation_results.items():
                        status = op_result.get("status", "unknown")
                        reason = op_result.get("reason", "")
                        affected = op_result.get("affected_rows", 0)
                        body_lines.append(f"{table_key} merge: {status}" + (f" ({reason})" if reason else f", {affected} rows affected"))

                    body = "\n".join(body_lines)

                    # Determine priority headers for urgent emails
                    extra_headers = {}
                    if is_urgent:
                        extra_headers["X-Priority"] = "1"
                        extra_headers["Importance"] = "high"
                        extra_headers["X-MSMail-Priority"] = "High"

                    send_email(
                        **smtp_cfg,
                        subject=f"{subject_prefix}[Validation] {task_name} - {run_id}",
                        header="Data Validation Report",
                        body=body,
                        footer="AI Database Analysis Pipeline",
                        **recipients,
                        pgp_enabled=pgp_cfg.get("pgp_enabled", False),
                        pgp_sign=pgp_cfg.get("pgp_sign", True),
                        pgp_encrypt=pgp_cfg.get("pgp_encrypt", True),
                        pgp_recipient_keys=pgp_cfg.get("pgp_recipient_keys"),
                        pgp_private_key_path=pgp_cfg.get("pgp_private_key_path"),
                        pgp_private_key_password=pgp_cfg.get("pgp_private_key_password"),
                        attachments=(
                            ([output_path] if Path(output_path).exists() else [])
                            + critical_error_csv_paths
                        ) or None,
                        extra_headers=extra_headers,
                    )

                    print(f"Email notification sent ({'URGENT' if is_urgent else 'normal'}).")

            except Exception as e:
                print(f"Failed to send email (non-blocking): {e}")

        elif local_only:
            print("\nLocal-only mode. Email reporting skipped.")

        # Final summary
        print("\n--- Run Complete ---")
        print(f"Run ID: {run_id}")
        print(f"Blocking errors: {has_blocking_errors}")
        print(f"AI findings: {len(ai_findings)}")

        return changelog_summary

    finally:
        # Clean up autofix tables
        try:
            drop_autofix_tables(connection, tables_config)
        except Exception:
            pass
        close_db(connection)


def run_all_tasks(task_file: str | None = None) -> list[dict]:
    """Run all tasks from tasks.json."""

    from functions.config_loader import load_task_config

    config = load_task_config(task_file)
    tasks = config.get("tasks", [])

    if not tasks:
        print("No tasks found in configuration.")
        return []

    results = []

    for i, task in enumerate(tasks):
        print(f"\n{'=' * 60}")
        print(f"Task {i + 1}/{len(tasks)}")
        print(f"{'=' * 60}")

        try:
            result = run_task(task)
            results.append(result)
        except Exception as e:
            print(f"Task failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "task_name": task.get("name", "unknown"),
                "status": "failed",
                "error": str(e)
            })

    return results
