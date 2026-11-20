# Reproduce the evaluation

Historical measurements are tied to `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` (v0) and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` (v1 without contracts), model `deepseek-flash`, thinking disabled, temperature 0.2, a 4,096-output-token cap and empty fallback. Dates were 2026-11-19 for synthetic and development and 2026-11-20 for held-out, in UTC. Held-out used `6bcacdd8df143e63a9564f3e9940e69657ffd4b1` as the shared harness and `1d95bb940bf13acc567767f2341187922ff2bedb` as the frozen pool.

## Offline verification

Install the app dependencies and start Docker. From the repo root, build the sandbox image and check the docs and local tests. The RAG retrieval tests use an existing seeded local Chroma database.

```sh
docker build -t incident-execution-sandbox:local sandbox
python scripts/check_readme_results.py
python -m pytest tests/ -m 'not integration'
```

Prepare the bare clones described in the [selection ledger](../../tests/benchmark/real/SELECTION.md), using the same directory for both sets. The validation modes evaluate the pinned buggy and fixed revisions without model inference. Held-out validation also checks that the unchanged candidate is rejected.

```sh
docker build -t incident-real-benchmark:stage-a tests/benchmark/real
docker build -t incident-real-heldout:v1-pool tests/benchmark/real/heldout
python -m tests.benchmark.real.run_benchmark validate --repos "$repos"
python -m tests.benchmark.real.heldout.validate_pool --repos "$repos"
```

Restore the private raw archive at its repo-relative paths and verify it from the repo root.

```sh
awk '!/^#/' docs/evaluation/CHECKSUMS | shasum -a 256 -c
```

## Historical model-run commands

These commands describe inference for an independently authorized reproduction. Keep the published files and ledger unchanged. Create fresh worktrees, caches, and a separate spend ledger.

```sh
git worktree add --detach "$v0_checkout" bench-v0-deepseek-flash
git worktree add --detach "$v1_checkout" bench-v1-nocontracts
```

In each frozen checkout, supply the API key privately, keep fallback empty, and use the measured configuration. The Flash transport in both tags disables thinking.

```sh
export LLM_PROVIDER=deepseek DEEPSEEK_MODEL=deepseek-flash
export DEEPSEEK_TEMPERATURE=0.2 DEEPSEEK_MAX_TOKENS=4096 FALLBACK_LLM_PROVIDER=''
export BENCH_MAX_SPEND_USD=3.60 BENCH_USAGE_DB="$fresh_ledger"
docker build -t incident-benchmark-pytest:phase1 sandbox
# In each frozen worktree, invoke the synthetic runner once per planned round.
python -m tests.benchmark.run_benchmark --save-history
python -m tests.benchmark.real.run_benchmark run --repos "$repos" --trials 3
```

The measured synthetic comparison used five full rounds per arm. Development used three trials per case. The held-out run used the archived `final-heldout/launch.py` in `tests/benchmark/results/` from each frozen checkout, with the same shared trace filter and pinned held-out image. Verify the launcher and raw records against [CHECKSUMS](CHECKSUMS). Use a fresh release checkout and adapt the archive launcher's local mirror path to your clones. Record that local adaptation and keep the reference artifact intact. The historical evaluator image digest is in [the validation record](../../tests/benchmark/real/heldout/validation.json).

```sh
# Run each line from its corresponding frozen worktree.
python "$launcher" v0 preflight
python "$launcher" v1 preflight
python "$launcher" v0 run
python "$launcher" v1 run
```

The release comparison fixed three trials per case and allowed reruns only for provider or infrastructure errors, with the original execution retained. Model output, runtime, and cost can vary with serving behavior, availability, caching, pricing and test infrastructure. A fresh run is a new measurement.
