# Spend

The retained ledger covers the 2026-11-19 to 2026-11-20 UTC DeepSeek measurements. Main comparisons used `deepseek-flash`, thinking disabled, temperature 0.2 and a 4,096-token cap. The [ablation ledger](ablations.md) gives each pipeline commit. The [diagnostic](model-sensitivity.md) at `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` additionally used Flash thinking and `deepseek-v4-pro` at the same temperature and cap. All used an empty fallback. The held-out arms were `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` with the shared `6bcacdd8df143e63a9564f3e9940e69657ffd4b1` harness.

| Scope | Requests | Usage-derived cost | Guard charge |
| --- | ---: | ---: | ---: |
| Cumulative before v2 | 4,793 | $1.051595 | $2.103190 |
| v2 additions | 1,123 | $0.224247 | $0.448494 |
| Held-out v0 | 279 | $0.072602 | $0.072602 |
| Held-out v1 without contracts | 271 | $0.105727 | $0.105727 |
| Held-out combined | 550 | $0.178329 | $0.178329 |
| Final cumulative ledger | 6,466 | $1.454171 | $2.730014 |

The final ledger had 4,901,178 input tokens and 1,398,132 output tokens, with zero unsettled requests. Held-out used 335,675 input and 93,350 output tokens. The guard cap was $2.50 before v2 and $3.60 for v2 and the held-out comparison. The guard settles conservatively at peak rates, while the usage-derived estimate uses the applicable rates. At the pre-v2 checkpoint the account owner checked the provider balance and confirmed the corresponding $1.0516 estimate. The final totals are usage-derived. No final invoice was checked.

Runtime and costs depend on output length, retries, cache hits, infrastructure and provider pricing. [Raw ledger and per-run data](CHECKSUMS)
