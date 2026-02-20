---
name: agent-router
description: Use this skill to determine the correct sub-agent type for task delegation. Provides routing tables for implementation tasks and review comment fixes, along with standard invocation patterns and error handling.
---

# Sub-Agent Delegation Router

This skill defines routing tables for selecting the appropriate sub-agent when delegating tasks or review comment fixes.

## When to Activate

- When delegating implementation tasks to sub-agents
- When delegating review comment fixes to sub-agents
- When determining the appropriate `subagent_type` for a Task tool call

---

## Task-Type Routing Table

Implementation tasks should be routed based on the nature of the work. Default to `general-purpose` unless a clearly better match exists.

| Task Nature | subagent_type | Selection Criteria |
|---|---|---|
| General feature implementation | `general-purpose` | Default. Composite or mixed tasks |
| Test implementation focused | `ecc:tdd-guide` | Tasks centered on adding/modifying tests |
| E2E testing | `ecc:e2e-runner` | Playwright E2E tests |
| Build/type error fixing | `ecc:build-error-resolver` | Build errors or type errors |
| Refactoring/dead code removal | `ecc:refactor-cleaner` | Code cleanup, removing unused code |
| Security tasks | `ecc:security-reviewer` | Auth, input validation, vulnerability fixes |
| Kotlin/Quarkus implementation | `ecc:kotlin-coder` | Kotlin code, Quarkus config, native image |
| SQL/schema design | `ecc:sql-coder` | SQL, migrations, query optimization |
| JPA/Hibernate entities | `ecc:jpa-model-coder` | Entity design, relations, N+1 prevention |
| TypeScript/Next.js implementation | `ecc:nextjs-coder` | React/Next.js components, Server Actions, API routes |
| Terraform/IaC implementation | `ecc:terraform-coder` | Terraform config, modules, cloud infra, state management |
| Documentation updates | `ecc:doc-updater` | Documentation and codemap sync |
| Architecture decisions | `ecc:architect` | System design, architectural review |

---

## Review-Category Routing Table

Review comment fixes should be routed based on the category assigned by the review comment parser.

| Comment Category | subagent_type | Selection Criteria |
|---|---|---|
| security | `ecc:security-reviewer` | Security vulnerability fixes |
| performance | Domain-specific agent (*) | Performance improvements |
| bug | `general-purpose` | Bug fixes |
| code-quality | `ecc:refactor-cleaner` | Code quality improvements |
| testing | `ecc:tdd-guide` | Test additions/modifications |
| style | `general-purpose` | Style and naming fixes |
| (other) | `general-purpose` | Any other category |

(*) For `performance` comments, cross-reference the Task-Type Routing Table to select the domain-specific agent. For example: SQL performance → `ecc:sql-coder`, Kotlin performance → `ecc:kotlin-coder`. If no domain match, fall back to `general-purpose`.

---

## Standard Invocation Pattern

Use the Task tool with the following structure:

```markdown
Task tool:
- prompt: <task description + relevant context>
- subagent_type: <selected from routing table>
- description: <brief description for tracking>
```

### Required Context by Use Case

**Implementation tasks** — include in prompt:
- Task description and acceptance criteria
- Relevant design document sections
- Target file paths
- TDD instructions (if applicable)

**Review comment fixes** — include in prompt:
- Original review comment text (as blockquote for full context)
- Target file and line number
- Fix strategy / approach

---

## Context Isolation Guidelines

- Each task MUST be delegated to an independent sub-agent (separate context window)
- Do NOT pass the full session history to sub-agents
- Provide only the minimum necessary context: the specific task, relevant file paths, and applicable constraints

---

## Error Handling

| Situation | Action |
|---|---|
| Sub-agent fix fails | Report error, mark as unresolved, continue with next item |
| Sub-agent times out | Retry once with simplified prompt; if still fails, mark as unresolved |
| Wrong agent selected (output doesn't match expectations) | Re-delegate to `general-purpose` as fallback |
| Multiple related issues | Group into a single sub-agent call for coherent fixes |
