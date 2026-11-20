# Synthetic regression suite

Model `deepseek-flash`, thinking disabled, temperature 0.2, 4,096 output tokens, empty fallback. Pipeline commits `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` (v0) and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf` (v1 without contracts). Runs were recorded on 2026-11-19 UTC.

Seven scenarios were run in five rounds per arm. A trial resolves only when the service and private held-out behavioral pytest contracts pass. The synthetic suite keeps these as two behavioral groups rather than separate BugsInPy fail-to-pass and pass-to-pass node lists. A missing oracle or evaluator failure is invalid and unscored, with all requested trials retained in the denominator. The scorer checks the expected target before testing. Target choice and legacy string-pattern agreement are reported separately from test success.

<!-- evaluation:synthetic -->
| Metric | v0 | v1 without contracts |
| --- | --- | --- |
| Trial resolves (mean) | 15/35 (42.9%) | 13/35 (37.1%) |
| Resolves by round | 2/7, 3/7, 4/7, 3/7, 3/7 | 3/7, 2/7, 2/7, 4/7, 2/7 |
| Round resolve-rate range | 28.6%–57.1% | 28.6%–57.1% |
| Invalid trials | 0 | 0 |
<!-- /evaluation -->

## Per scenario

| Scenario | v0 resolves | v1 without contracts resolves |
| --- | --- | --- |
| IndexError — file upload crash | 0/5 | 0/5 |
| KeyError — payment failure | 3/5 | 2/5 |
| TimeoutError — DB pool exhausted | 0/5 | 1/5 |
| AttributeError — NoneType on user | 5/5 | 5/5 |
| Mass outage — api_gateway KeyError | 4/5 | 0/5 |
| ZeroDivisionError — analytics | 3/5 | 5/5 |
| IndexError — order validation | 0/5 | 0/5 |

## Behavioral tests × pattern matching

| Final verdict | v0 | v1 without contracts |
| --- | --- | --- |
| Pass and match | 14 | 13 |
| Pass only | 1 | 0 |
| Match only | 20 | 19 |
| Neither | 0 | 3 |

The first three v0 rounds each matched the old string patterns on 7/7 scenarios. Their behavioral resolutions were 2/7, 3/7, and 4/7. The five-round summary above includes the two later baseline rounds at the same commit.
