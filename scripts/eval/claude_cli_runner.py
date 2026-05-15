"""subprocess wrapper around `claude -p --output-format json`.

Central invocation point for the Claude Code CLI. Both ClaudeCliExecutor and
LlmJudgeGrader route their model calls through here so timeout, JSON parsing,
tool-disabling, and error mapping are defined once.

Auth is delegated to the CLI's own credential lookup (`claude login` OAuth token,
`CLAUDE_CODE_OAUTH_TOKEN`, or `ANTHROPIC_API_KEY` — see Claude Code docs); this
module never touches API keys directly.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from scripts.eval.errors import ClaudeCliError
from scripts.eval.usage import UsageSnapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 300

# Default Claude Code session pulls in Bash/Edit/Read/WebFetch/... so even a
# simple "answer the prompt" task can decide to call tools mid-response. For an
# eval we want pure completion — disable every tool we know about by name. Any
# tool not in this list still goes through Claude Code's permission system, so
# new tools default to "ask", not "allow".
_DISALLOWED_TOOLS = ",".join(
    [
        "Bash",
        "BashOutput",
        "Edit",
        "Glob",
        "Grep",
        "KillBash",
        "NotebookEdit",
        "Read",
        "SlashCommand",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    ]
)


@dataclass(frozen=True)
class CliResult:
    text: str
    usage: UsageSnapshot
    model: str | None = None
    cost_usd: float | None = None


def run_claude_cli(
    *,
    prompt: str,
    system_prompt: str,
    model: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    extra_args: Sequence[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> CliResult:
    """Invoke `claude -p` and return the assistant output + usage.

    The prompt is piped via stdin so large fixtures don't hit ARG_MAX.
    `runner` is an injection point for tests; production callers leave it None
    and we use `subprocess.run`.
    """
    cli = shutil.which("claude")
    if cli is None:
        raise ClaudeCliError(
            "`claude` CLI is not on PATH; install Claude Code and run `claude login` first"
        )

    cmd = [
        cli,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--system-prompt",
        system_prompt,
        "--disallowed-tools",
        _DISALLOWED_TOOLS,
    ]
    if extra_args:
        cmd.extend(extra_args)

    runner_fn = runner or subprocess.run
    try:
        completed = runner_fn(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeCliError(f"claude CLI timed out after {timeout_sec}s") from e
    except FileNotFoundError as e:
        raise ClaudeCliError(f"failed to spawn claude CLI: {e}") from e

    if completed.returncode != 0:
        stderr_snippet = (completed.stderr or "")[:500]
        raise ClaudeCliError(
            f"claude CLI exited {completed.returncode}: stderr={stderr_snippet!r}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as e:
        snippet = (completed.stdout or "")[:500]
        raise ClaudeCliError(
            f"claude CLI output was not valid JSON: {e}; stdout[:500]={snippet!r}"
        ) from e

    if payload.get("is_error"):
        status = payload.get("api_error_status")
        detail = str(payload.get("result") or "(no detail)")[:300]
        raise ClaudeCliError(
            f"claude CLI reported is_error=true (api_error_status={status}): {detail}"
        )

    text = payload.get("result")
    if not isinstance(text, str):
        raise ClaudeCliError(
            f"claude CLI JSON missing `result` string; payload keys={list(payload)}"
        )

    usage_obj = payload.get("usage") or {}
    usage = UsageSnapshot(
        input_tokens=int(usage_obj.get("input_tokens", 0) or 0),
        output_tokens=int(usage_obj.get("output_tokens", 0) or 0),
        cache_read_input_tokens=int(usage_obj.get("cache_read_input_tokens", 0) or 0),
        cache_creation_input_tokens=int(
            usage_obj.get("cache_creation_input_tokens", 0) or 0
        ),
    )

    model_used: str | None = None
    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        model_used = next(iter(model_usage))

    cost_raw = payload.get("total_cost_usd")
    cost = float(cost_raw) if isinstance(cost_raw, (int, float)) else None

    return CliResult(text=text, usage=usage, model=model_used, cost_usd=cost)
