# Coding Style

## Immutability (CRITICAL)

ALWAYS create new objects, NEVER mutate:

```javascript
// WRONG: Mutation
function updateUser(user, name) {
  user.name = name  // MUTATION!
  return user
}

// CORRECT: Immutability
function updateUser(user, name) {
  return {
    ...user,
    name
  }
}
```

## Code Comments

Comment the code's **intent**, never its **history**.

- Do NOT narrate implementation history in comments: review feedback, bugs found during testing, "changed from X", "fixed per review", review rounds. That context belongs in the commit message, the PR description, or your reply to the user — not in the source.
- Write a comment only when intent is not readable from the code itself — e.g. a non-obvious operational constraint (a production incident, an external-system quirk) that the code alone cannot convey.
- Do NOT embed spec or requirement IDs in code (e.g. `Requirement 3.5`, `Requirements 8.1–8.3`, task numbers). They point at transient process docs the reader cannot follow from the code, so the number carries no usable information.

```python
# WRONG: narrates review/test history and a requirement ID
# Fixed per review round 2: server-side filtering instead of client-side.
# Default pass threshold (Requirement 3.5).
DEFAULT_PASS_THRESHOLD = 0.5

# CORRECT: explains intent only
# Task-level threshold; graders may still apply their own per-result cutoff.
DEFAULT_PASS_THRESHOLD = 0.5
```

## File Organization

MANY SMALL FILES > FEW LARGE FILES:
- High cohesion, low coupling
- 200-400 lines typical, 800 max
- Extract utilities from large components
- Organize by feature/domain, not by type

## Error Handling

ALWAYS handle errors comprehensively:

```typescript
try {
  const result = await riskyOperation()
  return result
} catch (error) {
  console.error('Operation failed:', error)
  throw new Error('Detailed user-friendly message')
}
```

## Input Validation

ALWAYS validate user input:

```typescript
import { z } from 'zod'

const schema = z.object({
  email: z.string().email(),
  age: z.number().int().min(0).max(150)
})

const validated = schema.parse(input)
```

## Code Quality Checklist

Before marking work complete:
- [ ] Code is readable and well-named
- [ ] Functions are small (<50 lines)
- [ ] Files are focused (<800 lines)
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling
- [ ] No console.log statements
- [ ] No hardcoded values
- [ ] No mutation (immutable patterns used)
- [ ] Comments explain intent, not implementation history; no spec/requirement IDs
