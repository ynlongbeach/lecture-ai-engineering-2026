from unittest.mock import MagicMock
from scripts.benchmark import (
    BenchmarkResult,
    format_markdown_table,
    run_single_benchmark,
)


def test_format_markdown_table():
    results = [
        BenchmarkResult(
            model="gemini-2.5-flash",
            question_id="Q1",
            prompt="test",
            prompt_tokens=10,
            candidates_tokens=100,
            latency_sec=2.0,
            tokens_per_sec=50.0,
        ),
        BenchmarkResult(
            model="gemini-2.5-pro",
            question_id="Q2",
            prompt="test2",
            prompt_tokens=None,
            candidates_tokens=None,
            latency_sec=1.5,
            tokens_per_sec=None,
            error="API error",
        ),
    ]

    table = format_markdown_table(results)
    assert "`gemini-2.5-flash`" in table
    assert "50.0" in table
    assert "成功" in table
    assert "エラー: API error" in table


def test_run_single_benchmark_success():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.usage_metadata.prompt_token_count = 15
    mock_response.usage_metadata.candidates_token_count = 120
    mock_client.models.generate_content.return_value = mock_response

    result = run_single_benchmark(mock_client, "test-model", "Q1", "hello")
    assert result.model == "test-model"
    assert result.prompt_tokens == 15
    assert result.candidates_tokens == 120
    assert result.latency_sec >= 0
    assert result.tokens_per_sec is not None
    assert result.error is None

