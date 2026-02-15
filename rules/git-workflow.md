# Git Workflow

## Commit Message Format

```
<type>: <description>

<optional body>
```

Types: feat, fix, refactor, docs, test, chore, perf, ci

Note: Attribution disabled globally via ~/.claude/settings.json.

## Pull Request Workflow

When creating PRs:
1. Analyze full commit history (not just latest commit)
2. Use `git diff [base-branch]...HEAD` to see all changes
3. Draft comprehensive PR summary
4. Include test plan with TODOs
5. Push with `-u` flag if new branch

## Feature Implementation Workflow

1. **Plan First**
   - Use **planner** agent to create implementation plan
   - Identify dependencies and risks
   - Break down into phases

2. **TDD Approach**
   - Use **tdd-guide** agent
   - Write tests first (RED)
   - Implement to pass tests (GREEN)
   - Refactor (IMPROVE)
   - Verify 80%+ coverage

3. **Code Review**
   - Use **code-reviewer** agent immediately after writing code
   - Address CRITICAL and HIGH issues
   - Fix MEDIUM issues when possible

4. **Commit & Push**
   - Detailed commit messages
   - Follow conventional commits format

## Versioning (Semantic Versioning)

バージョンは `VERSION` ファイルで一元管理し、`scripts/sync-version.sh` で `.claude-plugin/` 配下に反映する。

**機能改修・バグ修正時のバージョンアップは必須**:

| 変更の規模 | バージョン | 判断基準 | 対応者 |
|---|---|---|---|
| バグ修正・軽微な改善 | **パッチ** (x.y.Z) | 既存機能の修正、ドキュメント改善、小規模な機能追加 | Claude が自律的に実行 |
| 機能追加・既存機能の拡張 | **マイナー** (x.Y.0) | 新エージェント追加、新コマンド追加、ワークフローの大幅改善 | Claude が自律的に実行 |
| 破壊的変更・大規模刷新 | **メジャー** (X.0.0) | 互換性のない変更、アーキテクチャ刷新、大規模リファクタリング | **ユーザーに相談してから実行** |

**手順**:
1. `VERSION` ファイルのバージョンをインクリメント
2. `scripts/sync-version.sh` を実行して全ファイルに反映
3. バージョン変更を含めてコミット
