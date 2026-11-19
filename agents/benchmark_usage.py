"""Persistent DeepSeek request reservations and measured benchmark usage."""

import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


# USD nanodollars per token at published peak prices. Off-peak is half.
# https://api-docs.deepseek.com/quick_start/pricing/
PEAK_CACHE_HIT = 6
PEAK_CACHE_MISS = 300
PEAK_OUTPUT = 1200
USD_NANO = 1_000_000_000
CONTEXT_LIMIT = 1_048_576
DEFAULT_LEDGER = Path(__file__).resolve().parent.parent / "tests/benchmark/results/deepseek-usage.sqlite3"
_active = None


class BenchmarkStop(RuntimeError):
    """A benchmark must stop before making any more provider calls."""


def _peak_at(timestamp: datetime) -> bool:
    return timestamp.weekday() < 5 and (1 <= timestamp.hour < 4 or 6 <= timestamp.hour < 10)


class DeepSeekUsage:
    def __init__(self, path: Path, budget: Decimal):
        if not budget.is_finite() or budget < 0:
            raise ValueError("BENCH_MAX_SPEND_USD must be finite and nonnegative.")
        self.path = path
        self.budget = int(budget * USD_NANO)
        self.run_id = uuid4().hex
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, peak INTEGER NOT NULL,
                    guarded INTEGER NOT NULL, estimated INTEGER NOT NULL DEFAULT 0,
                    prompt INTEGER NOT NULL DEFAULT 0, completion INTEGER NOT NULL DEFAULT 0,
                    cached INTEGER NOT NULL DEFAULT 0, reasoning INTEGER NOT NULL DEFAULT 0,
                    settled INTEGER NOT NULL DEFAULT 0
                )
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def reserve(self, max_tokens: int) -> int:
        # The provider caps input at its context limit. Reserve that entire
        # input at the uncached peak price and the configured output max at peak.
        reserve = CONTEXT_LIMIT * PEAK_CACHE_MISS + max_tokens * PEAK_OUTPUT
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            guarded, = conn.execute("SELECT COALESCE(SUM(guarded), 0) FROM requests").fetchone()
            if guarded + reserve > self.budget:
                raise BenchmarkStop(
                    f"Spend guard stopped before the next request "
                    f"(${guarded / USD_NANO:.6f} guarded, ${self.budget / USD_NANO:.2f} limit)."
                )
            return conn.execute(
                "INSERT INTO requests (run_id, peak, guarded) VALUES (?, ?, ?)",
                (self.run_id, _peak_at(datetime.now(timezone.utc)), reserve),
            ).lastrowid

    def settle(self, request: int, usage: dict, normalized: dict):
        prompt = usage.get("prompt_tokens", normalized.get("input_tokens"))
        output = usage.get("completion_tokens", normalized.get("output_tokens"))
        if any(not isinstance(value, int) or value < 0 for value in (prompt, output)):
            raise BenchmarkStop("DeepSeek usage is unavailable. The request's budget reservation was retained.")
        cached = usage.get("prompt_cache_hit_tokens")
        if cached is None:
            cached = (usage.get("prompt_tokens_details") or {}).get(
                "cached_tokens", (normalized.get("input_token_details") or {}).get("cache_read", 0)
            )
        reasoning = (usage.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", (normalized.get("output_token_details") or {}).get("reasoning", 0)
        )
        cached, reasoning = cached or 0, reasoning or 0
        if not 0 <= cached <= prompt or not 0 <= reasoning <= output:
            raise BenchmarkStop("DeepSeek returned inconsistent usage. The request's budget reservation was retained.")
        peak_price = cached * PEAK_CACHE_HIT + (prompt - cached) * PEAK_CACHE_MISS + output * PEAK_OUTPUT
        with closing(self.connect()) as conn, conn:
            peak, guarded = conn.execute(
                "SELECT peak, guarded FROM requests WHERE id = ?", (request,),
            ).fetchone()
            if peak_price > guarded:
                raise BenchmarkStop("DeepSeek usage exceeded the request's reserved upper bound.")
            conn.execute(
                """UPDATE requests SET guarded = ?, estimated = ?, prompt = ?, completion = ?,
                   cached = ?, reasoning = ?, settled = 1 WHERE id = ?""",
                (peak_price, peak_price if peak else peak_price // 2, prompt, output, cached, reasoning, request),
            )

    def reject(self, request: int):
        with closing(self.connect()) as conn, conn:
            conn.execute("UPDATE requests SET guarded = 0, settled = 1 WHERE id = ?", (request,))

    def snapshot(self, *, cumulative=False) -> dict:
        where, params = ("", ()) if cumulative else (" WHERE run_id = ?", (self.run_id,))
        with closing(self.connect()) as conn:
            request_count, unsettled, prompt, output, cached, reasoning, cost, guarded = conn.execute(
                """SELECT COUNT(*), SUM(1 - settled), SUM(prompt), SUM(completion), SUM(cached),
                   SUM(reasoning), SUM(estimated), SUM(guarded) FROM requests""" + where,
                params,
            ).fetchone()
        return {
            "request_count": request_count,
            "unsettled_requests": unsettled or 0,
            "input_tokens": prompt or 0,
            "output_tokens": output or 0,
            "cached_input_tokens": cached or 0,
            "reasoning_tokens": reasoning or 0,
            "estimated_cost_usd": (cost or 0) / USD_NANO,
            "guarded_spend_usd": (guarded or 0) / USD_NANO,
        }


def active_usage():
    return _active


def usage_delta(before: dict, after: dict) -> dict:
    return {key: round(value - before[key], 9) for key, value in after.items()}


@contextmanager
def benchmark_usage(settings: dict):
    global _active
    if os.getenv("FALLBACK_LLM_PROVIDER", "").strip():
        raise ValueError("Benchmarks require FALLBACK_LLM_PROVIDER to be empty.")
    if settings["provider"] != "deepseek":
        yield None
        return
    if settings["model"] != "deepseek-flash":
        raise ValueError("The DeepSeek benchmark spend guard is priced for deepseek-flash.")
    if _active is not None:
        raise ValueError("A DeepSeek benchmark is already running in this process.")
    try:
        meter = DeepSeekUsage(
            Path(os.getenv("BENCH_USAGE_DB", DEFAULT_LEDGER)),
            Decimal(os.getenv("BENCH_MAX_SPEND_USD", "2.50")),
        )
    except ArithmeticError as error:
        raise ValueError("BENCH_MAX_SPEND_USD must be a valid dollar amount.") from error
    _active = meter
    try:
        yield meter
    finally:
        _active = None
