# Offline wrong-file re-score

Offline replay on 2026-11-19, dated from the saved artifact. No model was called in the replay, so model ID, temperature and output cap are inapplicable to the replay itself. The saved patches were generated with `deepseek-flash`, thinking disabled, temperature 0.2, a 4,096-token cap and empty fallback.

| Source arm | Git commit |
| --- | --- |
| v0 | `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` |
| Full v1 | `4e811f00806c2c2a64364a0f0aa5efa4aa5444e3` |
| v1 without contracts | `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` |

The replay allowed a saved terminal patch to target a different eligible source file in a fresh buggy checkout. It retained the exact anchor, syntax, containment and protected-path requirements, and used the original Docker evaluator tests. Official scores and scorer code were untouched.

| Arm | Terminal wrong-file trials | Failed to apply | Applied and tested | Fail-to-pass passed | Pass-to-pass passed | Passed both | Existing resolves flipped | Protected-path changes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v0 | 9 | 7 | 2 | 0 | 1 | 0 | 0 | 0 |
| Full v1 | 19 | 8 | 11 | 0 | 11 | 0 | 0 | 0 |
| v1 without contracts | 19 | 15 | 4 | 0 | 2 | 0 | 0 | 0 |
| Total | 47 | 30 | 17 | 0 | 14 | 0 | 0 | 0 |

The rejected target check did not mask a test-passing fix in these saved candidates. None modified tests or other protected paths. This replay says nothing about whether a different candidate could fix a bug from another file. The raw `v2/offline-rescore.json` record and replay script are listed in [CHECKSUMS](CHECKSUMS).
