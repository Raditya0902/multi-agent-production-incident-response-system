# Final BugsInPy held-out comparison

Model `deepseek-flash`, thinking disabled, temperature 0.2, 4,096 output tokens, empty fallback. Pipeline commits `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` (v0) and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` (v1 without contracts). Recorded on 2026-11-20 UTC (November 19 in US Arizona).  Harness commit `6bcacdd8df143e63a9564f3e9940e69657ffd4b1`. Pool commit `1d95bb940bf13acc567767f2341187922ff2bedb`.

Both arms used the same Docker scorer and trace boundary. Each retained its frozen trace producer. A trial resolves when both fail-to-pass and pass-to-pass checks pass. The frozen scorer checks the expected file at application time. Target-file choice is a secondary diagnostic. No statistical improvement is established by this comparison. The Wilson intervals describe each arm's case rate and do not estimate the paired difference.

<!-- evaluation:held-out -->
| Metric | v0 | v1 without contracts |
| --- | --- | --- |
| Trial resolves | 3/36 (8.3%) | 7/36 (19.4%) |
| Distinct cases resolved | 1/12 (8.3%) | 3/12 (25.0%) |
| Case-level Wilson 95% interval | 1.5%–35.4% | 8.9%–53.2% |
<!-- /evaluation -->

| Metric | v0 | v1 without contracts |
|---|---:|---:|
| Average trial runtime | 18.7 s | 20.8 s |
| Median trial runtime | 18.4 s | 21.5 s |
| Arm wall time | 11.25 min | 12.49 min |
| Provider requests | 279 | 271 |
| Input tokens | 108,118 | 227,557 |
| Output tokens | 39,274 | 54,076 |
| Usage-derived spend | $0.072602 | $0.105727 |
| Guard charge | $0.072602 | $0.105727 |

A case counts as resolved for the interval and shipping rule if at least one of its three trials resolves.

## All 12 cases

| Case | v0 | v1 without contracts |
|---|---:|---:|
| fastapi-2 | 0/3 | 0/3 |
| luigi-16 | 0/3 | 0/3 |
| luigi-17 | 0/3 | 1/3 |
| luigi-18 | 0/3 | 0/3 |
| thefuck-22 | 3/3 | 3/3 |
| thefuck-23 | 0/3 | 3/3 |
| thefuck-24 | 0/3 | 0/3 |
| tornado-1 | 0/3 | 0/3 |
| tornado-2 | 0/3 | 0/3 |
| tornado-4 | 0/3 | 0/3 |
| youtube-dl-1 | 0/3 | 0/3 |
| youtube-dl-2 | 0/3 | 0/3 |

## By repository

| Repository | v0 trial resolves | v1 trial resolves | v0 cases resolved | v1 cases resolved |
|---|---:|---:|---:|---:|
| fastapi | 0/3 (0.0%) | 0/3 (0.0%) | 0/1 | 0/1 |
| luigi | 0/9 (0.0%) | 1/9 (11.1%) | 0/3 | 1/3 |
| thefuck | 3/9 (33.3%) | 6/9 (66.7%) | 1/3 | 2/3 |
| tornado | 0/9 (0.0%) | 0/9 (0.0%) | 0/3 | 0/3 |
| youtube-dl | 0/6 (0.0%) | 0/6 (0.0%) | 0/2 | 0/2 |

## Paired comparison

- v0 only resolved 0 cases (none).
- v1 only resolved 2 cases (luigi-17, thefuck-23).
- Both versions resolved 1 case (thefuck-22).
- Neither version resolved 9 cases (fastapi-2, luigi-16, luigi-18, thefuck-24, tornado-1, tornado-2, tornado-4, youtube-dl-1, youtube-dl-2).

| Case with different counts | v0 | v1 without contracts |
|---|---:|---:|
| luigi-17 | 0/3 | 1/3 |
| thefuck-23 | 0/3 | 3/3 |

## Terminal failures and reruns

| Category | v0 | v1 without contracts |
|---|---:|---:|
| Patch failed to apply | 3 | 10 |
| Wrong file | 30 | 14 |
| Wrong fix | 0 | 5 |
| Pass-to-pass regression | 0 | 0 |
| Test environment failure | 0 | 0 |
| Timeout | 0 | 0 |
| Pipeline error | 0 | 0 |
| Provider interruption | 0 | 0 |

No provider or infrastructure error required a trial rerun.

## Decision and spend

The pre-registered rule selects `bench-v1-nocontracts`. The v1 minus v0 margin is +2 distinct cases.

The held-out runs used 550 requests and cost $0.178329 from provider-reported token usage. The guard charged $0.178329. Cumulative guard charges were $2.730014 of the $3.60 cap, leaving $0.869986.

All 12 held-out cases come from repos outside the dev set. Five of the nine The Fuck, Tornado, and Luigi cases target files under 1,000 lines, and eight fall below the 3,511-line dev median. The Tornado targets include a 3,582-line file. Public fixes may be in the model's training data.
