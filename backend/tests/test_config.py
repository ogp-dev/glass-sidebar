def test_settings_loads_required_keys() -> None:
    from glass.config import Settings

    s = Settings()
    assert s.anthropic_api_key == "test-anthropic"
    assert s.deepgram_api_key == "test-deepgram"
    assert s.exa_api_key == "test-exa"
