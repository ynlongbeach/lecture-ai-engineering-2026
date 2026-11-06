"""save_learning_log と承認フローのテスト（LLMもAPIキーも使わない）。"""

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import agent as agent_module
from app import tools


def _model_saving(content: str) -> FunctionModel:
    """最初に save_learning_log を呼び、ツール結果を受け取ったら終了する偽モデル。"""

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("save_learning_log", {"content": content})])
        return ModelResponse(parts=[TextPart("記録しました")])

    return FunctionModel(respond)


def test_save_learning_log_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG_DIR", tmp_path / "learning_log")
    message = tools.save_learning_log("第3回: エージェントはモデル+ループ+ツール")
    files = list((tmp_path / "learning_log").glob("*.md"))
    assert len(files) == 1 and files[0].name in message
    assert "エージェント" in files[0].read_text(encoding="utf-8")


def test_save_learning_log_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG_DIR", tmp_path / "learning_log")
    assert "空です" in tools.save_learning_log("  ")
    assert not (tmp_path / "learning_log").exists()


def test_tool_waits_for_approval_before_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG_DIR", tmp_path / "learning_log")
    with agent_module.agent.override(model=_model_saving("メモ")):
        result = agent_module.agent.run_sync("記録して")
    assert isinstance(result.output, DeferredToolRequests)
    assert [c.tool_name for c in result.output.approvals] == ["save_learning_log"]
    assert not (tmp_path / "learning_log").exists()  # まだ保存されていない


def test_approved_call_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG_DIR", tmp_path / "learning_log")
    with agent_module.agent.override(model=_model_saving("メモ")):
        result = agent_module.run_with_approval(
            agent_module.agent, "記録して", None, input_fn=lambda _: "y"
        )
    assert result.output == "記録しました"
    assert len(list((tmp_path / "learning_log").glob("*.md"))) == 1


def test_denied_call_does_not_save(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG_DIR", tmp_path / "learning_log")
    with agent_module.agent.override(model=_model_saving("メモ")):
        result = agent_module.run_with_approval(
            agent_module.agent, "記録して", None, input_fn=lambda _: "n"
        )
    assert isinstance(result.output, str)
    assert not (tmp_path / "learning_log").exists()
