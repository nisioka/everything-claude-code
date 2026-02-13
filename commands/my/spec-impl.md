---
description: Execute spec tasks using TDD with quality review and PR creation
allowed-tools: Bash, Read, Write, Edit, MultiEdit, Grep, Glob, LS, WebFetch, WebSearch, Task
argument-hint: <feature-name> [task-numbers]
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
- Verify tasks are approved in spec.json (stop if not)

**Determine tasks to execute**:
- If `$2` provided: Execute specified task numbers (e.g., "1.1" or "1,2,3")
- Otherwise: Execute all pending tasks (unchecked `- [ ]` in tasks.md)

---

### PHASE 1: タスク実装（順次処理）

For each selected task:

#### 1.1 サブエージェントに委任

**Important**: 各タスクは独立したサブエージェントで実行する（コンテキスト分離のため）

**エージェントタイプの選択**: タスクの内容に応じて最適な `subagent_type` を判断する。
多くは `general-purpose` で問題ないが、明確に適したエージェントがある場合はそちらを優先する。

| タスクの性質 | subagent_type | 判断基準 |
|---|---|---|
| 一般的な機能実装 | `general-purpose` | デフォルト。複合的なタスク |
| テスト実装が主体 | `ecc:tdd-guide` | テストの追加・修正が中心のタスク |
| E2Eテスト | `ecc:e2e-runner` | Playwrightを使ったE2Eテスト |
| ビルド/型エラー修正 | `ecc:build-error-resolver` | ビルドエラーや型エラーの修正 |
| リファクタリング/デッドコード削除 | `ecc:refactor-cleaner` | コード整理・不要コード削除 |
| セキュリティ対応 | `ecc:security-reviewer` | 認証・入力検証・脆弱性対応 |
| Kotlin/Quarkus実装 | `ecc:kotlin-coder` | Kotlin実装、Quarkus設定、native image対応 |
| SQL/スキーマ設計 | `ecc:sql-coder` | SQL記述、マイグレーション、クエリ最適化 |
| JPA/Hibernateエンティティ | `ecc:jpa-model-coder` | エンティティ設計、リレーション、N+1対策 |
| TypeScript/Next.js実装 | `ecc:nextjs-coder` | React/Next.js 16コンポーネント、Server Actions、API routes |
| Terraform/IaC実装 | `ecc:terraform-coder` | Terraform設定、モジュール設計、クラウドインフラ、状態管理 |

```markdown
Task tool を使用:
- prompt: タスク説明 + 関連コンテキスト
- subagent_type: （上記テーブルから適切なものを選択）
- description: "Implement task X.Y"
```

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
   - サブエージェントのタイプは指摘内容に応じて選択（例: セキュリティ指摘なら `ecc:security-reviewer`）

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

# PR作成
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
- **Suggested Action**: "Complete previous phases: `/kiro:spec-requirements`, `/kiro:spec-design`, `/kiro:spec-tasks`"

### Task Execution Examples

**Execute specific task(s)**:
- `/my:spec-impl feature-name 1.1` - Single task
- `/my:spec-impl feature-name 1,2,3` - Multiple tasks

**Execute all pending (default)**:
- `/my:spec-impl feature-name` - All unchecked tasks

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

### 次のステップ
- [ ] PRレビュー依頼
- [ ] 関連ドキュメント更新
```

think
