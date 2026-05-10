"""eval.yaml schema (Pydantic) + ConfigLoader (YAML → EvalConfig).

Implements requirements 1.1–1.8.

The schema is intentionally a Waza-compatible subset: top-level `config` (executor /
model / skill_path / instructions), `tasks` (id / prompt / expected / fixtures), and
`graders` (type / name / weight / config). All models are frozen so EvalConfig instances
are safe to share across the orchestration pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError
from yaml import YAMLError

from scripts.eval.errors import ConfigValidationError


# ---- Pydantic models -------------------------------------------------------


class GraderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["regex", "list_match", "llm_judge"]
    name: str
    weight: float = 1.0
    config: dict[str, Any] = {}


class TaskConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    prompt: str
    expected: Any | None = None
    fixtures: dict[str, str] = {}


class RunnerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    executor: Literal["mock", "anthropic"] = "mock"
    model: str = "claude-sonnet-4-6"
    skill_path: Path | None = None
    instructions: str = ""


class EvalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: RunnerConfig
    tasks: list[TaskConfig]
    graders: list[GraderConfig]


# ---- Loader ---------------------------------------------------------------


class ConfigLoader:
    """Load an eval.yaml into a fully-resolved EvalConfig.

    Resolution rules:
    - `tasks[].fixtures` paths are relative to the eval.yaml's parent directory.
    - Each fixture file's contents replace `{{<name>}}` placeholders inside the task's
      prompt string.
    - All schema violations and IO failures are wrapped as `ConfigValidationError` so
      callers only need to handle one exception type.
    """

    def load(self, eval_yaml_path: Path) -> EvalConfig:
        path = Path(eval_yaml_path)
        if not path.is_file():
            raise ConfigValidationError(f"eval.yaml not found: {path}")

        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigValidationError(f"failed to read {path}: {e}") from e

        try:
            raw = yaml.safe_load(raw_text)
        except YAMLError as e:
            raise ConfigValidationError(f"invalid YAML in {path}: {e}") from e

        if not isinstance(raw, dict):
            raise ConfigValidationError(
                f"top-level eval.yaml must be a mapping, got {type(raw).__name__}: {path}"
            )

        # Resolve fixtures + interpolate prompts before Pydantic validation so the model
        # contract reflects the prompt the executor will actually receive.
        try:
            self._resolve_fixtures(raw, path.parent)
        except ConfigValidationError:
            raise
        except Exception as e:
            raise ConfigValidationError(f"fixture resolution failed in {path}: {e}") from e

        try:
            return EvalConfig.model_validate(raw)
        except ValidationError as e:
            raise ConfigValidationError(f"schema validation failed for {path}:\n{e}") from e

    @staticmethod
    def _resolve_fixtures(raw: dict[str, Any], base_dir: Path) -> None:
        tasks = raw.get("tasks")
        if not isinstance(tasks, list):
            return

        for task in tasks:
            if not isinstance(task, dict):
                continue
            fixtures = task.get("fixtures") or {}
            prompt = task.get("prompt")
            if not isinstance(fixtures, dict) or not isinstance(prompt, str):
                continue

            for name, rel_path in fixtures.items():
                fixture_path = (base_dir / rel_path).resolve()
                if not fixture_path.is_file():
                    raise ConfigValidationError(
                        f"fixture '{name}' references missing file: {rel_path} "
                        f"(resolved to {fixture_path})"
                    )
                try:
                    content = fixture_path.read_text(encoding="utf-8")
                except OSError as e:
                    raise ConfigValidationError(
                        f"failed to read fixture '{name}' at {fixture_path}: {e}"
                    ) from e
                prompt = prompt.replace("{{" + name + "}}", content)

            task["prompt"] = prompt
