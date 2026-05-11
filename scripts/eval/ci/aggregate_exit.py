"""Print the aggregated exit code across all eval result JSONs in a directory.

Returns:
- 0 if every suite has 0 fail / 0 error
- 1 if any suite reported fail (and none reported error)
- 2 if any suite reported error (highest precedence)

Used by the GitHub Actions workflow to decide whether to fail the run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: aggregate_exit.py <results_dir>", file=sys.stderr)
        return 2
    results_dir = Path(argv[1])
    overall = 0
    for path in sorted(results_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Treat unreadable artifacts as the highest severity but keep scanning so
            # the workflow log shows every problem file rather than only the first.
            overall = max(overall, 2)
            print(f"WARN: could not read {path}", file=sys.stderr)
            continue
        s = payload["summary"]
        if s.get("error_count", 0) > 0:
            overall = max(overall, 2)
        elif s.get("fail_count", 0) > 0:
            overall = max(overall, 1)
    print(overall)
    return overall


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
