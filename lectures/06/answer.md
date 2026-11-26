# 第6回 解答

## 演習

<!-- [tool call] の行は、表示された行をそのまま貼り付けてください。終わらなかった STEP は、空欄のままでかまいません。 -->

- STEP 1 のツールの名前：`glossary_search_glossary`
- STEP 2 の [tool call]：`[tool call]   glossary_search_glossary({'query': '3レベル'})`
- STEP 3 の [tool call]：`[tool call]   fetch_fetch({'url': 'https://modelcontextprotocol.io/'})`
- STEP 4 の [tool call]：
  - `[tool call]   aws_aws___search_documentation({'topics': ['general'], 'search_phrase': 'Amazon S3 バージョニング 概要'})`
  - `[tool call]   aws_aws___search_documentation({'search_phrase': '"Using versioning" "Amazon S3"', 'topics': ['general']})`
- 気づき・疑問：
  - `app/mcp_servers.json` に接続設定を数行書き足すだけで、自作サーバー（`uv` による stdio 起動）、公開サーバー（`uvx` による `mcp-server-fetch==2026.11.11` 取得＋stdio 起動）、外部ホストサーバー（`url` による Streamable HTTP 接続）の3種類を、エージェント側（`app/mcp_agent.py`）のコード無変更で同じように扱えた。
  - ツールの名前空間（`サーバー名_ツール名`）により複数サーバー間でツール名が衝突しない一方、サーバーを増やすとモデルに見えているツール数と説明文が増え、入力トークン数も増加することを確認した（STEP 2: 1ツール・715 tokens → STEP 3: 2ツール・2,230 tokens → STEP 4: 7ツール・11,508 tokens／モデル応答3回）。
  - 外部サーバーを使う際は、提供元の信頼性やリスクの確認が重要であることも実感した（STEP 3 のログでも `fetch` が先に `robots.txt` を確認してからページを取得する動きが見えた一方、STEP 4 の外部ホストサーバーには質問内容がそのまま送信される）。

## 宿題

<!-- 基礎・実装・発展のどれか1つに取り組めば完了です。 -->

- 取り組んだレベル：発展
- やったこと：
  - 調査日 **2026-11-25** 時点の Gemini CLI 公式ドキュメントを参照し、MCP サーバーの設定方法を「設定を書く場所」「コマンドで起動する書き方」「URL で接続する書き方」「有効になる範囲」の4観点で演習の [app/mcp_servers.json](../../app/mcp_servers.json) と比較した。
- 結果：
  - **調査日**：2026-11-25
  - **参照した公式ドキュメント URL**：
    - MCP サーバー設定ガイド: https://geminicli.com/docs/tools/mcp-server/ （ドキュメントソース: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md ）
    - 設定ファイル仕様（Configuration）: https://geminicli.com/docs/reference/configuration/ （ドキュメントソース: https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md ）

| 比較項目 | 演習（`app/mcp_servers.json`） | Gemini CLI（公式ドキュメント） |
|---|---|---|
| **設定を書く場所** | プロジェクト内の [app/mcp_servers.json](../../app/mcp_servers.json) を手動編集（トップレベルキー `"mcpServers"` のみ） | `settings.json` 内の `"mcpServers"`（個別定義）および `"mcp"`（`allowed` / `excluded` 等の一括制御）に記述。または `gemini mcp add` / `remove` / `list` / `enable` / `disable` サブコマンドで登録・管理し、対話中は `/mcp` で確認・切替できる。 |
| **コマンドで起動する書き方** | `"command"`, `"args"`, 任意の `"env"` を記述（stdio） | 同様に `"command"`, `"args"`, `"env"` を記述（CLI では `gemini mcp add <name> <command> [args...]`）。さらに `"cwd"`, `"timeout"`（既定 `600000` ms）, `"trust"`（確認スキップ、既定 `false`）, `"includeTools"`, `"excludeTools"` を指定可能。`env` 内では `$VAR` / `${VAR}`（Windows は `%VAR%`）を展開でき、ホスト側の機密環境変数（`GEMINI_API_KEY`, `*TOKEN*`, `*SECRET*` 等）は未指定だと自動秘匿（redaction）される。 |
| **URL で接続する書き方** | `"url"` を書くと Streamable HTTP として接続 | **SSE と Streamable HTTP でキー名が分かれる**：`"httpUrl"` が Streamable HTTP、`"url"` が SSE（Server-Sent Events）エンドポイント用。さらに `"headers"` 指定や、401 応答時の OAuth 2.0 自動検出にも対応。CLI では `gemini mcp add --transport http <name> <url>` / `--transport sse <name> <url>` で登録する。 |
| **有効になる範囲** | `app.mcp_agent` を実行するときだけ有効（このリポジトリ内に閉じた設定） | 4階層の設定ファイルが優先順位（下位→上位）で適用される：① System defaults → ② **User**（`~/.gemini/settings.json`：全セッション共通）→ ③ **Project**（`<project>/.gemini/settings.json`：そのプロジェクトのみ）→ ④ System settings（`/etc/gemini-cli/settings.json` / Windows は `C:\ProgramData\gemini-cli\settings.json`）。`gemini mcp add` の `-s / --scope` は既定が `project` で、`user` も選択可能。なお `stdio` サーバーはフォルダ信頼（`gemini trust`）がある場合のみ接続される。 |

- 気づき・疑問：
  - **設定形式の互換性と違い**：`app/mcp_servers.json` も Gemini CLI も同じ `"mcpServers"` 形式を採用しているため基本構造はよく似ているが、リモート接続では演習の `"url"` に対し Gemini CLI では `"httpUrl"`（Streamable HTTP）と `"url"`（SSE）が区別される点に注意が必要だった。
  - **セキュリティ境界とスコープ設計**：Gemini CLI には、ホスト側の機密環境変数（`*TOKEN*`, `*SECRET*`, `GEMINI_API_KEY` 等）の自動秘匿、ツール実行確認をスキップする `trust` フラグ、`stdio` 起動時のフォルダ信頼（`gemini trust`）、さらに User / Project / System の4階層スコープなど、実用クライアントならではの安全な運用設計が組み込まれている点が印象的だった。
