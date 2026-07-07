# Waza 互換 評価ハーネス 運用ガイド

このディレクトリ (`evals/`) は、Claude Code スキル (現在は `skills/make-pr/`) を Waza 互換 YAML で評価するためのスイート置き場です。本ドキュメントは harness の **運用** にフォーカスし、設計思想や Markdown 形式の Capability/Regression Eval については `skills/eval-harness/SKILL.md` を参照してください。

- 実行系: `scripts/eval/` (Python, `uv` 管理)
- モデル呼び出し: `claude` (Claude Code CLI) を subprocess で起動する経路に統一
- スペック: `.kiro/specs/eval-harness-integration/`

> **認証は `claude` CLI 任せ**です。`claude login` で Max/Pro サブスクリプションを使うこともできるし、`ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` を env で渡してもよい。eval-harness 側は API キーを直接読み取らず、`subprocess.run(["claude", "-p", ...])` の戻り JSON だけを扱います。

---

## 1. 何を評価しているか

`evals/<suite>/eval.yaml` ごとに、対象スキルの 1 フェーズ (1 つの責務) を独立してテストします。現状のスイートは以下の 3 本:

| Suite | 対象フェーズ | Grader 構成 |
| --- | --- | --- |
| `make-pr-commit-message` | コミットメッセージ生成 | `regex` (Conventional Commits) + `llm_judge` (主題品質) |
| `make-pr-ticket-extract` | ブランチ名からのチケット抽出 | `regex` (チケット ID 形式) + 他 |
| `make-pr-sensitive-file` | 機密ファイル検出 | `list_match` (検出対象集合の包含関係) |

各スイートは `eval.yaml` + 同階層の `fixtures/` (任意) で完結します。フィクスチャは `{{name}}` プレースホルダで prompt に埋め込まれます (`scripts/eval/config.py:_resolve_fixtures`)。

---

## 2. ローカル運用

### 2.1 初回セットアップ

```bash
# 1) Claude Code CLI が PATH 上にあることを確認
claude --version

# 2) Max / Pro サブスクで使う場合はログイン (一度だけ)
claude login

# 3) Python 依存関係をインストール (uv.lock 固定)
uv sync --frozen
```

`uv` 未導入なら先に `curl -LsSf https://astral.sh/uv/install.sh | sh`。

### 2.2 mock 実行 (`claude` CLI を呼ばないスモークテスト)

`MockExecutor` は task の `expected` をそのままモデル出力として echo するため、grader 配線・fixture 解決・パイプラインの結線確認をモデル呼び出しゼロで行えます。サブスク枠も消費しません。

```bash
uv run python -m scripts.eval evals/make-pr-commit-message/eval.yaml --executor mock
```

`list_match` で `parse_mode: json_array` を使うスイート (例: `make-pr-sensitive-file`) は、mock 出力も JSON 配列形式に揃える必要があります:

```bash
EVAL_HARNESS_MOCK_FORMAT=json uv run python -m scripts.eval \
  evals/make-pr-sensitive-file/eval.yaml --executor mock
```

### 2.3 `claude_cli` 本実行

```bash
uv run python -m scripts.eval \
  evals/make-pr-commit-message/eval.yaml \
  --output results.json \
  --verbose
```

内部的には各 task ごとに以下が起動します:

```bash
claude -p \
  --output-format json \
  --model <eval.yaml の model> \
  --system-prompt <skill_path の内容 + instructions> \
  --disallowed-tools "Bash,Edit,Read,WebFetch,..."
# prompt は stdin から渡されます (ARG_MAX 回避)
```

ツールは全て `--disallowed-tools` で無効化しているので、ファイル編集や Web 取得、Bash 実行は走りません。

| フラグ | 用途 |
| --- | --- |
| `--executor mock\|claude_cli` | YAML の `config.executor` を上書き |
| `--output PATH` | EvalResult JSON を書き出し |
| `--verbose` | task ごとの grader 内訳を stdout に出力 |

### 2.4 終了コード

`scripts/eval/cli.py` 由来:

- `0` ─ すべての task が pass
- `1` ─ 1 つ以上の task が fail (モデル出力が grader を満たさない)
- `2` ─ 設定 / 実行エラー (YAML 不正、`claude` CLI 不在、CLI が `is_error=true` を返した、subprocess タイムアウト 等)

---

## 3. eval.yaml の書き方

```yaml
config:
  executor: claude_cli             # "mock" でも可
  model: claude-sonnet-5         # `claude --model` が受け付ける名前 (sonnet/haiku のエイリアスも可)
  skill_path: skills/make-pr/SKILL.md   # system prompt の前半に挿入
  instructions: |
    対象フェーズの固定 system prompt (skill_path の前に置かれる)

tasks:
  - id: short-stable-id
    prompt: "...{{diff}}..."       # {{name}} は fixtures.name で 1 パス置換
    fixtures:
      diff: fixtures/diff-feat-rate-limit.txt
    expected: "feat(api): add per-user rate limiting middleware"

graders:
  - type: regex
    name: conv_commits
    weight: 2.0
    config:
      pattern: '^(feat|fix|docs)(\([^)]+\))?:\s.+'
      mode: match                  # "no_match" で否定アサーション
  - type: llm_judge
    name: subject_quality
    weight: 1.0
    config:
      judge_model: claude-sonnet-5
      threshold: 0.7               # passed = (score >= threshold)
      timeout_sec: 180             # judge CLI 1 呼び出しの上限
      rubric: |
        Score 1.0 when ALL of:
        - imperative mood
        - subject under 72 chars
        - type prefix matches diff
```

> **system prompt の組み立て**: `instructions` (strip して空でなければ) と `skill_path` のファイル内容を `\n\n---\n\n` で連結し、`--system-prompt` 引数として CLI に渡します。両方空の場合は eval-harness 既定のフォールバック文が入ります。

### 3.1 Grader 選定ガイド

| Grader | 強み | 使いどころ |
| --- | --- | --- |
| `regex` | 決定的・モデル呼び出しなし | フォーマット制約 (Conventional Commits, チケット ID 形式) |
| `list_match` | 集合演算 (exact / superset / subset) | 「機密ファイルを 1 件も漏らさず検出」のような包含検証。`use_task_expected: true` で task ごとに `expected` を切り替えられる |
| `llm_judge` | 主観的品質 | 命令形か、要約が diff を反映しているか等。task 1 件につき judge_model への CLI 呼び出しが 1 回追加される |

スコアは grader ごとの `score × weight` を合計し、`weight` の合計で割った加重平均が task の `weighted_score`。`passed` は grader 個別の合否、task `status` は全 grader pass なら `pass`、1 つでも fail なら `fail`、内部例外なら `error`。

### 3.2 フィクスチャの規約

- パスは `eval.yaml` からの相対パス
- 安全制御: フィクスチャ resolve 後のパスは eval ディレクトリ配下に閉じ込められる (`config.py` の containment guard)。`../../etc/hostname` のような脱出は `ConfigValidationError`
- 置換は 1 パス: fixture A の内容に `{{B}}` が含まれていても、B として再展開されない (`config.py` の `re.sub` 一括置換)

---

## 4. 認証と CI に関する注意

### 4.1 ローカルでの認証

`claude` CLI が認証情報をどこから読むかは Claude Code 側の挙動に従います。優先順 (Claude Code 2.x 系) は概ね:

1. クラウドプロバイダ環境変数 (Bedrock 等を使う場合)
2. `ANTHROPIC_AUTH_TOKEN`
3. `ANTHROPIC_API_KEY`
4. `apiKeyHelper` (settings の helper script)
5. `CLAUDE_CODE_OAUTH_TOKEN` (1 年有効、`claude setup-token` で生成)
6. `claude login` の OAuth サブスクリプション

**通常運用は `claude login` でサブスク利用するのが最も安価**です。ハーネス側は何も意識しません。

### 4.2 CI

GitHub Actions ワークフローは **本ブランチで撤去** しました (`.github/workflows/eval-make-pr.yml` および `scripts/eval/ci/` を削除)。PR ごとの自動評価は現在走りません。必要になったら以下のいずれかで復活可能:

- `claude setup-token` で `CLAUDE_CODE_OAUTH_TOKEN` を発行 → GitHub Secrets に登録 → CI runner で `claude` をインストール + token 注入
- API キー運用に戻す: Secrets に `ANTHROPIC_API_KEY`、CI 側で `claude` をインストール

いずれにせよ「PR ごとに評価」が必要になってから再導入で十分という判断です。

---

## 5. 新しい評価スイートを追加する手順

1. `evals/<skill>-<phase>/` ディレクトリを作成
2. `eval.yaml` を書く (上記 3 章のひな形)
3. 必要なら `fixtures/` 配下に入力ファイルを置く (パスは eval ディレクトリ内に閉じる)
4. ローカルで mock スモーク + `claude_cli` 本実行を確認
5. (CI を再導入したら) workflow に追加

スイートを足す判断基準は `skills/eval-harness/SKILL.md` の "When to add a YAML eval" 節を参照。

---

## 6. トラブルシューティング

| 症状 | 原因 / 確認 |
| --- | --- |
| `ClaudeCliError: claude CLI is not on PATH` | `claude` を install したシェルとは別のシェルから実行している。`which claude` を確認 |
| `ClaudeCliError: claude CLI reported is_error=true (api_error_status=...)` | モデル名の誤り (`bogus-model` 等) 、または認証が CLI 側で通っていない。`claude -p "ping" --output-format json` を素で打って切り分け |
| `ClaudeCliError: claude CLI timed out` | task 単位の `timeout_sec` を伸ばすか、prompt を短縮。デフォルトは 300 秒 |
| `JUDGE_ERROR: ...` が grader reason に出る | judge への CLI 呼び出しが失敗、または judge 出力が JSON として解釈不能。CLI を直接叩いて応答を確認 |
| mock 実行で `list_match` が常に fail | `EVAL_HARNESS_MOCK_FORMAT=json` を付ける (`parse_mode: json_array` の場合) |
| `ConfigValidationError: fixture ... escapes eval directory` | `../` で eval ディレクトリ外を参照している。fixture をディレクトリ内にコピーする |
| `ConfigValidationError: fixture ... references missing file` | パスのタイポ、または fixture を commit し忘れ |
| キャッシュヒットが 0 のまま | 1 度目は cache_creation のみ、2 度目以降で cache_read が発生する。同じ system_prompt 内容なら 5 分〜1 時間程度キャッシュ寿命がある |

---

## 7. コストと運用 Tips

- 同一スイート内の task は同じ `skill_path + instructions` を system prompt として送るため、**2 task 目以降は cache hit** する (`--output-format json` の `cache_read_input_tokens` で観測可能)。`claude` CLI 自体の内部システム (約 30k tokens) も同 process 横断でキャッシュされる
- `llm_judge` は task ごとに別 CLI を起動するので、task × judge_count に比例して時間がかかる。決定的に判定できる制約は `regex` / `list_match` に寄せる
- ローカルだけで完結する設計なので、PR を出す前に一度通しておくのが安全。`--output results.json` を git 管理外で残せばベースラインとの比較に使える
- Max/Pro サブスクで運用する場合は使用量ダッシュボード (`claude /usage`) を併用するとレート消費を可視化できる

---

## 8. 参考

- 設計と哲学: `skills/eval-harness/SKILL.md`
- スペック (要件 / 設計 / タスク): `.kiro/specs/eval-harness-integration/`
- 実装エントリポイント: `scripts/eval/cli.py`
- 共通 CLI ラッパー: `scripts/eval/claude_cli_runner.py`
- Executor: `scripts/eval/executors/claude_cli.py`
- Judge: `scripts/eval/graders/llm_judge.py`
