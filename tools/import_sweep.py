#!/usr/bin/env python3
"""
import_sweep.py - import every project module and report what breaks.

Dependency drift after a 6-month gap rarely shows up as a startup crash; it
shows up as one module that silently fails to import and takes a feature with
it (a router, a parser helper, the stream proxy). This walks the package tree
and actually imports each module so failures are named.

Run:  .venv\\Scripts\\python.exe tools\\import_sweep.py
"""

import importlib
import os
import pkgutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Module-level side effects expect a server-ish environment.
os.environ.setdefault("LAUNCH_MODE", "test")
os.environ.setdefault("STREAM_PORT", "0")
os.environ.setdefault("SERVER_LOG_LEVEL", "CRITICAL")

PACKAGES = [
    "config",
    "models",
    "logging_utils",
    "errors_py",
    "api_utils",
    "browser_utils",
    "stream",
    "launcher",
]


def iter_modules(pkg_name: str):
    pkg = importlib.import_module(pkg_name)
    yield pkg_name
    if hasattr(pkg, "__path__"):
        for info in pkgutil.walk_packages(pkg.__path__, pkg_name + "."):
            yield info.name


def main() -> int:
    failures = []
    tested = 0

    for pkg_name in PACKAGES:
        try:
            modules = list(iter_modules(pkg_name))
        except Exception:
            failures.append((pkg_name, traceback.format_exc(limit=3)))
            continue

        for name in modules:
            tested += 1
            try:
                importlib.import_module(name)
            except Exception:
                failures.append((name, traceback.format_exc(limit=4)))

    for name, tb in failures:
        print(f"\n--- FAIL {name} ---")
        print(tb.strip().splitlines()[-1])
        for line in tb.strip().splitlines()[-6:]:
            print("   " + line)

    print(f"\nmodules imported: {tested - len(failures)}/{tested}")
    print(f"failures: {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
