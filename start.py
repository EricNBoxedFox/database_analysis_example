import argparse
import json
import sys
from pathlib import Path
# from pprint import pprint as pp

# ============================================================
# Importing in my functions. 
# ============================================================
from functions.config_loader import load_env, find_project_root, load_task_config
from functions.validate_runner import run_all_tasks, run_task


def _apply_email_override(task, send_email: bool) -> None:
    """Override reporting email settings based on CLI flag."""
    reporting = task.setdefault("reporting", {})
    reporting["email_on_complete"] = send_email
    reporting["local_only"] = not send_email


def run_from_file(task_file: str, send_email: bool = True) -> None:
    """Run validation from a task JSON file."""

    load_env()

    project_root = find_project_root()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    path = Path(task_file)

    if not path.is_file():
        print(f"Task file not found: {path}")
        sys.exit(1)

    config = load_task_config(str(path))
    tasks = config.get("tasks", [])

    for task in tasks:
        _apply_email_override(task, send_email)

    if not tasks:
        print("No tasks found in configuration.")
        sys.exit(1)

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

    print(f"\n{'=' * 60}")
    print(f"Completed {len(results)} task(s)")
    print(f"{'=' * 60}")


def run_from_default(send_email: bool = True) -> None:
    """Run validation from the default tasks.json."""

    load_env()

    project_root = find_project_root()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    task_file = project_root / "tasks.json"

    if not task_file.exists():
        print(f"Default task file not found: {task_file}")
        sys.exit(1)

    config = load_task_config(str(task_file))
    tasks = config.get("tasks", [])

    for task in tasks:
        _apply_email_override(task, send_email)

    if not tasks:
        print("No tasks found in configuration.")
        sys.exit(1)

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

    print(f"\n{'=' * 60}")
    print(f"Completed {len(results)} task(s)")
    print(f"{'=' * 60}")


def run_flask_server(host: str = "0.0.0.0", port: int = 5000, send_email_override: bool = True) -> None:
    """Run Flask server receving validation task JSON's via POST."""

    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("Flask is required for server mode. Install with: pip install flask")
        sys.exit(1)

    load_env()

    project_root = find_project_root()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/validate", methods=["POST"])
    def validate_endpoint():
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        # Query param: ?no_email=true
        no_email = request.args.get("no_email", "false").lower() == "true"
        send_email_flag = send_email_override and not no_email

        # Accept either a single task or a full project config
        if "tasks" in data:
            tasks = data["tasks"]
        elif "name" in data:
            tasks = [data]
        else:
            return jsonify({"error": "Invalid task structure"}), 400

        for task in tasks:
            _apply_email_override(task, send_email_flag)

        results = []

        for task in tasks:
            try:
                result = run_task(task)
                results.append(result)
            except Exception as e:
                results.append({
                    "task_name": task.get("name", "unknown"),
                    "status": "failed",
                    "error": str(e)
                })

        return jsonify({"results": results}), 200

    @app.route("/validate/file", methods=["POST"])
    def validate_file_endpoint():
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        no_email = request.args.get("no_email", "false").lower() == "true"
        send_email_flag = send_email_override and not no_email

        uploaded = request.files["file"]
        try:
            config = json.load(uploaded)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON file"}), 400

        if "tasks" in config:
            tasks = config["tasks"]
        elif "name" in config:
            tasks = [config]
        else:
            return jsonify({"error": "Invalid task structure"}), 400

        for task in tasks:
            _apply_email_override(task, send_email_flag)

        results = []

        for task in tasks:
            try:
                result = run_task(task)
                results.append(result)
            except Exception as e:
                results.append({
                    "task_name": task.get("name", "unknown"),
                    "status": "failed",
                    "error": str(e)
                })

        return jsonify({"results": results}), 200

    print(f"Starting Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=False)


def main():
    parser = argparse.ArgumentParser(
        description="AI Database Analysis - Validation Pipeline"
    )

    parser.add_argument(
        "task_file",
        nargs="?",
        default=None,
        help="Path to a task JSON file (optional)"
    )

    parser.add_argument(
        "--server",
        action="store_true",
        help="Run as Flask API server"
    )
    # ============================================================
    # Definetly do not listen on all devices in a prod environment.
    # Left this as listen on all just for showcase. And left port
    # 5000 since this isn't likely to be used in any prod env anyways.
    # ============================================================
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Flask server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Flask server port (default: 5000)"
    )

    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Disable email notifications (default: email enabled)"
    )

    args = parser.parse_args()

    if args.server:
        run_flask_server(args.host, args.port, send_email_override=not args.no_email)
    elif args.task_file:
        run_from_file(args.task_file, send_email=not args.no_email)
    else:
        run_from_default(send_email=not args.no_email)


if __name__ == "__main__":
    main()
