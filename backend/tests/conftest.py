import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-deepgram")
    monkeypatch.setenv("EXA_API_KEY", "test-exa")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.com/jwks.json")
    monkeypatch.setenv("CLERK_ISSUER", "https://example.com")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://glass:glass_dev@127.0.0.1:5432/glass_test",
    )
