# Shared benchmark trace boundary

The shared runner applies one harness correction to both frozen pipeline checkouts. Before either adapter turns a traced failing run into incident logs, it drops frames and observed calls whose directory segments include `test` or `tests`. Matching uses whole segments and is case-insensitive. The runner keeps production trace entries in their original order.

For a frozen checkout, load this checkout's `shared_runner.py` as a standalone module and call `run_trials` with the frozen runner, frozen adapter, run arguments and the preselected manifests. The wrapper keeps the pinned adapter and scorer active. It filters only traced reports going into incident construction. Ordinary evaluator verdicts and Docker scoring stay on their existing path.

This correction leaves the frozen refs untouched. Run the boundary unit tests with `python -m pytest -q tests/test_benchmark_trace_boundary.py`. Offline prompt replay compares the serialized role and content for each model request with provider responses fixed. It uses the frozen development snapshots and synthetic scenarios. Test-directory canaries exercise the boundary independently of either dataset.

Verification at `8fbc67e` and `4e811f0` found byte-identical prompts before and after the filter. Each checkout produced 120 matched requests from the 15 development cases and 56 matched requests from the seven synthetic scenarios. The singular-directory canary was removed from v0's prompts. The plural-directory canary was already absent, and a production path under `contest` was unchanged in both checkouts.
