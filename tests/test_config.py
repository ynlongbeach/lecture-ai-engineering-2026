import pytest
from app.config import get_api_key


def test_get_api_key_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret-key")
    assert get_api_key() == "env-secret-key"


def test_get_api_key_from_tmp_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_key_file = tmp_path / "gemini_api_key.txt"
    fake_key_file.write_text("file-secret-key\n", encoding="utf-8")

    # config.LOCAL_KEY_FILE をモック
    monkeypatch.setattr("app.config.LOCAL_KEY_FILE", fake_key_file)

    assert get_api_key() == "file-secret-key"


def test_get_api_key_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_key_file = tmp_path / "gemini_api_key.txt"
    monkeypatch.setattr("app.config.LOCAL_KEY_FILE", fake_key_file)

    with pytest.raises(SystemExit) as exc_info:
        get_api_key()

    assert "Gemini API キーが見つかりません" in str(exc_info.value)

