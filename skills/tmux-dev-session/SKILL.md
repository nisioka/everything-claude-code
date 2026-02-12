---
name: tmux-dev-session
description: Use this skill when running tests, starting dev servers, or executing commands in background panes. Enables Claude to operate tmux panes for non-blocking parallel workflows.
---

# Tmux Dev Session Pane Control

This skill enables Claude to send commands to and read output from tmux panes
set up by `scripts/tmux-session.sh`.

## Pane Layout

```
┌──────────────────┬───────────────┐
│                  │    server     │
│    claude        │              │
│   (you are here) ├───────────────┤
│                  │   test-1     │
│                  ├───────────────┤
│                  │   test-2     │
└──────────────────┴───────────────┘
```

## Detecting the Session

Before using panes, verify the tmux session is available:

```bash
# List all panes with titles
tmux list-panes -F "#{pane_index} #{pane_title}" 2>/dev/null
```

If this returns nothing, the tmux session has not been initialized.
Guide the user through setup using the instructions below.

## Setup (when session is not detected)

The setup script is bundled with this skill. When the session is not found:

1. Resolve the script path: this skill's base directory is in the system prompt
   as "Base directory for this skill: ...". The script is at `../../scripts/tmux-session.sh`
   relative to that directory.
2. Check if `tmux-dev-session` is already available on the user's PATH.
3. If not, guide the user to copy the script to a PATH-accessible location (one-time setup):

```
tmux-dev-session コマンドが見つかりません。初回セットアップとして以下を実行してください：

  cp <resolved-path>/scripts/tmux-session.sh ~/.local/bin/tmux-dev-session
  chmod +x ~/.local/bin/tmux-dev-session

セットアップ後、新しいターミナルで以下を実行してください：

  tmux-dev-session

セッション起動後、左のclaudeペインで `claude` を起動してください。
```

4. If `tmux-dev-session` is already on PATH but session is not running, simply instruct:

```
新しいターミナルで以下を実行してください：

  tmux-dev-session

セッション起動後、左のclaudeペインで `claude` を起動してください。
```

Do NOT attempt to run the script yourself, as it requires `tmux attach` which
conflicts with the current Claude Code session.

## Sending Commands to Panes

Use `pane_title` to target panes by name:

```bash
# Start dev server
tmux send-keys -t server "npm run dev" Enter

# Run a specific test suite
tmux send-keys -t test-1 "npm test -- auth" Enter

# Run a different test in parallel
tmux send-keys -t test-2 "npm test -- user" Enter
```

## Reading Pane Output

```bash
# Capture last 50 lines of a pane
tmux capture-pane -t test-1 -p -S -50

# Capture the entire scrollback buffer
tmux capture-pane -t test-1 -p -S -
```

## Typical Workflow

### Run Tests After Code Changes

1. Send test command with a completion marker to a test pane
2. Poll for the marker to detect completion
3. Capture output to check results

```bash
# Step 1: send command with completion marker
tmux send-keys -t test-1 'npm test -- --testPathPattern=auth; echo "--TEST-COMPLETE--"' Enter

# Step 2: wait for completion marker
while ! tmux capture-pane -p -t test-1 | grep -q -- --TEST-COMPLETE--; do
  sleep 1
done

# Step 3: read result
tmux capture-pane -t test-1 -p -S -30
```

### Restart Dev Server

```bash
# Send Ctrl+C to stop, then restart
tmux send-keys -t server C-c
sleep 1
tmux send-keys -t server "npm run dev" Enter
```

### Check if a Process is Running

```bash
# Check what command is running in a pane
tmux list-panes -F "#{pane_title}: #{pane_current_command}"
```

## Rules

- **Never send commands to the `claude` pane** - that is your own session
- **Always capture output after sending commands** - confirm success/failure
- **Use completion markers instead of `sleep`** - append `; echo "--MARKER--"` to commands and poll with `grep` for reliable completion detection
- **Prefer `test-1` for primary tests, `test-2` for secondary** - keep organized
- **Send `C-c` before new commands** if a previous process may still be running
