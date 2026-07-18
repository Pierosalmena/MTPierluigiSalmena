#!/usr/bin/env python3
"""
run_all_traces.py

Runs trace_ragas_allv3.py inside:
  classification/BASIC/CAT1
  classification/BASIC/CAT2
  classification/DRIFT/CAT1
  classification/DRIFT/CAT2
  resolution/BASIC/CAT1
  resolution/BASIC/CAT2
  resolution/DRIFT/CAT1
  resolution/DRIFT/CAT2

Each script is launched with its own folder as cwd so relative paths
(./answers, ./trace_exports) resolve correctly.
"""

import subprocess
import sys
import time
from pathlib import Path

# --- Config -----------------------------------------------------------------
BASE = Path(__file__).resolve().parent
ROOTS = ["classification", "resolution"]
GROUPS = ["BASIC", "DRIFT"]
CATS = ["CAT1", "CAT2"]
SCRIPT_NAME = "trace_ragas_allv3.py"
STOP_ON_ERROR = False   # set True if you want to abort on first failure
PYTHON = sys.executable  # use the same interpreter that runs this file
# ----------------------------------------------------------------------------


def run_one(script_path: Path) -> tuple[bool, float]:
    """Run a single script in its own directory. Returns (success, duration)."""
    start = time.time()
    print(f"\n{'=' * 70}")
    print(f"▶ Running: {script_path.relative_to(BASE)}")
    print(f"  cwd    : {script_path.parent}")
    print(f"{'=' * 70}", flush=True)

    try:
        result = subprocess.run(
            [PYTHON, script_path.name],
            cwd=script_path.parent,
            check=False,
        )
        ok = result.returncode == 0
    except Exception as e:
        print(f"  ✗ Failed to launch: {e}")
        ok = False

    dur = time.time() - start
    status = "✓ OK" if ok else "✗ FAILED"
    print(f"\n{status}  ({dur:0.1f}s)")
    return ok, dur


def main() -> int:
    targets = []
    for root in ROOTS:
        root_path = BASE / root
        if not root_path.exists():
            print(f"WARN: missing root folder {root_path}")
            continue
        for g in GROUPS:
            for c in CATS:
                p = root_path / g / c / SCRIPT_NAME
                if p.is_file():
                    targets.append(p)
                else:
                    print(f"WARN: missing {p}")

    if not targets:
        print("No scripts found.")
        return 2

    print(f"Found {len(targets)} script(s) to run.")
    results = []
    for p in targets:
        ok, dur = run_one(p)
        results.append((p, ok, dur))
        if not ok and STOP_ON_ERROR:
            print("\nStopping due to STOP_ON_ERROR=True")
            break

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = 0.0
    for p, ok, dur in results:
        tag = "OK   " if ok else "FAIL "
        rel = p.relative_to(BASE)
        print(f"  [{tag}] {dur:6.1f}s  {rel}")
        total += dur
    failed = sum(1 for _, ok, _ in results if not ok)
    print("-" * 70)
    print(f"  {len(results)} run · {failed} failed · total {total:0.1f}s")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())