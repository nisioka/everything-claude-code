---
description: Convert kiro spec to project document format
allowed-tools: Bash, Read, Write, Glob, Grep, Task
argument-hint: <input-kiro-spec-dir> <output-document-dir>
---

# Kiro Spec → Project Document 変換

<background_information>
- **Mission**: kiro形式の設計仕様（requirements.md, design.md, research.md）を、プロジェクト固有のドキュメントテンプレート群（feature-spec.md, api-spec.md, database-spec.md, frontend-spec.md, implementation-guide.md, test-spec.md）に変換する
- **Success Criteria**:
  - kiro specの全情報が漏れなくプロジェクト形式のドキュメントに反映される
  - 既存ドキュメントの文体・構造・粒度に合致する
  - 出力ディレクトリに7ファイル（README.md + 6テンプレート対応ファイル）が生成される
</background_information>

<instructions>
## Core Task
kiro spec ディレクトリ（第1引数）の内容を読み取り、プロジェクトドキュメント形式に変換して出力ディレクトリ（第2引数）に書き出す。

**引数**: $ARGUMENTS
- 第1引数: 入力 kiro spec ディレクトリパス（例: `.kiro/specs/bcc-email-lead-creation`）
- 第2引数: 出力 document ディレクトリパス（例: `document/01-features/bcc-email-lead`）

## Execution Steps

### Phase 1: 入力の読み取り
1. **kiro spec 読み込み**: 第1引数ディレクトリ内の全ファイルを読む
   - `spec.json` — メタデータ（言語設定等）
   - `requirements.md` — 要件定義（EARS形式）
   - `design.md` — 設計（Architecture, Components, Data Models, API Contracts, Flows等）
   - `research.md` — 調査・設計判断の記録（存在する場合）
2. **spec.json の language フィールド**を確認し、出力言語を決定する

### Phase 2: テンプレート・既存実例の把握
3. **テンプレート読み込み**: `document/99-templates/` 配下の全テンプレートを読む
   - `feature-spec.md`, `api-spec.md`, `database-spec.md`, `frontend-spec.md`, `implementation-guide.md`, `test-spec.md`
4. **既存ドキュメントの参照**: `document/01-features/` 配下から2-3機能の実例を読み、実際の記述粒度・文体・略記法を把握する

### Phase 3: マッピング変換
5. 以下のマッピングルールで変換し、出力ディレクトリに書き出す:

| kiro spec ソース | 出力ファイル | 主な変換内容 |
|-----------------|-------------|-------------|
| requirements.md 全体 + design.md Overview/Architecture/Flows | `feature-spec.md` | 概要・業務ルール・UI要件・画面遷移・アーキテクチャ構成 |
| design.md API Contract セクション | `api-spec.md` | エンドポイント一覧・リクエスト/レスポンス仕様・エラー定義 |
| design.md Data Models / Physical Data Model | `database-spec.md` | テーブル定義・ER図・インデックス・マイグレーションSQL |
| requirements.md UI要件 + design.md Components(フロント関連) | `frontend-spec.md` | 画面レイアウト・UI要素・コンポーネント構成・状態管理 |
| design.md Components(バックエンド関連) + Technology Stack | `implementation-guide.md` | ファイル構成・実装パターン・既存コード参照・フェーズ分け |
| design.md Testing Strategy | `test-spec.md` | ユニット/統合/E2E/パフォーマンス/セキュリティテスト |

6. **README.md** を生成: 機能概要・ドキュメント一覧・関連ドキュメントリンク

### Phase 4: 文体の統一
7. 既存ドキュメントの文体に合わせる:
   - TL;DR セクション（api-spec, database-spec で使われている場合）
   - 変更履歴テーブル
   - 実装参照パス形式（`references/backend/src/...`）
   - ASCII レイアウト図（既存で使われている場合）

## Important Constraints
- kiro specに存在しない情報を推測で補完しない（UI詳細が未定義の場合は「要設計」と明記）
- 既存ドキュメントのフォーマットを厳密に踏襲する（独自セクションを追加しない）
- design.md が未生成（spec.json の phase が requirements 以前）の場合、feature-spec.md のみ生成し、他は「設計フェーズ完了後に生成」と記載する
- 出力ディレクトリが既に存在する場合、上書き前にユーザーに確認する
</instructions>

## Tool Guidance
- Use **Glob** to list kiro spec files and existing document examples
- Use **Read** to read kiro spec files, templates, and existing document examples
- Use **Write** to create output documents
- Use **Bash** to create output directory (`mkdir -p`)
- Use **Grep** to find existing document patterns if needed
- Use **Task** (Explore agent) if template or example discovery requires broader search

## Output Description
Provide output in the language specified in `spec.json` with the following structure:

1. **変換サマリー**: 入力ファイル数・出力ファイル数の概要
2. **生成ファイル一覧**: 各ファイルのパスと主な内容（テーブル形式）
3. **マッピング結果**: kiro spec のどのセクションがどの出力ファイルに反映されたか
4. **注意事項**: kiro specに存在せず変換できなかった項目があれば記載

**Format Requirements**:
- Use Markdown headings (##, ###)
- Keep summary concise
- List all generated file paths

## Safety & Fallback
- **入力ディレクトリ不存在**: エラーメッセージを表示し、正しいパスの候補を `.kiro/specs/` から提示
- **テンプレート不存在**: `document/99-templates/` が見つからない場合、既存ドキュメントの構造を参考に変換
- **出力ディレクトリ既存**: 既存ファイルがある場合、上書きするかユーザーに確認
- **design.md 未生成**: feature-spec.md のみ部分生成し、残りは設計完了後に再実行するよう案内
- **引数不足**: 引数が不足している場合、使用方法を表示（`/convert-spec-to-doc <input-dir> <output-dir>`）
