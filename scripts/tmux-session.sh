#!/bin/bash
# tmux-session.sh - Initialize tmux development layout for Claude Code
#
# Layout:
#   ┌──────────────────┬───────────────┐
#   │                  │    server     │
#   │                  │              │
#   │    claude        │              │
#   │                  ├───────────────┤
#   │                  │   test-1     │
#   │                  ├───────────────┤
#   │                  │   test-2     │
#   └──────────────────┴───────────────┘
#     50%                50%
#
# Usage:
#   ./scripts/tmux-session.sh              # auto-detect branch
#   ./scripts/tmux-session.sh feature/auth  # specify branch name
#   ./scripts/tmux-session.sh --kill        # kill current branch session
#   ./scripts/tmux-session.sh --list        # list active sessions
#
# Claude Code can interact with panes via:
#   tmux send-keys -t <session>:0.server "npm run dev" Enter
#   tmux send-keys -t <session>:0.test-1 "npm test -- auth" Enter
#   tmux capture-pane -t <session>:0.test-1 -p -S -50

set -euo pipefail

# --- Configuration ---
TEST_PANE_HEIGHT=5  # lines per test pane
RIGHT_PANE_PERCENT=50

# --- Helper functions ---
usage() {
  sed -n '2,/^$/s/^# //p' "$0"
  exit 0
}

get_branch() {
  git branch --show-current 2>/dev/null || echo "main"
}

sanitize_session_name() {
  echo "$1" | tr '/.' '--'
}

# --- Command handling ---
case "${1:-}" in
  -h|--help)
    usage
    ;;
  --kill)
    SESSION=$(sanitize_session_name "$(get_branch)")
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      tmux kill-session -t "$SESSION"
      echo "Killed session: $SESSION"
    else
      echo "No session found: $SESSION"
    fi
    exit 0
    ;;
  --list)
    tmux list-sessions 2>/dev/null || echo "No active tmux sessions"
    exit 0
    ;;
esac

# --- Determine session name ---
BRANCH="${1:-$(get_branch)}"
SESSION=$(sanitize_session_name "$BRANCH")
PROJECT_DIR="$(pwd)"

# --- Attach if session exists ---
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists. Attaching..."
  exec tmux attach-session -t "$SESSION"
fi

# --- Create layout ---
# Pane 0: claude (left 50%)
tmux new-session -d -s "$SESSION" -c "$PROJECT_DIR"
tmux select-pane -T "claude"

# Pane 1: server (right top)
tmux split-window -h -t "$SESSION:0.0" -l "${RIGHT_PANE_PERCENT}%" -c "$PROJECT_DIR"
tmux select-pane -T "server"

# Pane 2: test-1 (right middle) - split bottom off server pane
tmux split-window -v -t "$SESSION:0.1" -l $((TEST_PANE_HEIGHT * 2)) -c "$PROJECT_DIR"
tmux select-pane -T "test-1"

# Pane 3: test-2 (right bottom) - split bottom off test-1
tmux split-window -v -t "$SESSION:0.2" -l "$TEST_PANE_HEIGHT" -c "$PROJECT_DIR"
tmux select-pane -T "test-2"

# --- Pane border styling ---
tmux set-option -t "$SESSION" pane-border-status top
tmux set-option -t "$SESSION" pane-border-format \
  " #[fg=blue,bold]#{pane_title}#[default] | #{pane_current_command} "

# --- Focus on claude pane ---
tmux select-pane -t "$SESSION:0.0"

echo "Session '$SESSION' created for branch '$BRANCH'"
echo ""
echo "  claude  : left    (main Claude Code pane)"
echo "  server  : right-top (dev server)"
echo "  test-1  : right-mid (test runner 1)"
echo "  test-2  : right-bot (test runner 2)"
echo ""

# --- Attach ---
exec tmux attach-session -t "$SESSION"
