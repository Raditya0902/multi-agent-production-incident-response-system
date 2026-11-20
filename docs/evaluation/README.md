# Evaluation evidence

The primary comparison used `deepseek-flash`, thinking disabled, temperature 0.2, a 4,096-output-token cap, and empty fallback. The frozen pipeline commits are `8fbc67e2adb4a68b05957d4588aaffcd0c21c030` and `7ca80de7a81d7d2fe88ef4f531105d2e158e69bf`. Development and synthetic measurements were recorded on 2026-11-19 UTC. The held-out comparison was recorded on 2026-11-20 UTC with shared harness `6bcacdd8df143e63a9564f3e9940e69657ffd4b1`.

- [Synthetic regression suite](synthetic.md)
- [BugsInPy development set and per-bug results](development.md)
- [Final held-out report](held-out.md)
- [Incremental v1, leave-one-out, and v2 ablations](ablations.md)
- [Development-only model-sensitivity diagnostic](model-sensitivity.md)
- [Offline wrong-file re-score](offline-rescore.md)
- [Token usage and spend](spend.md)
- [Frozen selection, leak controls, and shared trace boundary](selection.md)
- [Retired string-match results](retired.md)
- [Reproduction and archive verification](reproduce.md)
- [Raw artifact checksums](CHECKSUMS)

The Markdown reports retain measured aggregates. Raw patch results, logs, run caches, launchers, and SQLite ledgers remain in the private archive. The README result tables are mechanically checked against marked tables in the suite reports.
