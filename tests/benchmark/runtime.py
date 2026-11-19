"""Run provenance and provider interruption handling shared by the benchmarks."""

from datetime import datetime, timezone

from agents.benchmark_usage import BenchmarkStop
from agents.deepseek import DeepSeekRequestError


def label(settings: dict) -> str:
    return ("legacy, model no longer available" if settings["model"] == "llama-3.3-70b-versatile"
            else f"{settings['model']} baseline")


def run_metadata(settings: dict, commit: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        **settings,
        "git_commit": commit,
        "baseline": label(settings),
        "FALLBACK_LLM_PROVIDER": "",
        "date": now.date().isoformat(),
        "run_at": now.isoformat(),
    }


def interruption(error: Exception) -> bool:
    return isinstance(error, BenchmarkStop) or (
        isinstance(error, DeepSeekRequestError) and error.status_code in {400, 401, 402, 403, 404, 422, 429}
    )
