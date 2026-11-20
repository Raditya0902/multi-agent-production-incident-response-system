import os
import re
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_llm = None
_fallback_llm = None
_using_fallback: bool = False

# Retry config: wait 2^attempt seconds, up to MAX_RETRIES attempts
_MAX_RETRIES = 4
_BASE_WAIT = 2  # seconds


class LLMConfigurationError(ValueError):
    """Actionable error for an invalid provider or model setting."""


def _required_model(variable: str) -> str:
    model = os.getenv(variable, "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", model):
        raise LLMConfigurationError(f"Set {variable} to an available model ID.")
    return model


def primary_llm_settings() -> dict:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "deepseek":
        return {
            "provider": provider,
            "model": _required_model("DEEPSEEK_MODEL"),
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
            "thinking": "disabled",
        }
    if provider != "groq":
        raise LLMConfigurationError("Set LLM_PROVIDER to deepseek or groq.")
    return {
        "provider": provider,
        "model": _required_model("LLM_MODEL"),
        "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.2")),
        "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "4096")),
    }


def _model_rejected(error: Exception) -> bool:
    if getattr(error, "status_code", None) == 404:
        return True
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    details = body.get("error", body)
    if not isinstance(details, dict):
        return False
    return details.get("code") in {"model_not_found", "model_decommissioned", "invalid_model"} or (
        "model not exist" in str(details.get("message", "")).lower()
    )


def _invoke_configured(client, variable: str, *args, **kwargs):
    try:
        return client.invoke(*args, **kwargs)
    except Exception as error:
        if _model_rejected(error):
            raise LLMConfigurationError(
                f"The provider rejected the configured model. Set {variable} to an available model ID."
            ) from None
        raise


def _get_llm():
    global _llm
    if _llm is None:
        settings = primary_llm_settings()
        if settings["provider"] == "deepseek":
            from agents.deepseek import DeepSeekClient

            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise EnvironmentError("Set DEEPSEEK_API_KEY in the ignored .env.")
            _llm = DeepSeekClient(
                model=settings["model"], temperature=settings["temperature"],
                max_tokens=settings["max_tokens"], api_key=api_key,
            )
            return _llm

        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _llm = ChatGroq(
            model=settings["model"],
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"],
            api_key=api_key,
        )
    return _llm


def _get_fallback_llm():
    global _fallback_llm
    if _fallback_llm is not None:
        return _fallback_llm

    provider = os.getenv("FALLBACK_LLM_PROVIDER", "").lower().strip()
    if not provider:
        return None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("[LLM] FALLBACK_LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
            return None
        try:
            from langchain_openai import ChatOpenAI
            _fallback_llm = ChatOpenAI(
                model=_required_model("OPENAI_MODEL"),
                temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
                api_key=api_key,
            )
        except ImportError:
            logger.warning("[LLM] langchain-openai not installed; fallback unavailable")
            return None

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[LLM] FALLBACK_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
            return None
        try:
            from langchain_anthropic import ChatAnthropic
            _fallback_llm = ChatAnthropic(
                model=_required_model("ANTHROPIC_MODEL"),
                temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
                api_key=api_key,
            )
        except ImportError:
            logger.warning("[LLM] langchain-anthropic not installed; fallback unavailable")
            return None

    elif provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("[LLM] FALLBACK_LLM_PROVIDER=gemini but GOOGLE_API_KEY is not set")
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            _fallback_llm = ChatGoogleGenerativeAI(
                model=_required_model("GEMINI_MODEL"),
                temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
                google_api_key=api_key,
            )
        except ImportError:
            logger.warning("[LLM] langchain-google-genai not installed; run: pip install langchain-google-genai")
            return None

    else:
        logger.warning("[LLM] Unknown FALLBACK_LLM_PROVIDER=%s (use 'gemini', 'openai', or 'anthropic')", provider)
        return None

    return _fallback_llm


def is_using_fallback() -> bool:
    return _using_fallback


def _is_rate_limit_error(err_str: str) -> bool:
    return "rate_limit" in err_str or "429" in err_str or "rate limit" in err_str or "resource_exhausted" in err_str


def _is_daily_quota_error(err_str: str) -> bool:
    return "tokens per day" in err_str or "tpd" in err_str


def _invoke_fallback_with_retry(*args, **kwargs):
    """Invoke the fallback LLM with its own retry loop for transient rate limits."""
    fallback = _get_fallback_llm()
    if not fallback:
        return None
    for attempt in range(_MAX_RETRIES):
        try:
            provider = os.getenv("FALLBACK_LLM_PROVIDER", "").strip().upper()
            return _invoke_configured(fallback, f"{provider}_MODEL", *args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if _is_rate_limit_error(err_str) and attempt < _MAX_RETRIES - 1:
                wait = _BASE_WAIT ** (attempt + 1)
                logger.warning(f"[Fallback LLM] Rate limited. Retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})...")
                time.sleep(wait)
                continue
            raise
    return None


def _invoke_with_retry(*args, **kwargs):
    """Call the LLM with exponential backoff on rate limit errors, switching to fallback on quota exhaustion."""
    global _using_fallback

    if _using_fallback:
        result = _invoke_fallback_with_retry(*args, **kwargs)
        if result is not None:
            return result

    for attempt in range(_MAX_RETRIES):
        try:
            client = _get_llm()
            variable = "DEEPSEEK_MODEL" if os.getenv("LLM_PROVIDER", "").strip().lower() == "deepseek" else "LLM_MODEL"
            return _invoke_configured(client, variable, *args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()

            if _is_daily_quota_error(err_str):
                fallback = _get_fallback_llm()
                if fallback:
                    logger.warning("[LLM] Primary provider daily quota exhausted — switching to fallback provider")
                    _using_fallback = True
                    return _invoke_fallback_with_retry(*args, **kwargs)
                raise RuntimeError(
                    "The primary provider reached its daily token limit. Wait for the quota reset or "
                    "choose an available model with higher limits in your .env file."
                ) from e

            if _is_rate_limit_error(err_str) and attempt < _MAX_RETRIES - 1:
                wait = _BASE_WAIT ** (attempt + 1)  # 2s, 4s, 8s, 16s
                logger.warning(f"Rate limited by primary provider. Retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})...")
                time.sleep(wait)
                continue

            raise


class _LazyLLM:
    """Proxy that defers primary client construction until first use."""

    def __getattr__(self, name):
        return getattr(_get_llm(), name)

    def invoke(self, *args, **kwargs):
        return _invoke_with_retry(*args, **kwargs)


llm = _LazyLLM()
