# Synthetic regression suite

## Database timeout contract

The production-shaped fixture uses a placeholder connection from its pool. The
test replaces the acquire operation with a fake connection and accounts for
the acquired slot. The fake raises Python's built-in TimeoutError immediately
from execute. A valid fix surfaces the service's documented QueryTimeoutError
and returns the connection slot to the pool. The held-out case also checks that
pool exhaustion remains a distinct error and successful queries return rows.
This measures timeout error handling at the service boundary. The fixture
contains no database driver, actual waits, or concurrent load.

## Service contracts

| Module | Bug regression | Held-out coverage |
| --- | --- | --- |
| data_processing | Empty batch returns no item | Upper and lower boundaries, valid negative indexing |
| payment_service | Missing transaction raises PaymentError and records no payment | Missing nested amount, valid minimum amount |
| database_service | Query timeout translated and acquired slot released | Pool exhaustion distinguished from query timeout, successful result preserved |
| notification_service | Missing user causes no dispatch | A subsequent known user receives a welcome email |
| api_gateway | Unknown service returns a 503 error payload | Registered route preserves path and payload, empty service still rejected |
| analytics_service | Empty period returns zero conversion | Nonzero period preserves counts and rounds the conversion percentage |
| order_service | Empty order raises OrderError | Negative quantity on a later item is rejected, valid input still accepted |

The smoke and final scoring workspaces contain the applicable source and
pytest files. Reference patches stay in reference_fixes/ and are used only
by the contract verification unit test. The graph receives smoke test output
only. Held-out files are staged after the graph's execution and retry loop
returns, and their output is kept out of model inputs.

## Run the suite

```sh
docker build --tag incident-benchmark-pytest:phase1 sandbox
pytest tests/test_benchmark_contracts.py tests/test_benchmark_scoring.py
python -m tests.benchmark.run_benchmark --save-history
python scripts/export_benchmark_report.py
```

The benchmark needs a valid Groq key, Docker access, and the configured
sentence embedding model. The runner auto-approves generated fixes. Each
invocation creates a throwaway Chroma store from the bundled Markdown files
at the top level of `rag/past_incidents/`. The benchmark skips dashboard
feedback and the locally downloaded corpus in `rag/past_incidents/real/`.

Each scenario resolves when the final candidate passes both the service and
held-out pytest files. Missing tests, evaluator setup errors, and runs that
produce no candidate are invalid and unscored. A candidate that cannot be
applied fails. The headline denominator includes every requested scenario.
The disagreement matrix counts only rows with a test verdict and a pattern
verdict. Pattern match retains the legacy substring check as a diagnostic.
The runner writes `results/synthetic-latest.json` and optionally appends to
`results/synthetic-history.jsonl`.
