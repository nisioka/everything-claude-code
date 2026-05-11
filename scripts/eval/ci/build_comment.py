"""Build the PR comment markdown body from result JSONs in a directory.

Usage:
    uv run python scripts/eval/ci/build_comment.py <results_dir>

Reads every *.json in the given directory (each produced by `scripts.eval --output`)
and writes a Markdown summary to stdout. Includes a hidden HTML marker so the
workflow's update-or-create logic can find the existing comment to update.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "<!-- eval-make-pr-comment -->"


def _row(name: str, payload: dict) -> str:
    s = payload["summary"]
    status = "✅" if s["fail_count"] == 0 and s["error_count"] == 0 else "❌"
    cache = f"{s['cache_hit_ratio']:.0%}"
    return (
        f"| {status} | `{name}` | {s['pass_count']}/{s['total_tasks']} | "
        f"{s['fail_count']} | {s['error_count']} | "
        f"{s['weighted_average']:.2f} | "
        f"{s['total_input_tokens']} | "
        f"{s['total_output_tokens']} | {cache} | {s['elapsed_ms']} ms |"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: build_comment.py <results_dir>", file=sys.stderr)
        return 2
    results_dir = Path(argv[1])
    files = sorted(results_dir.glob("*.json"))

    lines = [
        MARKER,
        "## 🧪 make-pr eval results",
        "",
        "| Status | Suite | Pass / Total | Fail | Error | Score | Input tokens | Output tokens | Cache hit | Elapsed |",
        "| :---: | --- | :---: | :---: | :---: | :---: | ---: | ---: | ---: | ---: |",
    ]

    if not files:
        lines.append("| ⚠️ | _no results_ | – | – | – | – | – | – | – | – |")
    else:
        for f in files:
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                lines.append(f"| ⚠️ | `{f.stem}` | parse-error: {e} | | | | | | | |")
                continue
            lines.append(_row(f.stem, payload))

    lines.append("")
    lines.append("_See workflow artifacts for full per-task breakdown._")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
