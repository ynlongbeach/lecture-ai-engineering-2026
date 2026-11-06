# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：素のLLMは「3レベル」を一般的なAI活用レベルの話と推測し、最後は講義資料で確認するよう促すだけで、講座固有の意味に答えられなかった。エージェントは 基礎・実装・発展については、ほぼ固定で回答し、どれか1つで完了と正しく答え、末尾に（第1回）も付けた。
- `--trace` で見えたツール呼び出し（ツール名と引数）：「LoRAとQLoRAの違いは？」では `search_glossary({'query': 'LoRA'})` と `search_glossary({'query': 'QLoRA'})` の2回。用語を1つずつ検索していた。
- 1つの質問での LLM 呼び出し回数（`requests`）：2回（ツールを呼んだ後にまとめて回答するため。「3レベル」の質問も requests=2、tool_calls=1）
- 追加したツールと、docstring に書いた説明：`make_quiz(lecture: int)`。「指定した回の用語集から確認問題を1問作って返す。確認問題やクイズを求められたときに使う。answer は利用者が答えるまで伏せる」と記述。該当回の用語が無ければ「第N回の用語は用語集に見つかりませんでした」と返す。「第2回の内容から確認問題を1問出して」で `make_quiz({'lecture': 2})` が呼ばれ、pytest も 18 件通過した。

## 宿題

- 取り組んだレベル：発展
- やったこと：adk_agent/glossary_agent/ に __init__.py と agent.py を作成し、INSTRUCTIONS と演習の3ツール（search_glossary, get_lecture_summary, make_quiz）を Google ADK の Agent に渡して uv run --with google-adk adk run adk_agent/glossary_agent で演習と同じ3問を実行した
- 結果：
  - 書き方の違い：Pydantic AI では指示が複数形 `instructions` でツールを `agent.tool_plain(fn)` で個別登録するのに対し、Google ADK では単数形 `instruction` で、tools 引数（`tools=[...]`）に関数リストをそのまま渡す書き方になる。また、ADK では変数名を `root_agent` にする規約がある。
  - 実行方法の違い：Pydantic AI 版はコマンドライン引数（argparse）で1問1答を実行する形式だったが、ADK では `adk run` コマンドによって標準で対話型 REPL（チャット形式）が提供され、会話履歴を保持したやり取りが容易にできた。
  - 回答の違い：同じモデル（gemini-3.5-flash-lite）、同じ指示、同じツールの説明文（docstring）を渡しているため、3問（「3レベル」「LoRAとQLoRAの違い」「第2回の確認問題」）とも Pydantic AI 版と同様に適切にツールが呼び出され、回答の質や構成（末尾に関連回を付与する点など）もほぼ同等の結果が得られた。
- 気づき・疑問：
  - Pydantic AI から Google ADK にフレームワークを変えても、中心にある「指示（INSTRUCTIONS）」と「ツール関数（型ヒント＋docstring）」は1行も書き換えずにそのまま動いた。エージェントの本質がフレームワーク固有の文法ではなく「モデル＋ループ＋ツール」にあることが実感できた。
  - ADK は `adk run` による対話 REPL やログ出力が標準で揃っており、素早く対話エージェントを立ち上げるのに向いている。
