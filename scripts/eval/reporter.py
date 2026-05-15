"""Reporter — pretty-print summary to stdout, optionally write EvalResult JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from scripts.eval.orchestrator import EvalResult, TaskResult


class Reporter:
    """Render an EvalResult: terminal summary + optional JSON file."""

    def print_summary(
        self,
        result: EvalResult,
        *,
        verbose: bool = False,
        out: TextIO | None = None,
    ) -> None:
        out = out or sys.stdout
        s = result.summary
        print(f"Eval:    {result.eval_path}", file=out)
        print(
            f"Tasks:   {s.total_tasks} total | "
            f"pass={s.pass_count} fail={s.fail_count} error={s.error_count}",
            file=out,
        )
        print(
            f"Score:   weighted_average={s.weighted_average:.3f} "
            f"elapsed={s.elapsed_ms} ms",
            file=out,
        )
        if s.total_input_tokens or s.total_cache_read_tokens or s.total_cache_creation_tokens:
            print(
                f"Tokens:  input={s.total_input_tokens} output={s.total_output_tokens} "
                f"cache_read={s.total_cache_read_tokens} "
                f"cache_create={s.total_cache_creation_tokens} "
                f"cache_hit_ratio={s.cache_hit_ratio:.3f}",
                file=out,
            )

        if verbose:
            print("", file=out)
            for tr in result.task_results:
                self._print_task(tr, out)

    @staticmethod
    def _print_task(tr: TaskResult, out: TextIO) -> None:
        print(
            f"  [{tr.status:5s}] {tr.task_id}  "
            f"score={tr.weighted_score:.3f}  elapsed={tr.elapsed_ms}ms",
            file=out,
        )
        for gr in tr.grader_results:
            tag = "PASS" if gr.passed else "FAIL"
            print(f"      - {gr.grader_name:20s} [{tag}] {gr.score:.2f}  {gr.reason}", file=out)
        if tr.usage is not None:
            u = tr.usage
            print(
                f"      tokens: input={u.input_tokens} output={u.output_tokens} "
                f"cache_read={u.cache_read_input_tokens} "
                f"cache_create={u.cache_creation_input_tokens}",
                file=out,
            )
        if tr.error:
            print(f"      error: {tr.error}", file=out)

    def write_json(self, result: EvalResult, path: Path) -> None:
        payload = json.loads(result.model_dump_json())
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
