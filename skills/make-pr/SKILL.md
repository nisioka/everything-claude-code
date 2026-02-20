---
name: make-pr
description: Use this skill when performing the git workflow of commit, push, and pull request creation. Handles staged file selection, commit message generation, push with error handling, and PR creation with template support and ticket number extraction.
---

# Git Workflow Skill (Commit → Push → Pull Request)

This skill defines the complete workflow for committing changes, pushing to remote, and creating a pull request.

## When to Activate

- User requests to commit and push changes
- User requests to create a pull request
- User requests the full commit → push → PR workflow
- After completing a feature implementation or bug fix

## Workflow Overview

```
1. Pre-commit checks
2. Stage & Commit
3. Push
4. Pull Request creation
```

---

## Phase 1: Pre-commit Checks

### 1.1 Identify Changed Files

Run `git status` to identify files with changes. Classify files into:

- **Modified files (tracked)**: Files that were intentionally edited during this session
- **Auto-generated files**: Outputs from build tools, code generators, formatters, etc.
- **Unrelated files**: Files that should NOT be committed

**Rules:**
- Only commit files that were modified as part of the current task
- Include auto-generated outputs if a generation tool was explicitly executed
- NEVER blindly use `git add -A` or `git add .`
- Stage specific files by name: `git add <file1> <file2> ...`

### 1.2 Sensitive File Check

Before staging, check that NONE of the following are included in the commit:

- `.env`, `.env.local`, `.env.production`, `.env.*` (environment variable files)
- `credentials.json`, `serviceAccountKey.json` (credential files)
- `*.pem`, `*.key`, `*.p12`, `*.pfx` (private keys / certificates)
- `id_rsa`, `id_ed25519` (SSH keys)
- `*.secret`, `token.txt` (secret files)
- Any file containing API keys, passwords, or tokens in its content

**If a sensitive file is detected:**
- STOP and warn the user
- Do NOT proceed with the commit until the user explicitly confirms or removes the file

### 1.3 Large File Check

Warn if any staged file exceeds **5MB**. Large files may indicate:
- Build artifacts that should be in `.gitignore`
- Binary files that should use Git LFS
- Data files that don't belong in the repository

**If a large file is detected:**
- Warn the user with the file name and size
- Ask for confirmation before proceeding

### 1.4 Review Diff Summary

Present `git diff --stat` (for staged files) to the user and confirm the changes are correct before committing.

```bash
git diff --cached --stat
```

Show the user:
- Number of files changed
- Lines added / removed per file
- Total changes summary

Ask the user to confirm these are the intended changes.

---

## Phase 2: Commit

### 2.1 Commit Message Convention

Check the project for existing commit message conventions:

1. Check for a `commitlint` config, `.commitlintrc`, or similar
2. Check recent `git log --oneline -10` for the project's commit style
3. If Conventional Commits are used, follow: `type(scope): description`
   - Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `style`, `perf`, `ci`, `build`
4. If no convention is detected, use a clear and descriptive message

### 2.2 Execute Commit

```bash
git add <specific-files>
git commit -m "<commit-message>"
```

- Use a HEREDOC for multi-line commit messages
- If pre-commit hooks fail, report the error to the user and ask for instructions
- Do NOT use `--no-verify` to bypass hooks unless the user explicitly requests it

---

## Phase 3: Push

### 3.1 Pre-push Remote Check

Before pushing, verify the remote state:

```bash
git fetch origin <current-branch>
```

- If the local branch is **behind** the remote, warn the user
- Suggest `git pull --rebase` or `git merge` as appropriate
- Do NOT force push unless the user explicitly requests it

### 3.2 Execute Push

```bash
git push -u origin <branch-name>
```

### 3.3 Push Error Handling

**CRITICAL: If push fails for ANY reason:**
- Do NOT attempt to resolve the error automatically
- Do NOT retry with different flags (e.g., `--force`)
- STOP immediately and report the exact error to the user
- Ask the user for instructions on how to proceed

---

## Phase 4: Pull Request Creation

### 4.1 Determine Base Branch

Check for available base branches in this priority order:

1. **`develop`** — First priority. Use if the branch exists on remote.
2. **`main`** — Second priority.
3. **`master`** — Third priority.

```bash
git branch -r | grep -E 'origin/(develop|main|master)$'
```

Use the first match in priority order.

### 4.2 Extract Ticket Number from Branch Name

If the current branch follows the pattern `<prefix>/<TICKET_ID>-<description>`:

- Pattern: `feature/XXX-123-some-description` or `fix/PROJ-456-bug-title`
- Extract the ticket ID (alphabetic prefix + numeric suffix, e.g., `XXX-123`, `PROJ-456`)
- Also match patterns like `feature/XXX000-description` (no hyphen between letters and numbers)
- Prefix the PR title with `[TICKET_ID]`

**Regex pattern for extraction:**
```
^[^/]+/([A-Z]+-?\d+)
```

**Examples:**
| Branch Name | Extracted Ticket | PR Title Prefix |
|---|---|---|
| `feature/PROJ-123-add-login` | `PROJ-123` | `[PROJ-123]` |
| `feature/XXX000-hoge` | `XXX000` | `[XXX000]` |
| `fix/BUG-42-null-pointer` | `BUG-42` | `[BUG-42]` |
| `feature/add-new-page` | (none) | (no prefix) |

### 4.3 Check for PR Template

Look for PR templates in the following locations (in order):

1. `.github/pull_request_template.md`
2. `.github/PULL_REQUEST_TEMPLATE.md`
3. `.github/PULL_REQUEST_TEMPLATE/default.md`
4. `docs/pull_request_template.md`
5. `pull_request_template.md`

If a template is found, fill in its sections based on the changes made. If no template is found, use the default format below.

### 4.4 Check for Conflicts with Base Branch

Before creating the PR, check if there are merge conflicts with the base branch:

```bash
git fetch origin <base-branch>
git merge-tree $(git merge-base HEAD origin/<base-branch>) HEAD origin/<base-branch>
```

Or alternatively:

```bash
git diff origin/<base-branch>...HEAD --stat
```

If conflicts are detected:
- Warn the user about the conflicting files
- Ask if they want to proceed with PR creation anyway (conflicts can be resolved later)

### 4.5 Create Pull Request

Use `gh pr create` with the appropriate options:

```bash
gh pr create \
  --base <base-branch> \
  --title "<[TICKET_ID] if applicable> <PR title>" \
  --body "$(cat <<'EOF'
<PR body content following template or default format>
EOF
)"
```

### 4.6 Default PR Body Format

If no PR template exists, use:

```markdown
## Summary
<!-- Brief description of what this PR does -->

## Changes
<!-- List of specific changes -->
- Change 1
- Change 2

## Ticket
<!-- Link to ticket if applicable -->

## Test Plan
<!-- How to test these changes -->
- [ ] Test step 1
- [ ] Test step 2

## Notes
<!-- Any additional context or notes for reviewers -->
```

### 4.7 Draft PR Option

If the user indicates work is still in progress (WIP), or if the branch name contains `wip` or `draft`:

```bash
gh pr create --draft ...
```

Ask the user whether they want a regular PR or a draft PR.

---

## Complete Workflow Checklist

```
PRE-COMMIT:
  [ ] Identify changed files (only relevant changes)
  [ ] Check for sensitive files
  [ ] Check for large files (>5MB)
  [ ] Show diff summary and get user confirmation

COMMIT:
  [ ] Determine commit message convention
  [ ] Stage specific files
  [ ] Create commit with appropriate message

PUSH:
  [ ] Fetch remote state
  [ ] Check if local is behind remote
  [ ] Push to remote
  [ ] If error → STOP and ask user

PULL REQUEST:
  [ ] Determine base branch (develop > main > master)
  [ ] Extract ticket number from branch name
  [ ] Check for PR template
  [ ] Check for conflicts with base branch
  [ ] Create PR (or draft PR)
  [ ] Report PR URL to user
```

---

## Error Handling Summary

| Situation | Action |
|---|---|
| Sensitive file in changes | STOP, warn user |
| Large file in changes | Warn, ask confirmation |
| Pre-commit hook fails | Report error, ask user |
| Push fails | STOP immediately, report error, ask user |
| Merge conflicts with base | Warn user, ask if proceed |
| No remote base branch found | Ask user which branch to target |
| `gh` CLI not available | Report error, provide manual PR URL |

---

## Notes

- This skill should be combined with the **verification-loop** skill for pre-PR quality checks
- Always show the user what will be committed before committing
- Transparency and user confirmation at each critical step prevents mistakes
- When in doubt, ask the user rather than making assumptions
