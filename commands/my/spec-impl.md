---
description: Execute spec tasks using TDD with quality review and PR creation
allowed-tools: Bash, Read, Write, Edit, MultiEdit, Grep, Glob, LS, WebFetch, WebSearch, Task
argument-hint: <feature-name> [task-numbers] [-y]
---

# Smart Implementation Executor

<background_information>
- **Mission**: cc-sddで分解されたタスクを、TDD・品質レビュー・PR作成まで一気通貫で実行
- **Success Criteria**:
  - 全タスクがTDDで実装され、tasks.mdにマーク済み
  - 各タスク完了時にコミット（日本語メッセージ、`.kiro/` は除外）
  - 品質レビュー（リファクタリング、カバレッジ、検証、コードレビュー）の全指摘に対応
  - レビュー指摘はタスク化し、サブエージェントで修正（フィードバックループ）
  - PRが作成される
  - PR作成/Push後のボットレビューコメントにも自動対応（PHASE 4）
</background_information>

<instructions>

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    /my:spec-impl workflow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PHASE 1: タスク実装（順次処理）                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  For each unchecked task:                                  │ │
│  │    1. タスク内容に応じた適切なサブエージェントに委任（コンテキスト分離）│ │
│  │    2. TDD実装 (RED → GREEN → REFACTOR)                     │ │
│  │    3. tasks.md を [ ] → [x] に更新                         │ │
│  │    4. コミット（日本語メッセージ、.kiro/ は除外）          │ │
│  │    → 次のタスクへ                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  PHASE 2: 品質向上・レビュー（全タスク完了後）                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  1. /refactor-clean → デッドコード削除                     │ │
│  │  2. /test-coverage → カバレッジ改善                        │ │
│  │  3. verification-loop skill → ビルド・型・リント・テスト   │ │
│  │  4. code-reviewer agent → 全指摘を対応                     │ │
│  │     ↓                                                      │ │
│  │  指摘あり → tasks.mdに追記 → PHASE 1 に戻る               │ │
│  │  指摘なし → PHASE 3 へ                                     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  PHASE 3: PR作成                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  gh pr create でプルリクエストを作成                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  PHASE 4: PRレビュー・CI 対応（ボット/CI 自動対応）             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  1. スマート待機（コメント検知 or CI完了 / 上限2h）        │ │
│  │  2. pr-review-responder → コメント・CI失敗を取得           │ │
│  │  3. レビュー指摘・CI失敗をタスク化 → tasks.md              │ │
│  │  4. サブエージェントに委任して修正（指摘＋CI）             │ │
│  │  5. コミット＆プッシュ                                     │ │
│  │     ↓                                                      │ │
│  │  スマート再待機 → 指摘/CI失敗あり → 修正ループ(上限5回)    │ │
│  │  指摘/CI失敗なし → 完了                                    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Core Task

Execute implementation tasks for feature **$1** using Test-Driven Development.

## Execution Steps

### Step 0: Load Context & Select Tasks

**Read all necessary context**:
- `.kiro/specs/$1/spec.json`, `requirements.md`, `design.md`, `tasks.md`
- `.kiro/steering/` directory for project memory

**Validate approvals**:
- If `-y` flag provided: Auto-approve tasks in spec.json (`approvals.tasks.approved: true` に設定)
- Otherwise: Verify tasks are approved in spec.json (stop if not)

**Determine tasks to execute**:
- If `$2` provided: Execute specified task numbers (e.g., "1.1" or "1,2,3")
- Otherwise: Execute all pending tasks (unchecked `- [ ]` in tasks.md)

---

### PHASE 1: タスク実装（順次処理）

For each selected task:

#### 1.1 サブエージェントに委任

**Important**: 各タスクは独立したサブエージェントで実行する（コンテキスト分離のため）

`skills/agent-router/SKILL.md` の **Task-Type Routing Table** に従って、タスクの内容に応じて最適な `subagent_type` を選択する。
多くは `general-purpose` で問題ないが、明確に適したエージェントがある場合はそちらを優先する。

agent-router スキルの **Standard Invocation Pattern** に従って Task tool を呼び出す。

サブエージェントへの指示内容:
- タスクの具体的な実装内容
- 関連するdesign.mdの該当セクション
- 使用するファイルパス
- TDD手順（下記参照）

#### 1.2 TDD実装（サブエージェント内で実行）

1. **RED - Write Failing Test**:
   - テストを先に書く（まだ実装がないので失敗する）
   - 説明的なテスト名を使用

2. **GREEN - Write Minimal Code**:
   - テストを通す最小限の実装
   - 過剰な設計を避ける

3. **REFACTOR - Clean Up**:
   - コード構造の改善
   - 重複の除去
   - 全テストがパスすることを確認

#### 1.3 タスク完了処理

サブエージェント完了後:

1. **Mark Complete**: tasks.md の `- [ ]` を `- [x]` に更新

2. **Commit**: 日本語でコミットメッセージを作成
   - **`.kiro/` ディレクトリはコミット対象外**とする（仕様書・タスク管理ファイルはワーキングドキュメント）
   - ステージングは `git add` で対象ファイルを個別に指定する（`git add -A` は使わない）
   - `.kiro/` 配下のファイルが誤ってステージされていないことを `git status` で確認する
   ```bash
   # .kiro/ を除外してステージング
   git add --all -- ':!.kiro/'
   git commit -m "$(cat <<'EOF'
   feat: [タスク番号] [タスク内容の要約]

   - 実装した機能の詳細
   - テスト追加
   EOF
   )"
   ```

3. 次のタスクへ進む

---

### PHASE 2: 品質向上・レビュー（全タスク完了後）

全てのタスクが完了したら、以下を順番に実行:

#### 2.1 /refactor-clean

デッドコードを検出・削除:
```bash
# knip, depcheck, ts-prune で検出
# テスト実行して安全を確認後に削除
```

#### 2.2 /test-coverage

カバレッジを確認・改善:
```bash
# 80%未満のファイルを特定
# 不足テストを生成
```

#### 2.3 verification-loop skill

skills/verification-loop/SKILL.md に従って検証:

```
Phase 1: Build Verification
Phase 2: Type Check
Phase 3: Lint Check
Phase 4: Test Suite (coverage)
Phase 5: Security Scan (secrets, console.log)
Phase 6: Diff Review
```

**Output Format**:
```
VERIFICATION REPORT
==================

Build:     [PASS/FAIL]
Types:     [PASS/FAIL] (X errors)
Lint:      [PASS/FAIL] (X warnings)
Tests:     [PASS/FAIL] (X/Y passed, Z% coverage)
Security:  [PASS/FAIL] (X issues)
Diff:      [X files changed]

Overall:   [READY/NOT READY] for PR
```

#### 2.4 code-reviewer agent

code-reviewer エージェントを起動:
- 変更されたファイルをレビュー
- **全ての指摘（CRITICAL / HIGH / MEDIUM / LOW）を対応対象とする**

#### 2.5 レビュー指摘のフィードバックループ

レビューで指摘事項がある場合:

1. **tasks.md にレビュー指摘タスクを追記**:
   - `## Review Fixes (Round N)` セクションを tasks.md の末尾に追加
   - 各指摘を `- [ ] [Review] {severity}: {指摘内容} ({対象ファイル}:{行番号})` 形式で記載
   - severity: CRITICAL / HIGH / MEDIUM / LOW

2. **PHASE 1 に戻る**:
   - 追記したレビュー指摘タスクを対象として PHASE 1 を再実行
   - サブエージェントのタイプは `skills/agent-router/SKILL.md` の **Review-Category Routing Table** に従って選択する

3. **再度 PHASE 2 を実行**:
   - レビュー指摘の修正完了後、PHASE 2.1〜2.4 を再実行
   - 新たな指摘がなくなるまでループを繰り返す
   - **ループ上限: 3回**（3回を超えた場合は残存する指摘を最終レポートに記載し、PHASE 3 に進む）

レビューで指摘事項がない場合:
- そのまま PHASE 3 に進む

---

### PHASE 3: PR作成

全ての品質チェックをパスしたら（またはレビューループ上限到達後）:

```bash
# プッシュ
git push -u origin <current-branch>

# PR作成（既存PRがある場合はスキップ）
gh pr create --title "[Feature] $1 の実装" --body "$(cat <<'EOF'
## Summary
- [実装内容の要約]

## Tasks Completed
- [x] Task 1: ...
- [x] Task 2: ...

## Test Coverage
- X% coverage achieved

## Review Results
- Code Review: PASSED
- Security: PASSED
- Verification: PASSED
EOF
)"
```

PR番号を取得して PHASE 4 に渡す:
```bash
PR_NUMBER=$(gh pr view --json number -q '.number')
```

---

### PHASE 4: PRレビュー・CI 対応（ボット/CI フィードバック自動対応）

PR作成後（またはPush更新後）、自動レビューボット（CodeRabbit、Copilot 等）のフィードバックと CI チェック結果に対応する。

#### 4.1 スマート待機（レビューコメント / CI を監視）

固定の `sleep` ではなく、PR の状態を定期ポーリングし、対応すべきイベントが発生した
時点で待機を抜ける。レビューコメントが早く来た場合は CI 完了を待たずに対応へ進み、
コメントが無い場合は CI 完了まで待つ。

**待機を抜ける条件（先に成立したもの）:**

| `WAIT_RESULT` | 条件 |
|---|---|
| `COMMENTS` | 新規レビューコメント（レビュー / インライン / 会話）を検知 |
| `CI_DONE`  | CI チェックが全て完了（`pending` が 0 件） |
| `NO_CI`    | CI チェックが存在せず、猶予 10 分を経過 |
| `TIMEOUT`  | 上限 **2時間**（7200秒）を経過 |

**ポーリング間隔: 60秒。**

> **重要**: この監視は最大2時間かかり得るためフォアグラウンドのコマンドタイムアウトを
> 超える。**必ずバックグラウンドで実行**し（`run_in_background: true`）、完了通知を
> 受け取ってから `WAIT_RESULT` に応じて分岐すること。

```bash
PR=<PR_NUMBER>
# baseline: 初回は PR 作成時刻、再ループ時は LAST_FETCH_TIMESTAMP
BASELINE="${LAST_FETCH_TIMESTAMP:-$(gh pr view "$PR" --json createdAt -q '.createdAt')}"
START=$(date +%s); DEADLINE=$((START + 7200)); GRACE=$((START + 600))
RESULT=""
while :; do
  # 新規レビューコメントの検知（レビュー / インライン / 会話）
  N=$(gh api "repos/{owner}/{repo}/pulls/$PR/reviews"   --jq "[.[]|select(.submitted_at>\"$BASELINE\")]|length" 2>/dev/null || echo 0)
  N=$((N + $(gh api "repos/{owner}/{repo}/pulls/$PR/comments"  --jq "[.[]|select(.created_at>\"$BASELINE\")]|length" 2>/dev/null || echo 0)))
  N=$((N + $(gh api "repos/{owner}/{repo}/issues/$PR/comments" --jq "[.[]|select(.created_at>\"$BASELINE\")]|length" 2>/dev/null || echo 0)))
  if [ "$N" -gt 0 ]; then RESULT="COMMENTS"; break; fi

  # CI チェックの状態（gh pr view の statusCheckRollup を使用）
  TOTAL=$(gh pr view "$PR" --json statusCheckRollup --jq '.statusCheckRollup | length' 2>/dev/null || echo 0)
  PEND=$(gh pr view "$PR" --json statusCheckRollup --jq '[.statusCheckRollup[] | select((.__typename=="CheckRun" and .status!="COMPLETED") or (.__typename=="StatusContext" and (.state=="PENDING" or .state=="EXPECTED")))] | length' 2>/dev/null || echo 0)
  TOTAL=${TOTAL:-0}; PEND=${PEND:-0}
  if [ "$TOTAL" -gt 0 ] && [ "$PEND" -eq 0 ]; then RESULT="CI_DONE"; break; fi
  if [ "$TOTAL" -eq 0 ] && [ "$(date +%s)" -ge "$GRACE" ]; then RESULT="NO_CI"; break; fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then RESULT="TIMEOUT"; break; fi

  sleep 60
done
echo "WAIT_RESULT=$RESULT"
```

待機終了後、`WAIT_RESULT` に応じて分岐する:

| `WAIT_RESULT` | 次のアクション |
|---|---|
| `COMMENTS` | 4.2 へ（レビューコメントを取得・対応。CI 完了は待たない） |
| `CI_DONE`  | 4.2 へ（レビューコメント取得 + CI 失敗の確認の両方を実施） |
| `NO_CI`    | 4.2 へ（レビューコメント対応のみ。CI 確認はスキップ） |
| `TIMEOUT`  | 4.2 で現時点の状態を取得して可能な範囲で対応し、残りは最終レポートに記載 |

#### 4.2 レビューコメント・CI 結果の取得

##### 4.2.1 レビューコメント取得・解析

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
- 次回ループ（4.6）の再呼び出し時に `since` パラメータとして渡す
- これにより、前回取得済みのコメントを重複処理することを防ぐ

エージェントが返す構造化データ:
- 各コメントの severity（CRITICAL / HIGH / MEDIUM / LOW）
- カテゴリ（security, performance, code-quality, bug, style, testing）
- 対象ファイル・行番号
- 元のコメント本文
- **Fetch Timestamp**（次回ループ用）

##### 4.2.2 CI 失敗の取得

`WAIT_RESULT` が `CI_DONE` または `TIMEOUT` の場合のみ実施する（`COMMENTS` / `NO_CI`
ではスキップ）。CI チェック結果を確認し、失敗があればログを取得する:

```bash
# 失敗・エラーになったチェックを一覧
gh pr view <PR_NUMBER> --json statusCheckRollup --jq \
  '.statusCheckRollup[] | select(((.conclusion // .state) // "") | test("FAILURE|ERROR|CANCELLED|TIMED_OUT")) | {name, result: (.conclusion // .state), url: (.detailsUrl // .targetUrl)}'

# GitHub Actions の失敗ログ（該当ブランチ直近の失敗 run）
RUN_ID=$(gh run list --branch "$(git branch --show-current)" --status failure --limit 1 --json databaseId -q '.[0].databaseId')
[ -n "$RUN_ID" ] && gh run view "$RUN_ID" --log-failed
```

失敗ログから原因（ビルド / 型 / Lint / テスト失敗など）を特定し、修正対象とする。
失敗チェックが無い（全て `pass` / `skip`）場合は CI 対応不要。

#### 4.3 レビュー指摘・CI 失敗のタスク化

対応可能なレビュー指摘・CI 失敗がある場合、tasks.md に追記:

```markdown
## PR Review Fixes (Round N)
- [ ] [PR-Review] CRITICAL (security): XSS脆弱性の修正 (`src/api/handler.ts:42`)
  > Original: "User input is not sanitized before rendering..."
- [ ] [PR-Review] HIGH (performance): N+1クエリの解消 (`src/db/users.ts:15`)
  > Original: "This query inside a loop causes N+1 problem..."
- [ ] [CI-Failure] HIGH (build): 型エラーの修正 (`tsc` / `src/service.ts:88`)
  > Log: "Type 'string' is not assignable to type 'number'..."
- [ ] [CI-Failure] HIGH (testing): 失敗テストの修正 (`user.spec.ts`)
  > Log: "Expected 200, received 500..."
```

#### 4.4 サブエージェントに委任して修正

`skills/agent-router/SKILL.md` の **Review-Category Routing Table** に従って、各指摘を適切なサブエージェントに委任する。CI 失敗も内容に応じて委任する:

| 対象 | 委任先（例） |
|---|---|
| レビュー指摘 | カテゴリ別（agent-router のルーティング表に従う） |
| ビルド / 型エラー | `ecc:build-error-resolver` |
| テスト失敗 | 実装担当エージェント（`ecc:tdd-guide` 等） |
| Lint / フォーマット崩れ | `ecc:refactor-cleaner` 等 |

サブエージェントへの指示内容は agent-router スキルの **Standard Invocation Pattern** に従い、以下を含める:
- 元のレビューコメント本文 / CI 失敗ログの要点（コンテキスト理解のため）
- 対象ファイル・行番号
- 修正方針

#### 4.5 修正のコミット＆プッシュ

全指摘の修正後:

```bash
# .kiro/ を除外してステージング
git add --all -- ':!.kiro/'
git commit -m "$(cat <<'EOF'
fix: PRレビュー指摘対応 (Round N)

- [修正内容の要約]
EOF
)"

# プッシュ
git push -u origin <current-branch>
```

#### 4.6 再確認ループ

プッシュ後、再度ボットレビューと CI が走るため:

1. **`LAST_FETCH_TIMESTAMP` を `pr-review-responder` が返した最新の `Fetch Timestamp` に更新**（4.2 のタイムスタンプ管理に従う）
2. **4.1 のスマート待機を再実行**（バックグラウンド。`COMMENTS` / `CI_DONE` / `NO_CI` / `TIMEOUT` を再判定）
3. **新たなレビュー指摘または CI 失敗があれば** → 4.2〜4.5 を繰り返す
4. **レビュー指摘も CI 失敗も無ければ** → 完了

**ループ上限: 5回**（初回 + 再確認4回の計5ラウンド）

上限到達時:
- 残存する未対応コメント・CI 失敗を最終レポートに記載
- ユーザーに手動対応を促す

#### 4.7 対応不要な場合

`pr-review-responder` が「対応可能な指摘なし」と判断し、かつ CI 失敗も無い場合:
- PHASE 4 をスキップし、そのまま最終レポートに進む

</instructions>

## Error Handling

### 即時停止（環境エラー）

以下のエラーは復帰困難なため即時停止:
- ポート競合 (EADDRINUSE)
- 権限エラー (EACCES, EPERM)
- ディスク容量不足 (ENOSPC)
- ネットワーク接続不可
- 依存関係の解決不可

**対応**: エラー内容を報告し、手動での解決を促す

### リトライ上限（同一エラー5回）

同じエラーが5回発生した場合:
- 実装を停止
- エラーパターンと試行内容を報告
- 別のアプローチを提案

### その他のエラー

| エラー | 対応 |
|--------|------|
| テスト失敗 | サブエージェント内で修正を試行 |
| ビルドエラー | build-error-resolver を起動 |
| カバレッジ不足 | 追加テスト生成 |

## Safety & Fallback

### Tasks Not Approved or Missing Spec Files
- **Stop Execution**: All spec files must exist and tasks must be approved
- **Suggested Action**: "Run `/my:spec-impl $1 -y` to auto-approve tasks and proceed, or complete previous phases: `/kiro:spec-requirements`, `/kiro:spec-design`, `/kiro:spec-tasks`"

### Task Execution Examples

**Execute specific task(s)**:
- `/my:spec-impl feature-name 1.1` - Single task
- `/my:spec-impl feature-name 1,2,3` - Multiple tasks

**Execute all pending (default)**:
- `/my:spec-impl feature-name` - All unchecked tasks

**Auto-approve tasks and execute**:
- `/my:spec-impl feature-name -y` - Auto-approve and execute all pending
- `/my:spec-impl feature-name 1,2 -y` - Auto-approve and execute specific tasks

## Output Description

最終レポート（日本語）:

```markdown
## 実装完了レポート

### サマリー
- **Feature**: [feature-name]
- **Status**: ✅ 完了 / ⚠️ 要対応
- **Tasks**: X/Y 完了
- **Coverage**: Z%

### 完了タスク
- [x] 1. タスク名
- [x] 2. タスク名

### 品質レビュー結果
- デッドコード削除: ✅
- テストカバレッジ: ✅ (80%+)
- 検証: ✅
- コードレビュー: ✅
- レビューループ: N回（全指摘対応済み / 残存指摘あり）

### レビュー指摘対応
- [x] [Review] HIGH: ... (Round 1)
- [x] [Review] MEDIUM: ... (Round 1)
（未対応の指摘がある場合はここに記載）

### PR
- URL: https://github.com/...

### PRレビュー・CI 対応（PHASE 4）
- ボットレビュー: X件の指摘を検出 / CI 失敗: W件を検出
- 対応済み: Y件
- 残存（手動対応要）: Z件
- ラウンド数: N/5

### 次のステップ
- [ ] 残存PRレビューコメントの手動対応（あれば）
- [ ] PRレビュー依頼
- [ ] 関連ドキュメント更新
```

think
