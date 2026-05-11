# Eval Harness Skill

A formal evaluation framework for Claude Code sessions, implementing eval-driven development (EDD) principles.

## Philosophy

Eval-Driven Development treats evals as the "unit tests of AI development":
- Define expected behavior BEFORE implementation
- Run evals continuously during development
- Track regressions with each change
- Use pass@k metrics for reliability measurement

## Two complementary harnesses in this repo

This skill describes **two ways** to run evals against Claude Code skills. Pick the one that matches your need:

| Use case | Format | Where it lives | Runner |
| --- | --- | --- | --- |
| Lightweight, in-session checks (review-time, ad-hoc) | Markdown blocks (this document) | `.claude/evals/*.md` | Human / in-session Claude |
| Automated, regressable evals run on every PR | Waza-compatible YAML | `evals/<skill>/eval.yaml` + fixtures | `uv run python -m scripts.eval` |

If you're adding a one-off capability check while building a skill, use the markdown patterns lower in this document. If you want CI to fail on regressions and produce token / cache cost reports, use the YAML harness described below.

## Waza-compatible YAML Harness (auto-runnable)

A Python implementation of the [Microsoft Waza](https://github.com/microsoft/waza) YAML schema lives in `scripts/eval/`. It calls Claude via the Anthropic SDK directly (no Go required), supports prompt caching, and is wired into a GitHub Actions workflow that comments results on PRs.

### Layout

```
evals/
  make-pr-commit-message/
    eval.yaml
    fixtures/
      diff-feat-rate-limit.txt
      diff-fix-typo.txt
      diff-docs-readme.txt
  make-pr-ticket-extract/
    eval.yaml
  make-pr-sensitive-file/
    eval.yaml
    fixtures/
      files-with-secrets.txt
      files-clean.txt
scripts/eval/
  cli.py              # `python -m scripts.eval`
  config.py           # YAML → Pydantic schema
  orchestrator.py     # task-by-task execution + grading
  reporter.py         # stdout summary + JSON output
  executors/
    mock.py           # offline runner mechanics check
    anthropic.py      # real Claude API + prompt caching
  graders/
    regex.py          # match / no_match
    list_match.py     # exact / superset / subset
    llm_judge.py      # rubric-based judge with structured output
```

### Minimal commands

```bash
# Install once (pinned by uv.lock; no system Python pollution)
uv sync --frozen

# Smoke-test a suite without spending tokens (mock executor echoes expected)
uv run python -m scripts.eval evals/make-pr-commit-message/eval.yaml --executor mock

# Run for real against Anthropic API (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-... uv run python -m scripts.eval \
  evals/make-pr-commit-message/eval.yaml \
  --output results.json \
  --verbose
```

Exit codes: `0` all pass · `1` at least one task failed · `2` setup or execution error.

### eval.yaml shape

```yaml
config:
  executor: anthropic        # or "mock"
  model: claude-sonnet-4-6
  skill_path: skills/make-pr/SKILL.md  # auto-cached as a system block
  instructions: |
    Fixed system prompt for the eval (also cached).

tasks:
  - id: t1
    prompt: "...{{fixture_name}}..."   # {{name}} is replaced with fixture content
    fixtures:
      fixture_name: fixtures/some-input.txt
    expected: "feat: add x"

graders:
  - type: regex            # 1.0 if pattern matches, else 0.0
    name: conv_type
    weight: 2.0
    config:
      pattern: '^(feat|fix|docs)(\([^)]+\))?:\s'
      mode: match          # or "no_match" for negative assertions
  - type: list_match       # set comparison after parsing output
    name: items
    config:
      mode: superset       # or "exact" / "subset"
      use_task_expected: true   # use per-task `expected` (a list) as the items
  - type: llm_judge        # rubric-based scoring via a separate Claude call
    name: subject_quality
    config:
      judge_model: claude-sonnet-4-6
      rubric: |
        Score 1.0 when subject is concise (<72 chars), imperative mood, ...
```

### Capability / Regression Eval ↔ YAML mapping

The markdown EDD concepts translate to YAML like this:

| Markdown concept | YAML mechanism |
| --- | --- |
| **Capability Eval** ("can Claude do X?") | A task with `expected` set + a `regex` / `list_match` / `llm_judge` grader checking the success criterion |
| **Regression Eval** ("does it still work?") | The same eval.yaml committed in the repo; CI re-runs it on every PR and a score drop is flagged in the PR comment |
| **Code-Based Grader** | `regex` or `list_match` (deterministic, no API cost) |
| **Model-Based Grader** | `llm_judge` (separate judge model + rubric, returns score + reason) |
| **Human Grader** | Stays in markdown — YAML harness does not gate on humans |
| **pass@k metrics** | Run the suite k times and aggregate; the harness emits weighted_score per task and pass/fail/error counts per run |

### CI integration

`.github/workflows/eval-make-pr.yml` runs each `evals/make-pr-*/eval.yaml` in a matrix on `pull_request` events, posts a single PR comment that updates in place across pushes, and fails the workflow when any suite reports `fail` or `error`. The job is skipped when `ANTHROPIC_API_KEY` is not configured (e.g., on fork PRs), and `paths` filters mean unrelated PRs don't pay the API cost.

### When to add a YAML eval

Add a YAML suite when **all** of these hold:
- The skill has 2+ shippable phases that can be evaluated in isolation (no full git/PR/file-system dance)
- You have stable fixtures (diffs, file lists, branch names) that won't drift
- You're willing to spend ~$0.10 / PR for the regression signal

Stick with markdown evals when you're sketching a skill or doing one-off capability checks.

## Eval Types

### Capability Evals
Test if Claude can do something it couldn't before:
```markdown
[CAPABILITY EVAL: feature-name]
Task: Description of what Claude should accomplish
Success Criteria:
  - [ ] Criterion 1
  - [ ] Criterion 2
  - [ ] Criterion 3
Expected Output: Description of expected result
```

### Regression Evals
Ensure changes don't break existing functionality:
```markdown
[REGRESSION EVAL: feature-name]
Baseline: SHA or checkpoint name
Tests:
  - existing-test-1: PASS/FAIL
  - existing-test-2: PASS/FAIL
  - existing-test-3: PASS/FAIL
Result: X/Y passed (previously Y/Y)
```

## Grader Types

### 1. Code-Based Grader
Deterministic checks using code:
```bash
# Check if file contains expected pattern
grep -q "export function handleAuth" src/auth.ts && echo "PASS" || echo "FAIL"

# Check if tests pass
npm test -- --testPathPattern="auth" && echo "PASS" || echo "FAIL"

# Check if build succeeds
npm run build && echo "PASS" || echo "FAIL"
```

### 2. Model-Based Grader
Use Claude to evaluate open-ended outputs:
```markdown
[MODEL GRADER PROMPT]
Evaluate the following code change:
1. Does it solve the stated problem?
2. Is it well-structured?
3. Are edge cases handled?
4. Is error handling appropriate?

Score: 1-5 (1=poor, 5=excellent)
Reasoning: [explanation]
```

### 3. Human Grader
Flag for manual review:
```markdown
[HUMAN REVIEW REQUIRED]
Change: Description of what changed
Reason: Why human review is needed
Risk Level: LOW/MEDIUM/HIGH
```

## Metrics

### pass@k
"At least one success in k attempts"
- pass@1: First attempt success rate
- pass@3: Success within 3 attempts
- Typical target: pass@3 > 90%

### pass^k
"All k trials succeed"
- Higher bar for reliability
- pass^3: 3 consecutive successes
- Use for critical paths

## Eval Workflow

### 1. Define (Before Coding)
```markdown
## EVAL DEFINITION: feature-xyz

### Capability Evals
1. Can create new user account
2. Can validate email format
3. Can hash password securely

### Regression Evals
1. Existing login still works
2. Session management unchanged
3. Logout flow intact

### Success Metrics
- pass@3 > 90% for capability evals
- pass^3 = 100% for regression evals
```

### 2. Implement
Write code to pass the defined evals.

### 3. Evaluate
```bash
# Run capability evals
[Run each capability eval, record PASS/FAIL]

# Run regression evals
npm test -- --testPathPattern="existing"

# Generate report
```

### 4. Report
```markdown
EVAL REPORT: feature-xyz
========================

Capability Evals:
  create-user:     PASS (pass@1)
  validate-email:  PASS (pass@2)
  hash-password:   PASS (pass@1)
  Overall:         3/3 passed

Regression Evals:
  login-flow:      PASS
  session-mgmt:    PASS
  logout-flow:     PASS
  Overall:         3/3 passed

Metrics:
  pass@1: 67% (2/3)
  pass@3: 100% (3/3)

Status: READY FOR REVIEW
```

## Integration Patterns

### Pre-Implementation
```
/eval define feature-name
```
Creates eval definition file at `.claude/evals/feature-name.md`

### During Implementation
```
/eval check feature-name
```
Runs current evals and reports status

### Post-Implementation
```
/eval report feature-name
```
Generates full eval report

## Eval Storage

Store evals in project:
```
.claude/
  evals/
    feature-xyz.md      # Eval definition
    feature-xyz.log     # Eval run history
    baseline.json       # Regression baselines
```

## Best Practices

1. **Define evals BEFORE coding** - Forces clear thinking about success criteria
2. **Run evals frequently** - Catch regressions early
3. **Track pass@k over time** - Monitor reliability trends
4. **Use code graders when possible** - Deterministic > probabilistic
5. **Human review for security** - Never fully automate security checks
6. **Keep evals fast** - Slow evals don't get run
7. **Version evals with code** - Evals are first-class artifacts

## Example: Adding Authentication

```markdown
## EVAL: add-authentication

### Phase 1: Define (10 min)
Capability Evals:
- [ ] User can register with email/password
- [ ] User can login with valid credentials
- [ ] Invalid credentials rejected with proper error
- [ ] Sessions persist across page reloads
- [ ] Logout clears session

Regression Evals:
- [ ] Public routes still accessible
- [ ] API responses unchanged
- [ ] Database schema compatible

### Phase 2: Implement (varies)
[Write code]

### Phase 3: Evaluate
Run: /eval check add-authentication

### Phase 4: Report
EVAL REPORT: add-authentication
==============================
Capability: 5/5 passed (pass@3: 100%)
Regression: 3/3 passed (pass^3: 100%)
Status: SHIP IT
```
