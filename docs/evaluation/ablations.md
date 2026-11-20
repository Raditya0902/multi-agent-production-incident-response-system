# Development ablations

Model `deepseek-flash`, thinking disabled, temperature 0.2, 4,096 output tokens, empty fallback.  Each row gives the pipeline commit. Measurements were recorded on 2026-11-19 UTC. Rows use the frozen 15-bug development set (three rounds) and seven-scenario synthetic suite (five rounds). Deltas are percentage points. Observed differences also include model variation.

## Incremental v1
| Variant | Pipeline commit | Dev mean | Distinct dev | Dev Δ | Synthetic mean | Synthetic Δ | Synthetic rounds | Usage-derived USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Frozen baseline | `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` | 6/45 (13.3%) | 2/15 | — | 15/35 (42.9%) | — | 2/7, 3/7, 4/7, 3/7, 3/7 | $0.089410704 |
| Exact source windows and anchor feedback | `06f33504fcb74eb93155c74cd5d1c264982270f7` | 6/45 (13.3%) | 2/15 | +0.0 pp | 22/35 (62.9%) | +20.0 pp | 4/7, 5/7, 4/7, 4/7, 5/7 | $0.100091106 |
| Function contracts and verdict counts | `2ed5cf9b20884f55f0b2df1fbec03b815de2fcb1` | 7/45 (15.6%) | 3/15 | +2.2 pp | 11/35 (31.4%) | -31.4 pp | 2/7, 2/7, 3/7, 2/7, 2/7 | $0.099748620 |
| Call-path localization | `3276f3013c48093fd27576f5337900b4f71d2ba5` | 9/45 (20.0%) | 3/15 | +4.4 pp | 12/35 (34.3%) | +2.9 pp | 3/7, 2/7, 2/7, 2/7, 3/7 | $0.117760281 |
| Container path normalization and allowlist | `0a363b69119ca4bb640aeefd5abe269a9915e420` | 9/45 (20.0%) | 3/15 | +0.0 pp | 12/35 (34.3%) | +0.0 pp | 2/7, 3/7, 3/7, 2/7, 2/7 | $0.112818798 |
| Per-attempt diagnostics | `4e811f00806c2c2a64364a0f0aa5efa4aa5444e3` | 9/45 (20.0%) | 3/15 | +0.0 pp | 11/35 (31.4%) | -2.9 pp | 2/7, 2/7, 2/7, 2/7, 3/7 | $0.112640826 |

Exact windows reduced development apply failures from 25 to 15 and increased wrong fixes from 5 to 15, with development resolutions unchanged at 6/45. Adding contracts and coarse verdict counts then reduced the synthetic result from 22/35 to 11/35. The prompt change replaced some concrete evaluator feedback with counts and presented static descriptions of buggy behavior as contracts. Either could have disadvantaged this suite. This sequential comparison does not isolate those two changes.

## Leave-one-out

Deltas use full v1 as the reference. The rule required at least the v0 synthetic mean of 15/35 before ranking candidates by distinct development bugs. No v1 variant cleared that rule. The later held-out shipping comparison followed its own pre-registered rule.

| Variant | Pipeline commit | Dev mean | Distinct dev | Dev Δ | Synthetic mean | Synthetic Δ | Synthetic rounds | Usage-derived USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full v1 | `4e811f00806c2c2a64364a0f0aa5efa4aa5444e3` | 9/45 (20.0%) | 3/15 | — | 11/35 (31.4%) | — | 2/7, 2/7, 2/7, 2/7, 3/7 | $0.112640826 |
| Without contracts | `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` | 9/45 (20.0%) | 3/15 | +0.0 pp | 13/35 (37.1%) | +5.7 pp | 3/7, 2/7, 2/7, 4/7, 2/7 | $0.100966152 |
| Without call-path localization | `9b5b1971544dd26fcfa93806fdf9b7dae126485f` | 6/45 (13.3%) | 2/15 | -6.7 pp | 10/35 (28.6%) | -2.9 pp | 2/7, 2/7, 2/7, 2/7, 2/7 | $0.098353158 |

## v2

Deltas use the preceding row. Neither change increased distinct development resolutions. The final variant resolved 3 distinct development bugs and 10/35 synthetic trials, below both pre-registered requirements of 5 distinct bugs and 15/35 synthetic trials. v2 stayed off the default branch and was not tested on the held-out set.

| Variant | Pipeline commit | Dev mean | Distinct dev | Dev Δ | Synthetic mean | Synthetic Δ | Synthetic rounds | Usage-derived USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 without contracts | `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` | 9/45 (20.0%) | 3/15 | — | 13/35 (37.1%) | — | 3/7, 2/7, 2/7, 4/7, 2/7 | $0.100966152 |
| Provide top-three source windows | `ecfe8dd27fbb6b2015f4bceb803b55ead8ec8447` | 9/45 (20.0%) | 3/15 | +0.0 pp | 13/35 (37.1%) | +0.0 pp | 2/7, 2/7, 3/7, 3/7, 3/7 | $0.116365182 |
| Also diversify retry file choice | `50b163bf3e1c39e0c73b673e0e81ed9f48890b67` | 9/45 (20.0%) | 3/15 | +0.0 pp | 10/35 (28.6%) | -8.6 pp | 2/7, 2/7, 2/7, 2/7, 2/7 | $0.107881941 |
