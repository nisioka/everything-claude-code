#!/bin/bash
# claude-scheduler.sh - Task queue & scheduled execution for Claude Code
#
# タスクをキューに積み、指定時刻に1つずつ実行するスケジューラ。
# cron (毎分) と組み合わせて使う。
#
# Setup:
#   # cron登録（毎分チェック）
#   crontab -e
#   * * * * * /path/to/claude-scheduler.sh tick >> ~/.claude-scheduler/cron.log 2>&1
#
# Usage:
#   claude-scheduler.sh add <prompt> [options]   # タスク追加
#   claude-scheduler.sh list                      # キュー一覧
#   claude-scheduler.sh schedule <id> <time>      # 実行時刻を設定
#   claude-scheduler.sh run-next                  # 次のタスクを即時実行
#   claude-scheduler.sh run <id>                  # 指定タスクを即時実行
#   claude-scheduler.sh remove <id>               # タスク削除
#   claude-scheduler.sh tick                      # スケジューラtick（cron用）
#   claude-scheduler.sh log [id]                  # 実行ログ表示
#   claude-scheduler.sh setup-cron                # cron自動登録
#
# Options for 'add':
#   --at "HH:MM"              今日のHH:MMに予約（過ぎていれば翌日）
#   --at "YYYY-MM-DD HH:MM"   指定日時に予約
#   --project /path/to/dir    実行ディレクトリ（デフォルト: カレント）
#   --tools "Read,Edit,..."   許可ツール
#   --max-turns N             最大ターン数
#   --model <model>           使用モデル
#   --system-prompt <file>    追加システムプロンプトファイル
#
# Examples:
#   # 深夜2時にspec-impl相当のタスクを予約
#   claude-scheduler.sh add "auth-featureの未完了タスクをTDDで実装して" \
#     --at "02:00" --project ~/myapp --max-turns 50
#
#   # 日中13時にコードレビューを予約
#   claude-scheduler.sh add "src/ 以下のコードをレビューして" --at "13:00"
#
#   # 明日の朝9時に予約
#   claude-scheduler.sh add "テストカバレッジを改善して" --at "2026-03-01 09:00"

set -euo pipefail

# ===========================================================================
# Configuration
# ===========================================================================
SCHEDULER_DIR="${CLAUDE_SCHEDULER_DIR:-$HOME/.claude-scheduler}"
QUEUE_FILE="$SCHEDULER_DIR/queue.json"
LOCK_FILE="$SCHEDULER_DIR/scheduler.lock"
LOG_DIR="$SCHEDULER_DIR/logs"
PID_FILE="$SCHEDULER_DIR/running.pid"

# Claude Code defaults
DEFAULT_TOOLS="Read,Edit,Write,Bash,Glob,Grep,Task"
DEFAULT_MAX_TURNS=100

# ===========================================================================
# Helpers
# ===========================================================================
ensure_dirs() {
  mkdir -p "$SCHEDULER_DIR" "$LOG_DIR"
  if [[ ! -f "$QUEUE_FILE" ]]; then
    echo '[]' > "$QUEUE_FILE"
  fi
}

require_jq() {
  if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq / apt install jq" >&2
    exit 1
  fi
}

require_claude() {
  if ! command -v claude &>/dev/null; then
    echo "Error: claude CLI not found in PATH" >&2
    exit 1
  fi
}

now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%S%z" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%S%z"
}

now_epoch() {
  date +%s
}

to_epoch() {
  local timestr="$1"
  # Handle both GNU date and BSD date
  if date --version &>/dev/null 2>&1; then
    # GNU date
    date -d "$timestr" +%s 2>/dev/null || return 1
  else
    # BSD date (macOS)
    date -j -f "%Y-%m-%dT%H:%M:%S" "$timestr" +%s 2>/dev/null || \
    date -j -f "%Y-%m-%d %H:%M" "$timestr" +%s 2>/dev/null || return 1
  fi
}

generate_id() {
  date +"%Y%m%d-%H%M%S"-$(printf '%04x' $RANDOM)
}

# Parse "HH:MM" or "YYYY-MM-DD HH:MM" into ISO datetime
parse_schedule_time() {
  local input="$1"

  if [[ "$input" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]][0-9]{2}:[0-9]{2}$ ]]; then
    # Full datetime: "YYYY-MM-DD HH:MM"
    echo "${input}:00"
  elif [[ "$input" =~ ^[0-9]{2}:[0-9]{2}$ ]]; then
    # Time only: "HH:MM" -> use today, or tomorrow if past
    local today
    today=$(date +"%Y-%m-%d")
    local target_dt="${today} ${input}:00"
    local target_epoch
    target_epoch=$(to_epoch "$target_dt" 2>/dev/null || echo 0)
    local now
    now=$(now_epoch)

    if [[ "$target_epoch" -le "$now" ]]; then
      # Already passed today -> schedule for tomorrow
      if date --version &>/dev/null 2>&1; then
        today=$(date -d "+1 day" +"%Y-%m-%d")
      else
        today=$(date -v+1d +"%Y-%m-%d")
      fi
    fi
    echo "${today}T${input}:00"
  else
    echo "Error: Invalid time format '$input'. Use 'HH:MM' or 'YYYY-MM-DD HH:MM'" >&2
    return 1
  fi
}

# Pretty-print queue as table
print_table() {
  local json="$1"
  local count
  count=$(echo "$json" | jq 'length')

  if [[ "$count" -eq 0 ]]; then
    echo "  (empty)"
    return
  fi

  printf "  %-18s %-10s %-19s %-40s\n" "ID" "STATUS" "SCHEDULED" "PROMPT"
  printf "  %-18s %-10s %-19s %-40s\n" "──────────────────" "──────────" "───────────────────" "────────────────────────────────────────"

  echo "$json" | jq -r '.[] | [.id, .status, (.scheduled_at // "-"), .prompt] | @tsv' | \
  while IFS=$'\t' read -r id status scheduled prompt; do
    # Truncate prompt for display
    if [[ ${#prompt} -gt 40 ]]; then
      prompt="${prompt:0:37}..."
    fi
    # Format scheduled time for display
    if [[ "$scheduled" != "-" ]]; then
      scheduled=$(echo "$scheduled" | sed 's/T/ /;s/:00$//')
    fi
    # Color by status
    case "$status" in
      pending)   status_display="\033[33m${status}\033[0m" ;;
      scheduled) status_display="\033[36m${status}\033[0m" ;;
      running)   status_display="\033[1;32m${status}\033[0m" ;;
      completed) status_display="\033[32m${status}\033[0m" ;;
      failed)    status_display="\033[31m${status}\033[0m" ;;
      *)         status_display="$status" ;;
    esac
    printf "  %-18s ${status_display}%-$((10 - ${#status}))s %-19s %-40s\n" "$id" "" "$scheduled" "$prompt"
  done
}

# ===========================================================================
# Lock management (prevent concurrent execution)
# ===========================================================================
acquire_lock() {
  if [[ -f "$LOCK_FILE" ]]; then
    local lock_pid
    lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
      return 1  # Another instance is running
    fi
    # Stale lock file
    rm -f "$LOCK_FILE"
  fi
  echo $$ > "$LOCK_FILE"
  return 0
}

release_lock() {
  rm -f "$LOCK_FILE"
}

# ===========================================================================
# Commands
# ===========================================================================

cmd_add() {
  local prompt=""
  local project
  project=$(pwd)
  local tools="$DEFAULT_TOOLS"
  local max_turns="$DEFAULT_MAX_TURNS"
  local schedule_at=""
  local model=""
  local system_prompt=""

  # Parse arguments
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --at)
        schedule_at="$2"; shift 2 ;;
      --project)
        project="$2"; shift 2 ;;
      --tools)
        tools="$2"; shift 2 ;;
      --max-turns)
        max_turns="$2"; shift 2 ;;
      --model)
        model="$2"; shift 2 ;;
      --system-prompt)
        system_prompt="$2"; shift 2 ;;
      -*)
        echo "Unknown option: $1" >&2; exit 1 ;;
      *)
        if [[ -z "$prompt" ]]; then
          prompt="$1"
        else
          prompt="$prompt $1"
        fi
        shift ;;
    esac
  done

  if [[ -z "$prompt" ]]; then
    echo "Error: prompt is required" >&2
    echo "Usage: $0 add <prompt> [--at HH:MM] [--project /path] [--tools Tools]" >&2
    exit 1
  fi

  local id
  id=$(generate_id)

  local scheduled_at_val="null"
  local status="pending"
  if [[ -n "$schedule_at" ]]; then
    local parsed
    parsed=$(parse_schedule_time "$schedule_at") || exit 1
    scheduled_at_val="\"$parsed\""
    status="scheduled"
  fi

  local model_val="null"
  if [[ -n "$model" ]]; then
    model_val="\"$model\""
  fi

  local system_prompt_val="null"
  if [[ -n "$system_prompt" ]]; then
    system_prompt_val="\"$system_prompt\""
  fi

  # Add to queue
  local new_task
  new_task=$(jq -n \
    --arg id "$id" \
    --arg prompt "$prompt" \
    --arg project "$project" \
    --arg tools "$tools" \
    --argjson max_turns "$max_turns" \
    --argjson scheduled_at "$scheduled_at_val" \
    --argjson model "$model_val" \
    --argjson system_prompt "$system_prompt_val" \
    --arg status "$status" \
    --arg created_at "$(now_iso)" \
    '{
      id: $id,
      prompt: $prompt,
      project: $project,
      tools: $tools,
      max_turns: $max_turns,
      scheduled_at: $scheduled_at,
      model: $model,
      system_prompt: $system_prompt,
      status: $status,
      created_at: $created_at,
      started_at: null,
      completed_at: null,
      exit_code: null,
      log_file: null
    }')

  local updated
  updated=$(jq --argjson task "$new_task" '. += [$task]' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  echo "Task added: $id"
  if [[ "$status" == "scheduled" ]]; then
    echo "  Scheduled: $(echo "$scheduled_at_val" | tr -d '"' | sed 's/T/ /;s/:00$//')"
  else
    echo "  Status: pending (use 'schedule $id <time>' to set execution time)"
  fi
  echo "  Prompt: $prompt"
  echo "  Project: $project"
}

cmd_list() {
  local filter="${1:-all}"

  echo "Claude Scheduler Queue"
  echo "======================"

  case "$filter" in
    all)
      print_table "$(cat "$QUEUE_FILE")" ;;
    pending|scheduled|running|completed|failed)
      print_table "$(jq --arg s "$filter" '[.[] | select(.status == $s)]' "$QUEUE_FILE")" ;;
    *)
      echo "Unknown filter: $filter (all|pending|scheduled|running|completed|failed)" >&2
      exit 1 ;;
  esac

  echo ""
  # Summary counts
  local total pending scheduled running completed failed
  total=$(jq 'length' "$QUEUE_FILE")
  pending=$(jq '[.[] | select(.status == "pending")] | length' "$QUEUE_FILE")
  scheduled=$(jq '[.[] | select(.status == "scheduled")] | length' "$QUEUE_FILE")
  running=$(jq '[.[] | select(.status == "running")] | length' "$QUEUE_FILE")
  completed=$(jq '[.[] | select(.status == "completed")] | length' "$QUEUE_FILE")
  failed=$(jq '[.[] | select(.status == "failed")] | length' "$QUEUE_FILE")
  echo "  Total: $total | Pending: $pending | Scheduled: $scheduled | Running: $running | Completed: $completed | Failed: $failed"
}

cmd_schedule() {
  local id="$1"
  local time_str="$2"

  if [[ -z "$id" ]] || [[ -z "$time_str" ]]; then
    echo "Usage: $0 schedule <id> <time>" >&2
    exit 1
  fi

  # Check task exists
  local exists
  exists=$(jq --arg id "$id" '[.[] | select(.id == $id)] | length' "$QUEUE_FILE")
  if [[ "$exists" -eq 0 ]]; then
    echo "Error: Task '$id' not found" >&2
    exit 1
  fi

  local parsed
  parsed=$(parse_schedule_time "$time_str") || exit 1

  local updated
  updated=$(jq --arg id "$id" --arg at "$parsed" '
    map(if .id == $id then .scheduled_at = $at | .status = "scheduled" else . end)
  ' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  echo "Task '$id' scheduled for: $(echo "$parsed" | sed 's/T/ /;s/:00$//')"
}

cmd_remove() {
  local id="$1"

  if [[ -z "$id" ]]; then
    echo "Usage: $0 remove <id>" >&2
    exit 1
  fi

  local exists
  exists=$(jq --arg id "$id" '[.[] | select(.id == $id)] | length' "$QUEUE_FILE")
  if [[ "$exists" -eq 0 ]]; then
    echo "Error: Task '$id' not found" >&2
    exit 1
  fi

  local updated
  updated=$(jq --arg id "$id" 'map(select(.id != $id))' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  echo "Task '$id' removed"
}

cmd_run() {
  local id="$1"
  require_claude

  if [[ -z "$id" ]]; then
    echo "Usage: $0 run <id>" >&2
    exit 1
  fi

  local task
  task=$(jq --arg id "$id" '.[] | select(.id == $id)' "$QUEUE_FILE")
  if [[ -z "$task" ]]; then
    echo "Error: Task '$id' not found" >&2
    exit 1
  fi

  execute_task "$task"
}

cmd_run_next() {
  require_claude

  # Find next task: scheduled tasks whose time has come, or pending tasks (FIFO)
  local now_e
  now_e=$(now_epoch)

  # First: scheduled tasks that are due
  local task
  task=$(jq --arg now "$(date +%Y-%m-%dT%H:%M:%S)" '
    [.[] | select(.status == "scheduled" and .scheduled_at != null and .scheduled_at <= $now)]
    | sort_by(.scheduled_at)
    | first // empty
  ' "$QUEUE_FILE")

  # Fallback: oldest pending task
  if [[ -z "$task" ]]; then
    task=$(jq '
      [.[] | select(.status == "pending")]
      | sort_by(.created_at)
      | first // empty
    ' "$QUEUE_FILE")
  fi

  if [[ -z "$task" || "$task" == "null" ]]; then
    echo "No tasks ready to run"
    return 0
  fi

  execute_task "$task"
}

execute_task() {
  local task="$1"
  local id prompt project tools max_turns model system_prompt log_file

  id=$(echo "$task" | jq -r '.id')
  prompt=$(echo "$task" | jq -r '.prompt')
  project=$(echo "$task" | jq -r '.project')
  tools=$(echo "$task" | jq -r '.tools')
  max_turns=$(echo "$task" | jq -r '.max_turns')
  model=$(echo "$task" | jq -r '.model // empty')
  system_prompt=$(echo "$task" | jq -r '.system_prompt // empty')
  log_file="$LOG_DIR/${id}.log"

  echo "Executing task: $id"
  echo "  Prompt: $prompt"
  echo "  Project: $project"
  echo "  Log: $log_file"

  # Update status to running
  local updated
  updated=$(jq --arg id "$id" --arg started "$(now_iso)" --arg log "$log_file" '
    map(if .id == $id then .status = "running" | .started_at = $started | .log_file = $log else . end)
  ' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  # Build claude command
  local cmd=(claude -p "$prompt" --output-format json)
  cmd+=(--max-turns "$max_turns")

  # Add --allowedTools with individual flags
  IFS=',' read -ra tool_array <<< "$tools"
  for tool in "${tool_array[@]}"; do
    cmd+=(--allowedTools "$tool")
  done

  if [[ -n "$model" ]]; then
    cmd+=(--model "$model")
  fi

  if [[ -n "$system_prompt" && -f "$system_prompt" ]]; then
    cmd+=(--append-system-prompt "$(cat "$system_prompt")")
  fi

  # Execute
  local exit_code=0
  (
    cd "$project"
    echo "=== Task: $id ===" > "$log_file"
    echo "=== Started: $(now_iso) ===" >> "$log_file"
    echo "=== Prompt: $prompt ===" >> "$log_file"
    echo "=== Command: ${cmd[*]} ===" >> "$log_file"
    echo "" >> "$log_file"

    "${cmd[@]}" >> "$log_file" 2>&1
  ) || exit_code=$?

  echo "=== Completed: $(now_iso) (exit: $exit_code) ===" >> "$log_file"

  # Update status
  local final_status="completed"
  if [[ "$exit_code" -ne 0 ]]; then
    final_status="failed"
  fi

  updated=$(jq --arg id "$id" --arg status "$final_status" --arg completed "$(now_iso)" --argjson code "$exit_code" '
    map(if .id == $id then .status = $status | .completed_at = $completed | .exit_code = $code else . end)
  ' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  echo "Task $id: $final_status (exit code: $exit_code)"
}

cmd_tick() {
  # Called by cron every minute. Check if any scheduled task is due.
  # Only run one task at a time (lock-based).

  if ! acquire_lock; then
    # Another task is already running
    exit 0
  fi

  trap release_lock EXIT

  # Check for any running tasks that might be stale (PID no longer exists)
  local running_count
  running_count=$(jq '[.[] | select(.status == "running")] | length' "$QUEUE_FILE")
  if [[ "$running_count" -gt 0 ]]; then
    # Don't start a new task while one is running
    exit 0
  fi

  # Find scheduled tasks that are due
  local now_dt
  now_dt=$(date +"%Y-%m-%dT%H:%M:%S")

  local task
  task=$(jq --arg now "$now_dt" '
    [.[] | select(.status == "scheduled" and .scheduled_at != null and .scheduled_at <= $now)]
    | sort_by(.scheduled_at)
    | first // empty
  ' "$QUEUE_FILE")

  if [[ -z "$task" || "$task" == "null" ]]; then
    exit 0
  fi

  local id
  id=$(echo "$task" | jq -r '.id')
  echo "[$(date)] Tick: executing due task $id"

  execute_task "$task"
}

cmd_log() {
  local id="${1:-}"

  if [[ -z "$id" ]]; then
    # Show recent logs
    echo "Recent task logs:"
    echo ""
    ls -lt "$LOG_DIR"/*.log 2>/dev/null | head -10 || echo "  No logs yet"
    return
  fi

  local log_file="$LOG_DIR/${id}.log"
  if [[ ! -f "$log_file" ]]; then
    echo "No log file for task '$id'" >&2
    exit 1
  fi

  cat "$log_file"
}

cmd_setup_cron() {
  local script_path
  script_path=$(realpath "$0")

  local cron_entry="* * * * * $script_path tick >> $SCHEDULER_DIR/cron.log 2>&1"

  # Check if already registered
  if crontab -l 2>/dev/null | grep -qF "claude-scheduler.sh tick"; then
    echo "Cron entry already exists:"
    crontab -l | grep "claude-scheduler"
    return
  fi

  # Add to crontab
  (crontab -l 2>/dev/null; echo "$cron_entry") | crontab -

  echo "Cron entry added:"
  echo "  $cron_entry"
  echo ""
  echo "Scheduler will check every minute for due tasks."
  echo "Queue file: $QUEUE_FILE"
  echo "Logs: $LOG_DIR/"
}

cmd_clean() {
  local days="${1:-7}"

  local updated
  updated=$(jq --arg cutoff "$(date -d "-${days} days" +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -v-${days}d +%Y-%m-%dT%H:%M:%S)" '
    map(select(.status != "completed" and .status != "failed" or .completed_at > $cutoff or .completed_at == null))
  ' "$QUEUE_FILE")
  echo "$updated" > "$QUEUE_FILE"

  echo "Cleaned tasks completed more than $days days ago"
}

cmd_help() {
  sed -n '2,/^$/{ /^#/s/^# //p; /^$/q; }' "$0"
  echo ""
  echo "Commands:"
  echo "  add <prompt> [options]   Add a task to the queue"
  echo "  list [filter]            Show queue (all|pending|scheduled|running|completed|failed)"
  echo "  schedule <id> <time>     Set execution time (HH:MM or YYYY-MM-DD HH:MM)"
  echo "  run <id>                 Execute a specific task immediately"
  echo "  run-next                 Execute the next ready task"
  echo "  remove <id>              Remove a task from the queue"
  echo "  tick                     Scheduler tick (called by cron)"
  echo "  log [id]                 Show execution logs"
  echo "  setup-cron               Register cron entry"
  echo "  clean [days]             Remove completed tasks older than N days (default: 7)"
  echo "  help                     Show this help"
}

# ===========================================================================
# Main
# ===========================================================================
main() {
  require_jq
  ensure_dirs

  local command="${1:-help}"
  shift || true

  case "$command" in
    add)        cmd_add "$@" ;;
    list|ls)    cmd_list "$@" ;;
    schedule)   cmd_schedule "$@" ;;
    run)        cmd_run "$@" ;;
    run-next)   cmd_run_next "$@" ;;
    remove|rm)  cmd_remove "$@" ;;
    tick)       cmd_tick ;;
    log|logs)   cmd_log "$@" ;;
    setup-cron) cmd_setup_cron ;;
    clean)      cmd_clean "$@" ;;
    help|-h|--help) cmd_help ;;
    *)
      echo "Unknown command: $command" >&2
      cmd_help
      exit 1
      ;;
  esac
}

main "$@"
