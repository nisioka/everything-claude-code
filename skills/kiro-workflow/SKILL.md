---
name: kiro-workflow
description: Use this skill when executing the full Kiro spec-driven development workflow. Runs spec-init → spec-requirements → spec-design → spec-tasks sequentially, with user approval gates between each phase. Invoke when the user wants to create a complete specification from a project description in one flow.
---

# Kiro Workflow Skill

Orchestrates the full Kiro specification workflow by executing the four phases in sequence:
**Init → Requirements → Design → Tasks**

## When to Activate

- User wants to run the full Kiro spec workflow end-to-end
- User provides a project description and wants to generate a complete specification
- User says "kiro workflow", "spec workflow", "create spec", or similar
- User wants to go from idea to implementation-ready tasks in one flow

## Workflow Overview

```
Phase 1: Init          → Create spec directory and metadata
    ↓ (automatic)
Phase 2: Requirements  → Generate EARS-format requirements
    ↓ (user approval)
Phase 3: Design        → Create technical design document
    ↓ (user approval)
Phase 4: Tasks         → Generate implementation task list
    ↓ (user approval)
Done: Ready for /kiro:spec-impl
```

---

## Phase 1: Spec Initialization

Execute the same logic as `/kiro:spec-init`.

### Steps

1. **Receive project description** from user (or use `$ARGUMENTS`)
2. **Generate feature name** from the project description
3. **Check uniqueness** in `.kiro/specs/` — append numeric suffix if conflict exists
4. **Create directory**: `.kiro/specs/<feature-name>/`
5. **Initialize files using templates**:
   - Read `.kiro/settings/templates/specs/init.json`
   - Read `.kiro/settings/templates/specs/requirements-init.md`
   - Replace placeholders: `{{FEATURE_NAME}}`, `{{TIMESTAMP}}`, `{{PROJECT_DESCRIPTION}}`
   - Write `spec.json` and `requirements.md`
6. **Report** created files and generated feature name

### Transition to Phase 2

- Proceed **automatically** to Phase 2 (no user approval needed — init is just scaffolding)
- Pass the generated `<feature-name>` to Phase 2

---

## Phase 2: Requirements Generation

Execute the same logic as `/kiro:spec-requirements`.

### Steps

1. **Load context**:
   - Read `.kiro/specs/<feature-name>/spec.json` and `requirements.md`
   - Read **all** `.kiro/steering/` files for project memory
2. **Read guidelines**:
   - `.kiro/settings/rules/ears-format.md`
   - `.kiro/settings/templates/specs/requirements.md`
3. **Generate requirements**:
   - Group functionality into logical requirement areas
   - Apply EARS format to all acceptance criteria
   - Use numeric IDs only for requirement headings
   - Use language specified in `spec.json`
4. **Update metadata** in `spec.json`:
   - `phase: "requirements-generated"`
   - `approvals.requirements.generated: true`
5. **Present requirements summary** to user

### Approval Gate

- **Show** generated requirements summary to the user
- **Ask** user to approve or request modifications
- If **approved**: proceed to Phase 3
- If **modifications requested**: regenerate requirements with feedback, then re-ask

---

## Phase 3: Technical Design Generation

Execute the same logic as `/kiro:spec-design`.

### Steps

1. **Load context**:
   - Read spec.json, requirements.md, and all steering files
   - Read `.kiro/settings/templates/specs/design.md` and `.kiro/settings/rules/design-principles.md`
   - Read `.kiro/settings/templates/specs/research.md`
2. **Auto-approve requirements** in spec.json (user already approved in Phase 2 gate)
3. **Classify feature type** (New / Extension / Simple / Complex) and execute appropriate discovery:
   - Complex/New → `.kiro/settings/rules/design-discovery-full.md`
   - Extension → `.kiro/settings/rules/design-discovery-light.md`
   - Simple → minimal pattern check
4. **Persist findings** to `.kiro/specs/<feature-name>/research.md`
5. **Generate design document** following `specs/design.md` template:
   - Architecture Pattern & Boundary Map
   - Technology Stack & Alignment
   - Components & Interface Contracts
   - Type safety enforcement
6. **Update metadata** in `spec.json`:
   - `phase: "design-generated"`
   - `approvals.design.generated: true`
   - `approvals.requirements.approved: true`
7. **Present design summary** to user

### Approval Gate

- **Show** design summary (discovery type, key findings, component overview)
- **Ask** user to approve or request modifications
- If **approved**: proceed to Phase 4
- If **modifications requested**: regenerate design with feedback, then re-ask

---

## Phase 4: Task Generation

Execute the same logic as `/kiro:spec-tasks`.

### Steps

1. **Load context**:
   - Read spec.json, requirements.md, design.md, and all steering files
2. **Auto-approve design** in spec.json (user already approved in Phase 3 gate)
3. **Load generation rules**:
   - `.kiro/settings/rules/tasks-generation.md`
   - `.kiro/settings/rules/tasks-parallel-analysis.md` (for parallel markers)
   - `.kiro/settings/templates/specs/tasks.md`
4. **Generate task list**:
   - Map all requirements to tasks
   - Ensure all design components are covered
   - Use numeric requirement IDs only
   - Apply `(P)` markers for parallelizable tasks
   - Maximum 2 levels (major tasks + sub-tasks)
5. **Update metadata** in `spec.json`:
   - `phase: "tasks-generated"`
   - `approvals.tasks.generated: true`
   - `approvals.design.approved: true`
6. **Present task summary** to user

### Approval Gate

- **Show** task summary (total major tasks, sub-tasks, requirement coverage)
- **Ask** user to approve or request modifications
- If **approved**: workflow complete
- If **modifications requested**: regenerate tasks with feedback, then re-ask

---

## Completion

After all four phases are done and tasks are approved, output:

1. **Workflow Summary**:
   - Feature name and spec path
   - Requirements count
   - Design components count
   - Task count (major + sub-tasks)
2. **Next Steps**:
   - Clear conversation context before implementation
   - Execute tasks: `/kiro:spec-impl <feature-name> <task-number>`
   - Or execute all: `/kiro:spec-impl <feature-name>`

---

## Critical Constraints

- **Phase separation**: Each phase must complete fully before the next begins
- **User approval required**: Requirements, design, and tasks each require explicit user approval before proceeding
- **No skipping phases**: All four phases must execute in order
- **Template adherence**: Use `.kiro/settings/templates/` and `.kiro/settings/rules/` strictly
- **Language consistency**: Use the language specified in `spec.json` throughout all phases
- **Numeric IDs only**: Requirement headings must use numeric IDs (never alphabetic)
- **EARS format**: All acceptance criteria must follow EARS patterns

## Error Handling

| Situation | Action |
|---|---|
| Missing templates in `.kiro/settings/` | Report specific missing file, suggest checking repo setup |
| Feature name conflict | Auto-append numeric suffix, notify user |
| Steering directory empty | Warn that project context is missing, proceed with limitation noted |
| User rejects phase output | Collect feedback, regenerate that phase, re-present for approval |
| Missing numeric requirement IDs | Stop and fix before proceeding to next phase |
| Spec directory doesn't exist | Create it during Phase 1 |

## Tool Guidance

- **Read first**: Always load all context, templates, and rules before generating output
- **Write last**: Generate documents only after all analysis is complete
- **WebSearch/WebFetch**: Use for external dependency research during design phase
- **Grep**: Analyze existing codebase patterns during design discovery
- **Glob**: Check spec directory uniqueness and find existing files
