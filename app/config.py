"""講座全体で共通の設定。

APIキーやモデル名はコードに書かず、環境変数またはローカルの tmp/gemini_api_key.txt から読み込む。
"""

import os
from pathlib import Path

# 既定モデル。環境変数 AIE_MODEL を設定すると切り替えられる。
#   例: export AIE_MODEL=gemini-3.5-flash
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MODEL = os.getenv("AIE_MODEL", DEFAULT_MODEL)

# 第5回: 1ページを1チャンクとして検索する。索引はscripts/build_rag_index.pyで作成する。
ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT
LOCAL_KEY_FILE = ROOT / "tmp" / "gemini_api_key.txt"
RAG_SOURCE = ROOT / "data/rag_data/lectures.json"
RAG_TREE = ROOT / "data/rag_data/tree.json"
RAG_GRAPH = ROOT / "data/rag_data/graph.json"
RAG_DB = Path(os.getenv("AIE_RAG_DB", str(ROOT / "data/rag_data/index.sqlite3")))
RAG_DOCUMENT_IDS = ("lec01-main", "lec02-main", "lec03-main")
RAG_TOP_K = 5
GRAPH_START_K = 3
GRAPH_HOPS = 2
GRAPH_MAX_RESULTS = 10
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
# 2,048トークンの上限に対し、タスク指定等の分を残す。超過時は切り捨てず停止する。
EMBEDDING_MAX_TOKENS = 2000


def api_error_message(status: int, detail: str = "") -> str:
    """HTTPステータスコードを、受講生向けの日本語の説明にする（ask.py と agent.py で共用）。"""
    if status == 429:
        return "レート制限に達しました。1分ほど待ってから再実行してください。"
    if status == 503:
        return "モデルが混み合っています（503）。少し待ってから再実行してください。"
    if status in (400, 401, 403, 404):
        return f"APIキーかモデル名に問題があります（{status}）: {detail}"
    return f"APIエラー（{status}）: {detail}"


def get_api_key() -> str:
    """環境変数 GEMINI_API_KEY または tmp/gemini_api_key.txt から APIキーを返す。

    未設定なら手順を表示して終了する。
    """
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    # ローカルの tmp/gemini_api_key.txt から読み込み（.gitignore 対象）
    if LOCAL_KEY_FILE.is_file():
        try:
            file_key = LOCAL_KEY_FILE.read_text(encoding="utf-8").strip()
            if file_key:
                return file_key
        except OSError:
            pass

    raise SystemExit(
        "Gemini API キーが見つかりません。\n"
        "以下のいずれかの方法で設定してください：\n"
        "1. ローカル利用時: tmp/gemini_api_key.txt に APIキーを保存する（Git除外設定済み）\n"
        "2. 環境変数の設定: export GEMINI_API_KEY='your-key' (Windows: $env:GEMINI_API_KEY='your-key')\n"
        "3. Codespaces 利用時: GitHub Settings → Codespaces → Secrets に GEMINI_API_KEY を登録\n"
    )
