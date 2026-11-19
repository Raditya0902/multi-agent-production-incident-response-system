# BugsInPy selection protocol

Set before inspecting individual candidates.

- Use public BugsInPy records for ordinary functional defects. Require an upstream buggy and fixed commit, a Python source regression, and a small fix confined to one production Python file. Screen for up to 35 added/deleted production lines.
- Prefer projects with simple offline test environments. Screen tqdm, PySnooper, cookiecutter, and Black first, in that order, with numeric BugsInPy IDs ascending within a project. If necessary, extend to other bundled projects in lexical order and record the extension.
- Require Python 3.11, deterministic tests, no external service or GPU, and a total validation duration under roughly two minutes per revision. Resolve dependencies before the offline test run.
- Require at least one pytest node that fails in the buggy source and passes in the fixed source, plus at least one different node from the same test file that passes in both. Keep the test oracle identical on both revisions, and use the fixed-revision test file when the buggy revision lacks the upstream regression.
- Exclude defects involving security boundaries, live services, or network calls that cannot be replaced by fixtures already supplied upstream. Exclude revisions with environment failures, non-test failures, divergent or unavailable test oracles, multiple production changes, out-of-scope paths, or flaky results.
- Record all screened candidates, including exclusions and reasons. Freeze 10–20 validated bugs before any model run. Stop screening at 15 validated bugs where feasible. Never replace a bug based on model performance.
- Pin the BugsInPy snapshot, both upstream source revisions, source and test paths, the failing and passing node IDs, and the validated Docker dependency environment. Give agents only diagnostic frames from the buggy revision. Keep the fixed source, oracle, expected outputs, and Git metadata outside agent inputs.

## Screening ledger

Dataset revision `11c5f1eea954a42132cfd06bf257766a7963e0fd`. The
final ordered screen stopped at the 15th eligible case. Both revisions
used the same upstream oracle from the fixed test tree. When the upstream
selector expanded into multiple nodes, only nodes that reproduced a
test-body failure became fail-to-pass targets. Pass-to-pass controls were
the first three common passes among the first eight other node IDs in
lexical order. An independent exact-node rerun confirmed each case.

| Project | Selected IDs | Excluded IDs and reason |
| --- | --- | --- |
| tqdm | 8, 9 | 1, 3, 4, 5, 6 call the removed `sys.setcheckinterval` in test setup. 2 changes two production files. 7 has no separate control in the test file. |
| PySnooper | 3 | 1 changes two production files. 2 changes six. |
| cookiecutter | 3 | 1's upstream target also passes on the buggy revision in this Linux environment. 2's tests write under the read-only checkout. 4 changes three production files. |
| Black | 4, 5, 7–14, 17 | 1 and 3 require a generated `_black_version` module and fail collection from the checkout. 2 and 15 exceed the production line limit. 6 changes multiple production files. 16 concerns a symlink outside the checkout and was excluded at screening. |

An environment trial reached Black 18–20 before the final dependency pins
and legacy pytest settings admitted additional earlier cases. Black 18
exceeded the line limit. Black 19 and 20 validated in the trial but fell
after the final ordered cutoff. Black 21–23 and the remaining BugsInPy
projects were outside that cutoff. No model output informed selection.

The [frozen manifests](manifests) pin the exact source commits, oracle
files, and test node IDs. The [validation record](validation.json) records
each verdict and the Docker image used. This sample is weighted toward
Black and small functional defects. Public bugs may appear in LLM
training data. [Pinned BugsInPy snapshot](https://github.com/soarsmu/BugsInPy/tree/11c5f1eea954a42132cfd06bf257766a7963e0fd)

## Reproduce the offline checks

From the incident-response repository with the app's Python dependencies installed:

```sh
repos="$(mktemp -d)"
git clone --bare https://github.com/tqdm/tqdm.git "$repos/tqdm.git"
git clone --bare https://github.com/cool-RR/PySnooper.git "$repos/PySnooper.git"
git clone --bare https://github.com/cookiecutter/cookiecutter.git "$repos/cookiecutter.git"
git clone --bare https://github.com/psf/black.git "$repos/black.git"
docker build -t incident-real-benchmark:stage-a tests/benchmark/real
python -m tests.benchmark.real.run_benchmark validate --repos "$repos"
```

The optional screening command takes a checkout of the pinned BugsInPy
snapshot, the same mirrors, and a new output directory.

```sh
python -m tests.benchmark.real.screen --dataset "$bugsinpy_checkout" --repos "$repos" --output "$screen_output"
```

The adapter archives each revision into a fresh workspace without Git
metadata. Only the candidate or revision, the test oracle, and the
pytest reporter are mounted in the network-disabled container. The
agent receives the failure class, available buggy production traceback
frames or observed production calls, a labeled synthetic complaint, and
coarse retry feedback. Model inputs exclude fixed source, test files,
test IDs, expected outputs, and raw assertions. Each model trial uses an
empty throwaway Chroma directory with no feedback writes.

The separate `run` mode uses auto-approval with a valid Groq key.
`--trials` defaults to three. `--bugs` and `--max` select from the frozen
list. Complete attempts are cached per bug and trial under
`tests/benchmark/results/real/`, keyed by the effective benchmark
configuration. After a provider interruption, the same command resumes
with the first missing trial.
