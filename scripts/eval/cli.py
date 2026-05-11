"""CLI entry point for the eval harness.

Exit codes (Requirement 4.5):
- 0: every task passed
- 1: at least one task failed (model output didn't satisfy graders)
- 2: configuration / runtime error (YAML invalid, executor missing, missing API key, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from scripts.eval.config import ConfigLoader, EvalConfig, RunnerConfig
from scripts.eval.errors import EvalHarnessError
from scripts.eval.orchestrator import Orchestrator
from scripts.eval.reporter import Reporter

logger = logging.getLogger("scripts.eval")


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
    parser.add_argument("--verbose", action="store_true", help="Print per-task grader breakdown")
    return parser


def _override_executor(cfg: EvalConfig, executor: str) -> EvalConfig:
    """Build a new EvalConfig with config.executor swapped (models are frozen)."""
    new_runner = cfg.config.model_copy(update={"executor": executor})
    return cfg.model_copy(update={"config": new_runner})


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.eval_yaml is None:
        parser.print_help()
        return 0

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    eval_path = Path(args.eval_yaml)
    try:
        cfg = ConfigLoader().load(eval_path)
        if args.executor is not None:
            try:
                cfg = _override_executor(cfg, args.executor)
            except ValidationError as e:
                print(f"ERROR: invalid --executor override: {e}", file=sys.stderr)
                return 2
        result = Orchestrator().run(cfg, eval_path)
    except EvalHarnessError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — top-level safety net
        logger.exception("unexpected error")
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    reporter = Reporter()
    reporter.print_summary(result, verbose=args.verbose)
    if args.output:
        reporter.write_json(result, Path(args.output))

    if result.summary.error_count > 0:
        return 2
    if result.summary.fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
