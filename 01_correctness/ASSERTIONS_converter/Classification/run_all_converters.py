#!/usr/bin/env python3
"""
Launcher for all `add_answers_to_activity.py` scripts in this folder.

This launcher lives inside `Classification/`. It looks at every sibling
subfolder, and for each one that contains `add_answers_to_activity.py`
it runs that script with the subfolder as the working directory — so
the script can find its own local `activity_cat*.json` and
`classification_answer*.txt` files via relative paths.

Usage (from inside Classification/):
    python run_all_converters.py
    python run_all_converters.py --stop-on-error   # halt at first failure
    python run_all_converters.py --only cat1_rag   # run a single folder
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_NAME = "add_answers_to_activity.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Halt the launcher at the first failing script (default: continue).",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Run only folder(s) whose name contains this substring "
             "(e.g. 'cat1_rag').",
    )
    args = parser.parse_args()

    # This launcher lives inside Classification/, so siblings of this file
    # are the converter folders.
    here = Path(__file__).resolve().parent
    print(f"Scanning: {here}\n")

    scripts = sorted(here.glob(f"*/{SCRIPT_NAME}"))
    if args.only:
        scripts = [s for s in scripts if args.only in s.parent.name]
    if not scripts:
        sys.exit(
            f"No '{SCRIPT_NAME}' scripts found in subfolders of {here}.\n"
            f"Place this launcher inside the Classification/ folder."
        )

    print(f"Found {len(scripts)} converter(s) to run:")
    for s in scripts:
        print(f"  - {s.parent.name}")
    print()

    results: list[tuple[str, int]] = []
    for script in scripts:
        folder = script.parent.name
        print("=" * 72)
        print(f"  Running: {folder}")
        print(f"  Command: python {script.name}   (cwd={script.parent})")
        print("=" * 72)
        result = subprocess.run(
            [sys.executable, script.name],
            cwd=str(script.parent),
            check=False,
        )
        results.append((folder, result.returncode))
        status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
        print(f"  -> {folder}: {status}\n")
        if result.returncode != 0 and args.stop_on_error:
            print("Stopping early because --stop-on-error was set.")
            break

    # Summary
    print("=" * 72)
    print("  Summary")
    print("=" * 72)
    width = max((len(name) for name, _ in results), default=0)
    n_ok = sum(1 for _, rc in results if rc == 0)
    n_fail = len(results) - n_ok
    for name, rc in results:
        mark = "OK  " if rc == 0 else "FAIL"
        print(f"  [{mark}] {name.ljust(width)}   exit={rc}")
    print()
    print(f"  Total: {len(results)} run, {n_ok} ok, {n_fail} failed")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
