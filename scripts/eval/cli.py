"""CLI entry point for the eval harness. Wired up properly in task 5.3."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.eval",
        description="Run a Waza-compatible eval YAML against an executor.",
    )
    parser.add_argument("eval_yaml", nargs="?", help="Path to the eval.yaml file")
    parser.add_argument(
        "--executor",
        choices=["mock", "anthropic"],
        default=None,
        help="Override config.executor in the YAML",
    )
    parser.add_argument("--output", default=None, help="Path to write the EvalResult JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.eval_yaml is None:
        parser.print_help()
        return 0
    # Real wiring is added in task 5.3.
    print(f"[eval-harness skeleton] would run: {args.eval_yaml}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
