import pytest

import agents


@pytest.mark.parametrize(
    ("provider", "variable", "model"),
    [("groq", "LLM_MODEL", "openai/gpt-oss-20b"), ("deepseek", "DEEPSEEK_MODEL", "deepseek-flash")],
)
def test_provider_and_model_are_explicit(monkeypatch, provider, variable, model):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(variable, "")
    with pytest.raises(agents.LLMConfigurationError, match=variable):
        agents.primary_llm_settings()
    monkeypatch.setenv(variable, model)
    settings = agents.primary_llm_settings()
    assert (settings["provider"], settings["model"]) == (provider, model)


@pytest.mark.parametrize("provider", ["", "invalid"])
def test_unknown_provider_names_env_setting(monkeypatch, provider):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    with pytest.raises(agents.LLMConfigurationError, match="LLM_PROVIDER"):
        agents.primary_llm_settings()


@pytest.mark.parametrize(
    ("provider", "variable", "status", "code"),
    [("groq", "LLM_MODEL", 400, "model_not_found"), ("deepseek", "DEEPSEEK_MODEL", 404, None)],
)
def test_unknown_model_rejected_by_provider_names_env_setting(monkeypatch, provider, variable, status, code):
    class UnknownModel(RuntimeError):
        status_code = status
        body = {"error": {"code": code}}

    class Client:
        def invoke(self, *args, **kwargs):
            raise UnknownModel("provider response")

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setattr(agents, "_llm", Client())
    monkeypatch.setattr(agents, "_using_fallback", False)
    with pytest.raises(agents.LLMConfigurationError, match=variable):
        agents.llm.invoke([])
