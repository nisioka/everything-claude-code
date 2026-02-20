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
5. Post-PR Bot Review Response
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

## Phase 5: Post-PR Bot Review Response

PR作成後、自動レビューボット（Gemini Code Assist 等）のフィードバックに対応する。

### 5.1 レビュー待機

ボットレビューの完了を待つため **5分間待機** する:

```bash
echo "⏳ ボットレビュー完了を待機中（5分）..."
sleep 300
```

### 5.2 レビューコメント取得・解析

`pr-review-responder` エージェントを使用してPRのレビューコメントを取得・解析する。

**初回呼び出し**（`since` なし = 全件取得）:

```markdown
Task tool を使用:
- prompt: "PR #<PR_NUMBER> のレビューコメントを取得・解析してください"
- subagent_type: ecc:pr-review-responder
- description: "Fetch PR review comments"
```

**2回目以降の呼び出し**（`since` 指定 = 差分取得）:

```markdown
Task tool を使用:
- prompt: "PR #<PR_NUMBER> のレビューコメントを取得・解析してください。since=<LAST_FETCH_TIMESTAMP> 以降の新規コメントのみ対象としてください"
- subagent_type: ecc:pr-review-responder
- description: "Fetch new PR review comments since <LAST_FETCH_TIMESTAMP>"
```

**タイムスタンプ管理**:
- エージェントの出力に含まれる `Fetch Timestamp`（ISO 8601）を変数 `LAST_FETCH_TIMESTAMP` として保持する
- 次回ループ（5.7）の再呼び出し時に `since` パラメータとして渡す
- これにより、前回取得済みのコメントを重複処理することを防ぐ

エージェントが返す構造化データ:
- 各コメントの severity（CRITICAL / HIGH / MEDIUM / LOW）
- カテゴリ（security, performance, code-quality, bug, style, testing）
- 対象ファイル・行番号
- 元のコメント本文
- **Fetch Timestamp**（次回ループ用）

### 5.3 ユーザー確認

検出された指摘をユーザーに提示し、対応方針を確認する:

- 各指摘の severity、カテゴリ、概要を一覧表示
- ユーザーに「全て対応」「選択して対応」「スキップ」を選択させる
- ユーザーが選択した指摘のみ修正対象とする

### 5.4 サブエージェントに委任して修正

`skills/agent-router/SKILL.md` の **Review-Category Routing Table** に従って、各指摘を適切なサブエージェントに委任する。

サブエージェントへの指示内容は agent-router スキルの **Standard Invocation Pattern** に従い、以下を含める:
- 元のレビューコメント本文（コンテキスト理解のため）
- 対象ファイル・行番号
- 修正方針

### 5.5 修正のコミット＆プッシュ

全指摘の修正後:

```bash
git add <modified-files>
git commit -m "$(cat <<'EOF'
fix: PRレビュー指摘対応 (Round N)

- [修正内容の要約]

Co-Authored-By: Claude Agent <noreply@anthropic.com>
EOF
)"

git push -u origin <branch-name>
```

**エラーハンドリング**: プッシュ失敗時は Phase 3.3 と同じルールに従う（即時停止してユーザーに報告）。

### 5.6 再レビュー依頼

プッシュ完了後、レビューボットに再レビューを依頼する。使用するコマンドはプロジェクトに導入されているレビューボットに応じて選択する:

| Review Bot | Command |
|---|---|
| Gemini Code Assist | `gh pr comment <PR_NUMBER> --body "/gemini review"` |
| CodeRabbit | `gh pr comment <PR_NUMBER> --body "@coderabbitai review"` |

プロジェクトの PR 履歴やボット設定を確認し、適切なコマンドを使用すること。複数のボットが導入されている場合は、それぞれに再レビューを依頼する。

### 5.7 再レビュー確認ループ

プッシュ後、再度ボットレビューが走る可能性があるため:

1. **再度5分待機**
2. **`LAST_FETCH_TIMESTAMP` を `since` として渡し、新しいコメントのみ取得**（5.2 の2回目以降の手順に従う）
3. **新たな指摘があれば** → 5.3〜5.6 を繰り返す（`LAST_FETCH_TIMESTAMP` も更新される）
4. **新たな指摘がなければ** → 完了

**ループ上限: 2回**（初回 + 再レビュー1回の計2ラウンド）

上限到達時:
- 残存する未対応コメントを最終レポートに記載
- ユーザーに手動対応を促す

### 5.8 対応不要な場合

`pr-review-responder` が「対応可能な指摘なし」と判断した場合:
- Phase 5 をスキップし、そのまま完了とする

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

BOT REVIEW RESPONSE:
  [ ] Wait 5 minutes for bot review
  [ ] Fetch and analyze review comments (pr-review-responder)
  [ ] Present findings to user for confirmation
  [ ] Delegate fixes to appropriate sub-agents
  [ ] Commit and push fixes
  [ ] Request re-review (/gemini review)
  [ ] Re-check loop (max 2 rounds)
  [ ] Report final status to user
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
| Bot review fetch fails | Warn user, skip Phase 5 |
| Bot review loop limit reached (2 rounds) | Report remaining issues, ask user for manual review |
| Sub-agent fix fails | Report error, mark as unresolved, continue with next item |
| Push fails during bot review fix (Phase 5.5) | Follow Phase 3.3 rules: STOP and ask user |
| Re-review request fails (`gh pr comment`) | Warn user, continue to next loop iteration |

---

## Notes

- This skill should be combined with the **verification-loop** skill for pre-PR quality checks
- Always show the user what will be committed before committing
- Transparency and user confirmation at each critical step prevents mistakes
- When in doubt, ask the user rather than making assumptions
