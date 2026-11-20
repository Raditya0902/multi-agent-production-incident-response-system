# BugsInPy development set

Model `deepseek-flash`, thinking disabled, temperature 0.2, 4,096 output tokens, empty fallback. Pipeline commits `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` (v0) and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` (v1 without contracts). The full v1 diagnostic arm was `4e811f00806c2c2a64364a0f0aa5efa4aa5444e3` under the same settings. Runs were recorded on 2026-11-19 UTC.

The frozen set has 15 bugs. Black contributes 11, tqdm two, and PySnooper and cookiecutter one each. A trial resolves when the fail-to-pass target and pass-to-pass controls pass. The frozen scorer checks the expected file before running tests. File choice is a secondary diagnostic here. A distinct bug resolves if any trial resolves. Mean is per trial across all 45 case-trials. The range is across the three full-set rounds.

<!-- evaluation:development -->
| Metric | v0 | v1 without contracts |
| --- | --- | --- |
| Trial resolves (mean) | 6/45 (13.3%) | 9/45 (20.0%) |
| Distinct bugs resolved | 2/15 | 3/15 |
| Resolves by round | 2/15, 2/15, 2/15 | 3/15, 3/15, 3/15 |
| Round resolve-rate range | 13.3%–13.3% | 20.0%–20.0% |
<!-- /evaluation -->

## Per bug

| Bug | v0 resolves | v1 without contracts resolves | Full v1 resolves |
| --- | --- | --- | --- |
| tqdm-8 | 0/3 | 0/3 | 0/3 |
| tqdm-9 | 0/3 | 0/3 | 0/3 |
| PySnooper-3 | 0/3 | 3/3 | 3/3 |
| cookiecutter-3 | 0/3 | 0/3 | 0/3 |
| black-4 | 0/3 | 0/3 | 0/3 |
| black-5 | 0/3 | 0/3 | 0/3 |
| black-7 | 0/3 | 0/3 | 0/3 |
| black-8 | 0/3 | 0/3 | 0/3 |
| black-9 | 0/3 | 0/3 | 0/3 |
| black-10 | 0/3 | 0/3 | 0/3 |
| black-11 | 0/3 | 0/3 | 0/3 |
| black-12 | 3/3 | 3/3 | 3/3 |
| black-13 | 0/3 | 0/3 | 0/3 |
| black-14 | 0/3 | 0/3 | 0/3 |
| black-17 | 3/3 | 3/3 | 3/3 |

## Terminal failures and localization

| Failure | v0 | v1 without contracts | Full v1 |
| --- | --- | --- | --- |
| Patch failed to apply | 25 | 8 | 8 |
| Wrong file | 9 | 19 | 19 |
| Wrong fix | 5 | 9 | 9 |
| Pass-to-pass regression | 0 | 0 | 0 |

In v1 without contracts, all 19 terminal wrong-file trials used all three attempts. Every attempt was classified wrong-file in 17 of those trials. The expected file was absent from the provided source windows in 15 of 19. In full v1 it was absent in 15 of 19. In the v0 first-trial failure diagnosis, the trace omitted the expected dependency file for Black-10 and Black-13. PySnooper-3 included the correct file alongside the intermediate file selected by the model. Retry feedback reported a wrong file without adding the missing source. These observations support localization as a bottleneck on this set.

Raw evidence is indexed in [CHECKSUMS](CHECKSUMS). See the [selection protocol](../../tests/benchmark/real/SELECTION.md) and the [test-only replay](offline-rescore.md).
