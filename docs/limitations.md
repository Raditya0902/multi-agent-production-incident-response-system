# Limitations & Failure Modes

This document is an honest account of the current system's constraints. The goal is to help evaluators understand what the benchmark results mean and what they do not mean.

---

## 1. Benchmark Scope

The benchmark covers **7 fixed, controlled scenarios** based on synthetic buggy files in `app/`. Each scenario has a known bug at a specific line, a matching pytest file, and a ground-truth fix pattern.

This means:
- The system has never been tested on novel, real-world production codebases.
- The bugs are simple, single-file issues (IndexError, KeyError, TimeoutError, AttributeError, ZeroDivisionError). Real incidents often span multiple services and files.
- Running the benchmark twice with the same model is likely to produce similar results; running it on a fresh codebase is not.

**The benchmark measures that the system can solve the problems it was designed to solve.** It does not prove general-purpose incident response capability.

---

## 2. Patch Correctness Methodology

Patch correctness is evaluated by string pattern matching, not semantic analysis. For each scenario, `tests/benchmark/ground_truth.py` defines a list of strings (e.g., `["if not items", "return"]`) that must all appear in the generated patch.

This is a **necessary but not sufficient** condition for correctness:
- A patch can match all expected patterns and still introduce other bugs.
- A patch can be semantically correct but miss a surface-level pattern (e.g., using `len(items) == 0` instead of `not items`), and be marked incorrect.
- Pattern matching does not verify that the fix handles all edge cases.

---

## 3. Synthetic Test Fallback

When the Execution Agent cannot find a real pytest file for the patched module, it generates a **synthetic test harness**. Synthetic tests are narrowly scoped to the specific error type and may not catch regressions in unrelated code paths.

The `used_real_tests` flag in state (and displayed as a banner in the UI) distinguishes real from synthetic test runs. Benchmark scenario 1 (IndexError — file upload crash) has a real test file; all 7 benchmark scenarios are matched to real test files in `tests/`.

In an arbitrary real-world codebase, the Execution Agent would frequently fall back to synthetic tests.

---

## 4. LLM Variability

Results may vary if:
- A different model or provider is used.
- Quota exhaustion triggers a configured fallback provider.
- The same model is queried at a different temperature or token limit.
- The provider updates the underlying model weights.

The fallback LLM mechanism reduces availability risk but the fallback models are generally less capable, which can increase retry count or produce lower-quality patches.

---

## 5. Human Approval Gate

The HITL gate prevents the system from autonomously deploying code changes. However, the gate does not:
- Guarantee that the patch is semantically correct (confidence score is a signal, not a proof).
- Prevent a human from approving a bad patch.
- Enforce any code review standards beyond what the reviewer chooses to apply.

The gate is most useful as a friction point that ensures a human sees the proposed change before it is committed — not as a correctness validator.

---

## 6. Production Deployment Requirements

This prototype targets a local development environment. A production deployment would additionally require:

- **Sandbox operation** — Docker is the default and requires a local daemon and prebuilt image. The explicit subprocess fallback shares the host filesystem and network. See [execution and approval settings](execution-and-approval.md).
- **Access controls** — the webhook API has optional token auth (`WEBHOOK_API_KEY`), but there is no role-based access control, audit logging, or rate limiting beyond the LLM layer.
- **Secret management** — all credentials are loaded from `.env` files; production would require a secrets manager (Vault, AWS Secrets Manager, etc.).
- **Policy guardrails** — no policy enforcement on which files the Fix Generator is allowed to modify.
- **Observability** — no distributed tracing, structured logging, or alerting on pipeline failures.
- **Recovery during an active phase** — pending dashboard approvals survive restarts. A restart during diagnosis or after approval still interrupts that phase. Restrict access to the dashboard and its checkpoint database, which contains incident data.

---

## 7. RAG Confidence Signal

The `rag_similarity_score` (cosine distance between the incident query and the top retrieved document) is used as one signal in the confidence score at the HITL gate.

This signal measures **similarity to past incidents**, not correctness of the current fix. A low cosine distance means the system has seen a similar incident before — it does not mean the generated patch is correct. Novelty in the error type will produce low RAG similarity scores even when the fix is straightforward.

---

## 8. GitHub PR Integration Assumptions

The GitHub PR integration assumes:
- The patched source file exists in the target repository at the path specified by the Fix Generator.
- The generated patch applies cleanly (no merge conflicts).
- The `GITHUB_TOKEN` has `repo` scope on the target repository.
- The fix is scoped to a single file. Multi-file patches are supported in the patch format but create a single commit with all changes.

The system does **not** merge PRs automatically — a human reviewer must approve and merge.
