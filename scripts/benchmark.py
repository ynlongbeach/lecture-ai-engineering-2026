"""第1回 発展課題用 ベンチマークスクリプト。

複数のモデルと質問に対して、応答時間・トークン数・生成速度（tokens/s）を計測し、
Markdown 表形式で出力します。

使い方:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --models gemini-2.5-flash gemini-2.0-flash
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# プロジェクトルートを PYTHONPATH に追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google import genai
from google.genai import errors

from app.config import api_error_message, get_api_key

DEFAULT_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

QUESTIONS = [
    {
        "id": "Q1 (短文・一般)",
        "prompt": "LoRAとは何ですか？簡潔に説明してください。",
    },
    {
        "id": "Q2 (講座固有)",
        "prompt": "AIE2026の講座の宿題にある「3レベル」とは何ですか？",
    },
    {
        "id": "Q3 (長文・解説)",
        "prompt": "機械学習における過学習（Overfitting）の原因と代表的な対策手法（正則化、ドロップアウト等）について詳細に解説してください。",
    },
]


@dataclass
class BenchmarkResult:
    model: str
    question_id: str
    prompt: str
    prompt_tokens: int | None
    candidates_tokens: int | None
    latency_sec: float
    tokens_per_sec: float | None
    error: str | None = None


def run_single_benchmark(
    client: genai.Client, model: str, question_id: str, prompt: str
) -> BenchmarkResult:
    start_time = time.perf_counter()
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        elapsed = time.perf_counter() - start_time

        usage = response.usage_metadata
        p_tokens = usage.prompt_token_count if usage else None
        c_tokens = usage.candidates_token_count if usage else None

        tps = (c_tokens / elapsed) if c_tokens and elapsed > 0 else None

        return BenchmarkResult(
            model=model,
            question_id=question_id,
            prompt=prompt,
            prompt_tokens=p_tokens,
            candidates_tokens=c_tokens,
            latency_sec=elapsed,
            tokens_per_sec=tps,
        )
    except errors.APIError as e:
        elapsed = time.perf_counter() - start_time
        err_msg = api_error_message(e.code, e.message)
        return BenchmarkResult(
            model=model,
            question_id=question_id,
            prompt=prompt,
            prompt_tokens=None,
            candidates_tokens=None,
            latency_sec=elapsed,
            tokens_per_sec=None,
            error=err_msg,
        )
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        return BenchmarkResult(
            model=model,
            question_id=question_id,
            prompt=prompt,
            prompt_tokens=None,
            candidates_tokens=None,
            latency_sec=elapsed,
            tokens_per_sec=None,
            error=str(e),
        )


def format_markdown_table(results: List[BenchmarkResult]) -> str:
    lines = [
        "| モデル | 質問種別 | 応答時間 (秒) | 入力トークン | 出力トークン | 生成速度 (tokens/s) | 状態 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in results:
        status = "成功" if not r.error else f"エラー: {r.error}"
        p_tok = str(r.prompt_tokens) if r.prompt_tokens is not None else "-"
        c_tok = str(r.candidates_tokens) if r.candidates_tokens is not None else "-"
        tps = f"{r.tokens_per_sec:.1f}" if r.tokens_per_sec is not None else "-"
        lines.append(
            f"| `{r.model}` | {r.question_id} | {r.latency_sec:.2f}s | {p_tok} | {c_tok} | {tps} | {status} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini API ベンチマーク計測スクリプト")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="計測対象のモデルリスト（スペース区切り）",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="リクエスト間の待機秒数（レート制限対策）",
    )
    args = parser.parse_args()

    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    print("=" * 60)
    print("Gemini API ベンチマーク計測を開始します")
    print(f"対象モデル: {', '.join(args.models)}")
    print(f"対象質問数: {len(QUESTIONS)}")
    print("=" * 60)

    results: List[BenchmarkResult] = []

    for model in args.models:
        print(f"\n--- モデル: {model} ---")
        for q in QUESTIONS:
            print(f"実行中: [{q['id']}] ... ", end="", flush=True)
            res = run_single_benchmark(client, model, q["id"], q["prompt"])
            results.append(res)
            if res.error:
                print(f"失敗 ({res.error})")
            else:
                print(
                    f"完了 ({res.latency_sec:.2f}s, 入力:{res.prompt_tokens}, 出力:{res.candidates_tokens}, {res.tokens_per_sec:.1f} tok/s)"
                )
            time.sleep(args.interval)

    print("\n" + "=" * 60)
    print("【計測結果 Markdown テーブル】")
    print("=" * 60 + "\n")
    table_md = format_markdown_table(results)
    print(table_md)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

