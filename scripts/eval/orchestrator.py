"""Orchestrator — for each task: execute, grade, aggregate, isolate failures."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from scripts.eval.config import EvalConfig, GraderConfig, TaskConfig
from scripts.eval.executors import Executor, get_executor
from scripts.eval.graders import GraderResult, aggregate, build_grader, summarise_status
from scripts.eval.usage import UsageSnapshot

logger = logging.getLogger(__name__)


# ---- Result schema --------------------------------------------------------


class TaskResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    task_id: str
    output: str
    grader_results: list[GraderResult]
    weighted_score: float
    status: Literal["pass", "fail", "error"]
    usage: UsageSnapshot | None
    elapsed_ms: int
    error: str = ""


class EvalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_tasks: int
    pass_count: int
    fail_count: int
    error_count: int
    weighted_average: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    cache_hit_ratio: float
    elapsed_ms: int


class EvalResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    eval_path: Path
    task_results: list[TaskResult]
    summary: EvalSummary


# ---- Orchestrator ---------------------------------------------------------


class Orchestrator:
    """Runs a fully-loaded EvalConfig and returns an EvalResult.

    Constraints encoded here:
    - Sibling task isolation: an executor exception or a per-task grader exception
      is captured into the failing TaskResult; other tasks keep running.
    - Pre-instantiated graders are reused across tasks (the grader config doesn't
      depend on per-task data, so this is safe and avoids re-parsing patterns).
    """

    def run(self, config: EvalConfig, eval_path: Path) -> EvalResult:
        executor = get_executor(config.config.executor, model=config.config.model)
        skill_md = self._load_skill_md(config.config.skill_path)
        graders = [build_grader(g.name, g.type, g.config) for g in config.graders]

        eval_started = time.perf_counter()
        task_results = [
            self._run_one(task, executor, config, skill_md, graders)
            for task in config.tasks
        ]
        eval_elapsed = int((time.perf_counter() - eval_started) * 1000)

        summary = self._summarise(task_results, eval_elapsed)
        return EvalResult(eval_path=eval_path, task_results=task_results, summary=summary)

    @staticmethod
    def _load_skill_md(skill_path: Path | None) -> str | None:
        if skill_path is None:
            return None
        try:
            return Path(skill_path).read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("failed to read skill_path %s: %s — proceeding without it", skill_path, e)
            return None

    def _run_one(
        self,
        task: TaskConfig,
        executor: Executor,
        config: EvalConfig,
        skill_md: str | None,
        graders,
    ) -> TaskResult:
        started = time.perf_counter()
        try:
            execution = executor.run(
                prompt=task.prompt,
                system_instructions=config.config.instructions,
                skill_markdown=skill_md,
                expected=task.expected,
            )
        except Exception as e:  # noqa: BLE001 — sibling-isolation boundary
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.error("task %s: executor failed: %s", task.id, e, exc_info=True)
            return TaskResult(
                task_id=task.id,
                output="",
                grader_results=[],
                weighted_score=0.0,
                status="error",
                usage=None,
                elapsed_ms=elapsed,
                error=f"executor error: {e}",
            )

        grader_results: list[GraderResult] = []
        for grader, grader_cfg in zip(graders, config.graders, strict=True):
            try:
                grader_results.append(
                    grader.grade(
                        execution.output,
                        task.expected,
                        {"task_id": task.id, "model": config.config.model},
                    )
                )
            except Exception as e:  # noqa: BLE001 — surface as GRADER_ERROR
                logger.error("task %s grader %s raised: %s", task.id, grader_cfg.name, e, exc_info=True)
                grader_results.append(
                    GraderResult(
                        grader_name=grader_cfg.name,
                        score=0.0,
                        passed=False,
                        reason=f"GRADER_ERROR: {e}",
                    )
                )

        weights = [g.weight for g in config.graders]
        score = aggregate(grader_results, weights)
        status = summarise_status(grader_results, weights)
        elapsed = int((time.perf_counter() - started) * 1000)

        return TaskResult(
            task_id=task.id,
            output=execution.output,
            grader_results=grader_results,
            weighted_score=score,
            status=status,
            usage=execution.usage,
            elapsed_ms=elapsed,
        )

    @staticmethod
    def _summarise(task_results: list[TaskResult], elapsed_ms: int) -> EvalSummary:
        total = len(task_results)
        pass_count = sum(1 for t in task_results if t.status == "pass")
        fail_count = sum(1 for t in task_results if t.status == "fail")
        error_count = sum(1 for t in task_results if t.status == "error")
        weighted_avg = (
            sum(t.weighted_score for t in task_results) / total if total else 0.0
        )

        usages = [t.usage for t in task_results if t.usage is not None]
        in_tok = sum(u.input_tokens for u in usages)
        out_tok = sum(u.output_tokens for u in usages)
        c_read = sum(u.cache_read_input_tokens for u in usages)
        c_create = sum(u.cache_creation_input_tokens for u in usages)
        denom = c_read + c_create
        cache_ratio = (c_read / denom) if denom else 0.0

        return EvalSummary(
            total_tasks=total,
            pass_count=pass_count,
            fail_count=fail_count,
            error_count=error_count,
            weighted_average=weighted_avg,
            total_input_tokens=in_tok,
            total_output_tokens=out_tok,
            total_cache_read_tokens=c_read,
            total_cache_creation_tokens=c_create,
            cache_hit_ratio=cache_ratio,
            elapsed_ms=elapsed_ms,
        )
