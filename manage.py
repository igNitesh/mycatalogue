#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run administrative tasks."""
    # Auto-switch to project virtualenv if running from global Python on host machine
    if (
        not Path("/.dockerenv").exists()
        and not os.environ.get("DOCKER_CONTAINER")
        and sys.prefix == sys.base_prefix
    ):
        base_dir = Path(__file__).resolve().parent
        if sys.platform == "win32":
            venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = base_dir / ".venv" / "bin" / "python"

        if venv_python.exists():
            sys.exit(subprocess.call([str(venv_python)] + sys.argv))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
