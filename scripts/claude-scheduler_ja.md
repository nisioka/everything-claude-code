# Claude Scheduler - タスクキュー & スケジュール実行

## 概要

Claude Code のタスクをキューに積み、指定時刻に自動実行するローカルスケジューラです。
深夜バッチや日中の定期実行など、**非対話的な Claude Code 実行を動的に予約**できます。

```
┌─────────────────────────────────────────────────────────────┐
│                      claude-scheduler                        │
│                                                              │
│  ユーザー                    cron (毎分)                     │
│    │                           │                             │
│    ├─ add "タスクA" --at 02:00 │                             │
│    ├─ add "タスクB" --at 13:00 │                             │
│    ├─ add "タスクC"            │                             │
│    │                           │                             │
│    │   queue.json              │                             │
│    │   ┌────────────────┐      │                             │
│    │   │ A: scheduled   │◀─────┤ tick → 時刻到達？          │
│    │   │ B: scheduled   │      │   → claude -p で実行       │
│    │   │ C: pending     │      │   → 1タスクずつ（排他）    │
│    │   └────────────────┘      │                             │
│                                                              │
│  実行ログ: ~/.claude-scheduler/logs/<id>.log                 │
└─────────────────────────────────────────────────────────────┘
```

## 前提条件

- `claude` CLI がインストール済み & PATH に存在
- `jq` がインストール済み（`brew install jq` / `apt install jq`）
- cron が利用可能（ほとんどの Linux/macOS 環境で標準搭載）

## セットアップ

```bash
# 1. cron 登録（毎分スケジューラがキューをチェック）
./scripts/claude-scheduler.sh setup-cron

# または手動で crontab -e:
# * * * * * /path/to/claude-scheduler.sh tick >> ~/.claude-scheduler/cron.log 2>&1
```

## 使い方

### タスクの追加

```bash
# 基本: タスクを追加（pending 状態、手動実行 or 後からスケジュール）
./scripts/claude-scheduler.sh add "auth-featureの未完了タスクをTDDで実装して"

# 深夜2時に予約実行
./scripts/claude-scheduler.sh add "auth-featureの未完了タスクをTDDで実装して" \
  --at "02:00" \
  --project ~/myapp \
  --max-turns 50

# 日中13時にコードレビュー
./scripts/claude-scheduler.sh add "src/ 以下のコードをレビューして問題をissueに起票" \
  --at "13:00"

# 明日の朝9時に予約
./scripts/claude-scheduler.sh add "テストカバレッジを改善して" \
  --at "2026-03-01 09:00"

# カスタムコマンド相当の処理をシステムプロンプト付きで実行
./scripts/claude-scheduler.sh add "auth-featureを実装して" \
  --system-prompt ./commands/my/spec-impl.md \
  --at "02:00"
```

### `add` のオプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--at "HH:MM"` | 今日の指定時刻に予約（過ぎていれば翌日） | - |
| `--at "YYYY-MM-DD HH:MM"` | 指定日時に予約 | - |
| `--project /path` | 実行ディレクトリ | カレントディレクトリ |
| `--tools "Read,Edit,..."` | 許可ツール | `Read,Edit,Write,Bash,Glob,Grep,Task` |
| `--max-turns N` | 最大ターン数 | 100 |
| `--model <model>` | 使用モデル | claude デフォルト |
| `--system-prompt <file>` | 追加システムプロンプトファイル | - |

### キューの確認

```bash
# 全タスク一覧
./scripts/claude-scheduler.sh list

# ステータスでフィルタ
./scripts/claude-scheduler.sh list scheduled
./scripts/claude-scheduler.sh list completed
```

出力例:
```
Claude Scheduler Queue
======================
  ID                 STATUS     SCHEDULED           PROMPT
  ──────────────────  ──────────  ───────────────────  ────────────────────
  20260227-143012-a1f scheduled  2026-02-28 02:00    auth-featureの未完了タスクをTDDで...
  20260227-143055-b2e scheduled  2026-02-28 13:00    src/ 以下のコードをレビューして...
  20260227-143120-c3d pending    -                   テストカバレッジを改善して

  Total: 3 | Pending: 1 | Scheduled: 2 | Running: 0 | Completed: 0 | Failed: 0
```

### スケジュール変更

```bash
# 既存タスクの実行時刻を変更
./scripts/claude-scheduler.sh schedule 20260227-143120-c3d "15:30"

# 明日に変更
./scripts/claude-scheduler.sh schedule 20260227-143120-c3d "2026-03-01 10:00"
```

### 手動実行

```bash
# 次に実行すべきタスクを即時実行
./scripts/claude-scheduler.sh run-next

# 特定タスクを即時実行
./scripts/claude-scheduler.sh run 20260227-143012-a1f
```

### ログ確認

```bash
# 最近のログ一覧
./scripts/claude-scheduler.sh log

# 特定タスクのログ
./scripts/claude-scheduler.sh log 20260227-143012-a1f
```

### その他

```bash
# タスク削除
./scripts/claude-scheduler.sh remove 20260227-143012-a1f

# 完了タスクをクリーンアップ（7日以上前）
./scripts/claude-scheduler.sh clean

# 3日以上前をクリーンアップ
./scripts/claude-scheduler.sh clean 3
```

## 仕組み

### スケジューリングの流れ

1. `add --at` でタスクがキュー（`~/.claude-scheduler/queue.json`）に `scheduled` 状態で追加される
2. cron が毎分 `tick` を呼び出す
3. `tick` は `scheduled` かつ実行時刻を過ぎたタスクを探す
4. 見つかれば **最も古い1件だけ** を `claude -p` で実行
5. 実行中は **ロックファイル** で排他制御（同時実行を防止）
6. 完了/失敗でステータスが更新され、ログが `~/.claude-scheduler/logs/` に保存される

### ファイル構成

```
~/.claude-scheduler/
├── queue.json       # タスクキュー
├── scheduler.lock   # 排他ロック
├── cron.log         # cron 出力ログ
└── logs/
    ├── 20260227-143012-a1f.log   # タスクごとの実行ログ
    └── ...
```

### タスクの状態遷移

```
pending ──(schedule)──→ scheduled ──(時刻到達)──→ running ──→ completed
   │                       │                         │
   └──(run/run-next)───→ running                     └──→ failed
```

## `/my:spec-impl` をスケジュール実行する例

`spec-impl.md` は対話型スラッシュコマンドなので `-p` モードでは直接呼び出せません。
代わりに、コマンドの内容をシステムプロンプトとして渡す方法を使います。

```bash
# spec-impl のワークフローを深夜に実行
./scripts/claude-scheduler.sh add \
  "auth-feature のタスク 3,4,5 を実装して。仕様は .kiro/specs/auth-feature/ を参照。" \
  --system-prompt ./commands/my/spec-impl.md \
  --at "02:00" \
  --project ~/myapp \
  --max-turns 80 \
  --tools "Read,Edit,Write,Bash,Glob,Grep,Task,WebFetch"
```

## 注意事項

- **`--dangerously-skip-permissions`**: 無人実行では Claude Code が権限確認をブロックします。必要に応じてスクリプト側でこのフラグを追加してください（信頼できる環境でのみ）
- **APIコスト**: 長時間タスクはトークン消費が大きいため `--max-turns` の設定を推奨
- **タイムゾーン**: スケジュール時刻はシステムのローカルタイムゾーンに従います
- **同時実行**: ロックにより1タスクずつ実行されます。前のタスクが完了するまで次のタスクは待機します
