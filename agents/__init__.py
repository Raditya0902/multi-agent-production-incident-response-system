import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_llm = None

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


def _invoke_with_retry(*args, **kwargs):
    """Call the LLM with exponential backoff on rate limit errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return _get_llm().invoke(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "rate_limit" in err_str or "429" in err_str or "rate limit" in err_str
            is_daily_limit = "tokens per day" in err_str or "tpd" in err_str

            if is_daily_limit:
                # Daily quota exhausted — no point retrying
                raise RuntimeError(
                    "Groq daily token limit reached. Wait until tomorrow or switch to a "
                    "model with higher limits (e.g. llama-3.1-8b-instant) in your .env file."
                ) from e

            if is_rate_limit and attempt < _MAX_RETRIES - 1:
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
