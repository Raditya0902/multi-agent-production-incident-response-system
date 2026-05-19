import os
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


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _llm = ChatGroq(
            model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("GROQ_MAX_TOKENS", "4096")),
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
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
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
                model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
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
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
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
            return fallback.invoke(*args, **kwargs)
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
            return _get_llm().invoke(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()

            if _is_daily_quota_error(err_str):
                fallback = _get_fallback_llm()
                if fallback:
                    logger.warning("[LLM] Groq daily quota exhausted — switching to fallback provider")
                    _using_fallback = True
                    return _invoke_fallback_with_retry(*args, **kwargs)
                raise RuntimeError(
                    "Groq daily token limit reached. Wait until tomorrow or switch to a "
                    "model with higher limits (e.g. llama-3.1-8b-instant) in your .env file."
                ) from e

            if _is_rate_limit_error(err_str) and attempt < _MAX_RETRIES - 1:
                wait = _BASE_WAIT ** (attempt + 1)  # 2s, 4s, 8s, 16s
                logger.warning(f"Rate limited by Groq. Retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})...")
                time.sleep(wait)
                continue

            raise


class _LazyLLM:
    """Proxy that defers ChatGroq construction until first use."""

    def __getattr__(self, name):
        return getattr(_get_llm(), name)

    def invoke(self, *args, **kwargs):
        return _invoke_with_retry(*args, **kwargs)


llm = _LazyLLM()
