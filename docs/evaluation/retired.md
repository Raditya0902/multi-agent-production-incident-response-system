# Retired synthetic results

The saved run is dated 2026-05-04 UTC. The historical documentation reported Groq model `llama-3.3-70b-versatile`, temperature 0.2 and a 4,096-output-token cap. The saved JSON did not capture the executed commit or effective provider settings. The historical reporting commit is `e6a1da7c237b8649edde7793a8e749754f9dd182`. The model is no longer available.

| Historical metric | Reported value | Meaning |
| --- | ---: | --- |
| Patch correctness | 100.0% (7/7) | The generated patch matched the expected strings |
| False-positive rate | 0.0% | No test pass disagreed with the string-match check under the old definition |
| Average runtime | 41.1 s | Mean elapsed time in the archived run |

The historical figures overstated what was established about correctness. String matching checked for expected text and the old evaluator could use a synthetic test fallback. The first three modern baseline rounds at `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` on 2026-11-19 UTC, with `deepseek-flash`, temperature 0.2 and a 4,096-token cap, each matched 7/7 patterns while resolving 2, 3 and 4 of 7 cases under behavioral scoring. That directly demonstrates why pattern agreement overstates behavioral success. Those were different generated patches. A behavioral score for the retired run cannot be recovered from the saved rows.

See the [synthetic disagreement matrix](synthetic.md) and [archived file hashes](CHECKSUMS).
