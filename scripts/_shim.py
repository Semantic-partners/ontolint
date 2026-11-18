"""What the deprecated shims share: run an installed ontolint command, or say how to get one."""
import sys
from importlib import import_module
from pathlib import Path


def run(module, command):
    """Run `module`'s main(); if ontolint isn't installed, explain instead of a traceback."""
    try:
        main = import_module(module).main
    except ModuleNotFoundError as e:
        if e.name != "ontolint":   # ontolint is there, but something it needs is not
            raise
        root = Path(__file__).resolve().parent.parent
        script = Path(sys.argv[0]).name
        sys.stderr.write(
            f"{script}: ontolint is not installed in this Python ({sys.executable}).\n"
            f"The scripts in scripts/ now run the installed package. Install it with\n\n"
            f"    pip install {root}\n\n"
            f"(or `poetry install` in that directory), then run `{command}` instead of {script}.\n")
        return 2
    return main()
