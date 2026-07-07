# Rules（ルール）解説

## ルールとは

**ルール**は、Claude Codeが常に従うべきガイドラインです。セキュリティ、コードスタイル、テスト、Gitワークフローなど、プロジェクト全体に適用される規約を定義します。

### 配置場所

```
~/.claude/rules/
```

---

## ルール一覧

| ルール | 説明 | 重要度 |
|--------|------|--------|
| **security.md** | セキュリティチェック、シークレット管理 | 最重要 |
| **coding-style.md** | イミュータビリティ、ファイル構成、エラーハンドリング | 高 |
| **testing.md** | TDDワークフロー、80%カバレッジ要件 | 高 |
| **git-workflow.md** | コミットフォーマット、PRワークフロー | 中 |
| **agents.md** | エージェントオーケストレーション、使用タイミング | 中 |
| **patterns.md** | API レスポンス、リポジトリパターン | 中 |
| **performance.md** | モデル選択、コンテキスト管理 | 中 |
| **hooks.md** | フックシステム、TodoWriteベストプラクティス | 低 |

---

## 各ルールの詳細

### security.md - セキュリティ

**コミット前の必須チェック：**
- [ ] ハードコードされたシークレットがないこと
- [ ] すべてのユーザー入力が検証されていること
- [ ] SQLインジェクション対策（パラメータ化クエリ）
- [ ] XSS対策（HTMLサニタイズ）
- [ ] CSRF保護が有効
- [ ] 認証/認可の確認
- [ ] レート制限
- [ ] エラーメッセージが機密情報を漏洩しない

**シークレット管理：**
```typescript
// NG: ハードコード
const apiKey = "sk-proj-xxxxx"

// OK: 環境変数
const apiKey = process.env.OPENAI_API_KEY
```

---

### coding-style.md - コードスタイル

**イミュータビリティ（最重要）：**
```typescript
// NG: ミューテーション
function updateUser(user, name) {
  user.name = name  // ミューテーション！
  return user
}

// OK: イミュータブル
function updateUser(user, name) {
  return { ...user, name }
}
```

**ファイル構成：**
- 小さなファイルを多数 > 大きなファイルを少数
- 200-400行が標準、800行が上限
- 機能/ドメインで整理

**コード品質チェックリスト：**
- [ ] 読みやすく適切な命名
- [ ] 関数は50行未満
- [ ] ファイルは800行未満
- [ ] ネスト深度は4レベル以下
- [ ] 適切なエラーハンドリング
- [ ] console.logがない
- [ ] ハードコード値がない

---

### testing.md - テスト

**最低カバレッジ：80%**

**必須テストタイプ：**
1. **ユニットテスト** - 個別関数、ユーティリティ
2. **インテグレーションテスト** - APIエンドポイント、DB操作
3. **E2Eテスト** - 重要なユーザーフロー（Playwright）

**TDD必須ワークフロー：**
1. テストを先に書く（RED）
2. テスト実行 - 失敗すべき
3. 最小限の実装（GREEN）
4. テスト実行 - 成功すべき
5. リファクタリング（IMPROVE）
6. カバレッジ確認（80%+）

---

### git-workflow.md - Gitワークフロー

**コミットメッセージフォーマット：**
```
<type>: <description>

<optional body>
```

**タイプ：** feat, fix, refactor, docs, test, chore, perf, ci

**機能実装ワークフロー：**
1. **計画** - plannerエージェントで実装計画
2. **TDD** - tdd-guideエージェントでテストファースト
3. **レビュー** - コミット前に /code-review を実行（プロジェクト固有の深掘りが必要な場合は code-reviewer エージェント）
4. **コミット** - Conventional Commitsに従う

---

### agents.md - エージェントオーケストレーション

**即座にエージェントを使用すべき場面：**
1. 複雑な機能リクエスト → **planner**
2. バグ修正/新機能 → **tdd-guide**
3. アーキテクチャ判断 → **architect**

コードレビューはコミット前の /code-review で実施し、プロジェクト固有の深掘り（OWASP・ライセンス監査・性能分析）が必要な場合に **code-reviewer** エージェントを使用する。

**並列実行を常に使用：**
```markdown
# 良い例：並列実行
3つのエージェントを並列起動：
1. Agent 1: auth.tsのセキュリティ分析
2. Agent 2: キャッシュシステムのパフォーマンスレビュー
3. Agent 3: utils.tsの型チェック

# 悪い例：不要な順次実行
Agent 1、次にAgent 2、次にAgent 3
```

---

### patterns.md - 共通パターン

**APIレスポンスフォーマット：**
```typescript
interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  meta?: {
    total: number
    page: number
    limit: number
  }
}
```

**リポジトリパターン：**
```typescript
interface Repository<T> {
  findAll(filters?: Filters): Promise<T[]>
  findById(id: string): Promise<T | null>
  create(data: CreateDto): Promise<T>
  update(id: string, data: UpdateDto): Promise<T>
  delete(id: string): Promise<void>
}
```

---

### performance.md - パフォーマンス

**モデル選択戦略：**

特定バージョンではなくモデルティアで選択する（ティア間の能力差は世代ごとに変わるため、最新のモデル能力・価格は公式ドキュメントで確認する）。

| ティア | 用途 | コスト |
|--------|------|--------|
| **Haiku 系** | 軽量エージェント、頻繁な呼び出し、機械的タスク（ドキュメント更新・整形・分類）、マルチエージェントのワーカー | 低 |
| **Sonnet 系** | メイン開発と大半のコーディング、マルチエージェントオーケストレーション、ビルド修正・テスト生成、通常のリファクタリング | 中 |
| **Opus 系** | 複雑なアーキテクチャ判断、長時間の自律的作業と深いデバッグ、セキュリティレビュー、調査・分析タスク | 高 |

エージェントには原則 `inherit`（セッションのモデルを継承）を検討し、明確に安価/高性能なティアが適する場合のみ固定する。

**コンテキストウィンドウ管理：**

コンテキスト残り20%では避けるべき作業：
- 大規模リファクタリング
- 複数ファイルにまたがる機能実装
- 複雑なインタラクションのデバッグ

コンテキスト感度が低い作業：
- 単一ファイル編集
- 独立したユーティリティ作成
- ドキュメント更新

---

### hooks.md - フックシステム

**フックタイプ：**
- **PreToolUse**: ツール実行前（検証、パラメータ修正）
- **PostToolUse**: ツール実行後（自動フォーマット、チェック）
- **Stop**: セッション終了時（最終検証）

**TodoWriteベストプラクティス：**
- マルチステップタスクの進捗追跡
- 指示の理解確認
- リアルタイムステアリング有効化
- 詳細な実装ステップ表示

---

## カスタマイズ提案

### 1. プロジェクト固有ルールの追加

技術スタックに応じてルールを追加：

```markdown
# react-patterns.md

## Reactパターン

- useState/useReducerの使い分け
- カスタムフックの命名規則
- コンポーネント分割の基準
```

### 2. 不要なルールの削除/調整

使わない技術のルールは削除または調整：
- Playwrightを使わない → E2Eテストの記述を調整
- 別のコミット規約を使う → git-workflow.mdを調整

### 3. 厳格度の調整

プロジェクトに応じて厳格度を調整：
- カバレッジ要件: 80% → 90%
- ファイル行数: 800行 → 500行

---

## 参考リンク

- [Claude Code Docs - Rules](https://code.claude.com/docs/en/rules)
- [元リポジトリ - rules/](https://github.com/affaan-m/everything-claude-code/tree/main/rules)
