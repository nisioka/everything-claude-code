"""Eval harness CLI entry point. Re-exports cli.main() so `python -m scripts.eval` works."""

from scripts.eval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
