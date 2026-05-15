"""Domain-specific exception hierarchy for the eval harness."""

from __future__ import annotations


class EvalHarnessError(Exception):
    """Base class for all eval harness errors."""


class ConfigValidationError(EvalHarnessError):
    """Raised when an eval.yaml fails schema validation or fixture resolution."""


class UnknownExecutorError(EvalHarnessError):
    """Raised when a requested executor name is not registered."""


class UnknownGraderError(EvalHarnessError):
    """Raised when a requested grader type is not registered."""


class ClaudeCliError(EvalHarnessError):
    """Raised when `claude -p` exits non-zero, times out, or reports is_error=true."""
