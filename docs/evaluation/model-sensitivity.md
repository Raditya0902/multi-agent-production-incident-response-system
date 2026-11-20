# Model-sensitivity diagnostic

Development only, recorded on 2026-11-19 UTC at pipeline commit `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf`. Both arms used temperature 0.2, a 4,096-output-token cap and empty fallback. One trial per bug on the 15-bug development set. This diagnostic was outside the benchmark and played no role in the held-out shipping rule.

| Model | Thinking | Resolves | Wrong file | Apply failure | Wrong fix | Pipeline error | Requests | Usage-derived USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `deepseek-flash` | Enabled | 1/15 | 8 | 1 | 0 | 5 | 92 | $0.116039 |
| `deepseek-v4-pro` | Disabled | 3/15 | 8 | 2 | 2 | 0 | 113 | $0.102268 |

Flash thinking resolved Black-17. Pro resolved PySnooper-3, Black-12, and Black-17, the same set observed in the non-thinking Flash development comparison. Flash thinking reported 32 responses ending at the length cap. All five pipeline errors were JSON parsing failures in trials with a cap hit. Reasoning consumed part of the shared output budget, leaving insufficient content for the evaluator in those cases. The cap confounds the Flash thinking comparison. The diagnostic is inconclusive about the effect of thinking and too small to rank the models.

Raw records and finish reasons are listed in [CHECKSUMS](CHECKSUMS).
