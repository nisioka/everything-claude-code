# Performance Optimization

## Model Selection Strategy

Choose by model tier, not by specific version — capability gaps between tiers
shift with each generation, so verify current model capabilities and pricing
in the official docs before hard-coding assumptions.

**Haiku tier** (fastest, lowest cost):
- Lightweight agents with frequent invocation
- Mechanical tasks: doc updates, formatting, classification
- Worker agents in multi-agent systems

**Sonnet tier** (balanced speed and capability):
- Main development work and most coding tasks
- Orchestrating multi-agent workflows
- Build fixes, test generation, routine refactoring

**Opus tier** (highest capability):
- Complex architectural decisions
- Long-horizon agentic work and deep debugging
- Security-sensitive reviews, research and analysis tasks

Prefer `inherit` (the session's model) for agents unless a task clearly
benefits from a cheaper or stronger tier.

## Context Window Management

Avoid last 20% of context window for:
- Large-scale refactoring
- Feature implementation spanning multiple files
- Debugging complex interactions

Lower context sensitivity tasks:
- Single-file edits
- Independent utility creation
- Documentation updates
- Simple bug fixes

## Ultrathink + Plan Mode

For complex tasks requiring deep reasoning:
1. Use `ultrathink` for enhanced thinking
2. Enable **Plan Mode** for structured approach
3. "Rev the engine" with multiple critique rounds
4. Use split role sub-agents for diverse analysis

## Build Troubleshooting

If build fails:
1. Use **build-error-resolver** agent
2. Analyze error messages
3. Fix incrementally
4. Verify after each fix
