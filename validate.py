import sys
from pathlib import Path

from functions.config_loader import load_env, find_project_root, load_task_config
from functions.validate_runner import run_all_tasks


def main():
    """Entry point for validation runs."""

    # Load environment
    load_env()

    project_root = find_project_root()
    print(f"Project root: {project_root}")

    # Add project root to path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Load and run tasks
    task_file = Path(project_root) / "tasks.json"

    if not task_file.exists():
        print(f"Task file not found: {task_file}")
        sys.exit(1)

    results = run_all_tasks(str(task_file))

    print(f"\n{'=' * 60}")
    print(f"Completed {len(results)} task(s)")
    print(f"{'=' * 60}")

    for result in results:
        status = result.get("status", "completed")
        name = result.get("task_name", result.get("task", "unknown"))
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
