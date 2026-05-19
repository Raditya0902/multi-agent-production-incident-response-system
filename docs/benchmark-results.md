# Benchmark Results

## Environment

| Field | Value |
|---|---|
| Model | `llama-3.3-70b-versatile` (Groq) |
| Benchmark scenarios | 7 production-style incidents |
| Run date | 2026-05-04 |
| Python version | 3.11 |
| Platform | Linux (Docker) / macOS |
| Groq temperature | 0.2 |
| Max tokens | 4096 |
| Max retry attempts | 3 |

---

## Aggregate Metrics

| Metric | Result |
|---|---|
| Patch correctness | **100.0%** |
| First-attempt success rate | **71.4%** |
| Retry success rate | **100.0%** |
| False positive rate | **0.0%** |
| Average runtime | **41.1s** per scenario |
| Escalation rate | **0.0%** |

---

## Per-Scenario Breakdown

| # | Scenario | File | Severity | Pass | Correct | Retries | Time |
|---|---|---|---|---|---|---|---|
| 1 | IndexError — file upload crash | `data_processing.py` | P2 | ✓ | ✓ | 3 | 97.2s |
| 2 | KeyError — payment failure | `payment_service.py` | P0 | ✓ | ✓ | 2 | 41.4s |
| 3 | TimeoutError — DB pool exhausted | `database_service.py` | P0 | ✓ | ✓ | 1 | 48.1s |
| 4 | AttributeError — NoneType on user | `notification_service.py` | P2 | ✓ | ✓ | 1 | 33.1s |
| 5 | Mass outage — api_gateway KeyError | `api_gateway.py` | P0 | ✓ | ✓ | 1 | 2.8s |
| 6 | ZeroDivisionError — analytics | `analytics_service.py` | P2 | ✓ | ✓ | 1 | 32.9s |
| 7 | IndexError — order validation | `order_service.py` | P0 | ✓ | ✓ | 1 | 32.2s |

**Pass** — tests passed in the execution sandbox.  
**Correct** — the patch matched the ground-truth fix pattern.  
**Retries** — number of fix attempts (1 = passed on first try).

---

## Metric Definitions

| Metric | Definition |
|---|---|
| `patch_correctness_pct` | % of scenarios where the generated patch contains the ground-truth fix pattern |
| `first_attempt_success_rate` | % where tests passed on the first attempt (`retry_count = 1`) |
| `retry_success_rate` | % of cases that failed attempt 1 but succeeded by attempt 3 |
| `false_positive_rate` | % where tests passed but the patch did **not** contain the correct fix pattern |
| `avg_run_time_seconds` | Average wall-clock time per scenario, from input to incident report |
| `escalation_rate` | % of scenarios that hit `MAX_RETRY_ATTEMPTS` and escalated to a human |

---

## How Correctness Is Evaluated

Patch correctness is **not** determined by semantic code analysis. It is checked by the benchmark runner (`tests/benchmark/run_benchmark.py`) against ground-truth patterns defined in [`tests/benchmark/ground_truth.py`](../tests/benchmark/ground_truth.py).

Each scenario in `ground_truth.py` defines:
- The **buggy source file** (e.g., `app/data_processing.py`)
- The **expected fix patterns** — a list of strings that must all appear in the generated patch (e.g., `["if not items", "return"]`)
- The **error type** and **severity**

A patch is marked correct if every string in the expected fix patterns is present in the generated code. This is a **keyword/pattern match**, not a full semantic correctness proof.

**Honest caveats:**
- This is a controlled benchmark over 7 fixed scenarios with known bugs.
- The same 7 scenarios are used every run; the system has not been tested on novel, unseen production incidents.
- Pattern matching is a necessary but not sufficient condition for correctness — a patch could match the pattern while still introducing other bugs.
- Results may vary across LLM providers, model versions, and Groq rate-limit conditions.

For a full discussion of limitations, see [`limitations.md`](limitations.md).

---

## Reproduce

To run the benchmark and verify these results:

```bash
# Requires GROQ_API_KEY set in .env
python -m tests.benchmark.run_benchmark

# Append results to history file
python -m tests.benchmark.run_benchmark --save-history

# Inspect raw results JSON
cat tests/benchmark/results/latest.json

# Run only first 3 scenarios (faster)
python -m tests.benchmark.run_benchmark --max 3
```

Or with Docker:

```bash
docker compose run --rm app python -m tests.benchmark.run_benchmark
```

Results are written to `tests/benchmark/results/latest.json` after each run. Use the export script to generate a Markdown summary:

```bash
python scripts/export_benchmark_report.py
```
