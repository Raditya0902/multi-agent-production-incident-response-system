# Limitations

## Evidence and generalization

The synthetic suite covers seven fixed scenarios. BugsInPy contributes 15 development bugs and 12 held-out cases. Black accounts for 11 of the 15 development bugs. The held-out repos are outside development, but the sample leans toward small files. Five of the nine The Fuck, Tornado, and Luigi cases target files under 1,000 lines. Public fixes may appear in the model's training data. Pinned revisions and hidden oracles control what the harness exposes at runtime. [Synthetic suite](evaluation/synthetic.md) · [Development set](evaluation/development.md) · [Held-out report](evaluation/held-out.md) · [Selection](evaluation/selection.md)

The primary comparison used one configuration of `deepseek-flash`. The held-out distinct case counts were 3/12 for v1 without contracts and 1/12 for v0. The case-level Wilson intervals are wide, and the observed difference is not statistically established. The small dev-only thinking diagnostic exhausted its 4,096-token cap in some responses and cannot establish whether thinking improves repairs. [Held-out uncertainty](evaluation/held-out.md) · [Model diagnostic](evaluation/model-sensitivity.md)

## What counts as a fix

BugsInPy counts a resolve only when a fail-to-pass target passes and pass-to-pass controls still pass. The synthetic suite requires its service and private behavioral tests. These are finite test oracles. Multi-file fixes were not evaluated, and a passing patch can still have defects outside the tested behavior. The retired string-match metric overstated the behavioral evidence. [Scoring and controls](evaluation/selection.md) · [Retired results](evaluation/retired.md)

## Localization and retries

In v1 without contracts, 17 of 19 terminal wrong-file development trials were classified wrong-file on every attempt. In 15 of those 19, the expected file was absent from the source windows. A retry can regenerate a patch, but generic failure feedback rarely provided the missing localization information. Wider fixed windows and retry diversification did not clear the v2 acceptance bar. [Development diagnostics](evaluation/development.md) · [Ablations](evaluation/ablations.md) · [Offline replay](evaluation/offline-rescore.md)

## Runtime boundaries

The dashboard restores a pending approval by run ID. Restarting during diagnosis or after approval interrupts that phase. The API and benchmark paths bypass the dashboard approval gate. The benchmark does not send notifications or create pull requests. The dashboard can open a proposed pull request when configured. A human is responsible for reviewing and merging it.

The local default uses a disposable Docker sandbox for each execution. Subprocess mode creates a temp copy and applies a timeout, but candidate code can reach files and the network available to its process. Compose adds a service-container boundary and uses subprocess mode within it. Run the controller on the Docker host when a per-run sandbox is needed. Limit access to the dashboard and checkpoint database because they contain incident data. [Execution and approval settings](execution-and-approval.md)

## Future work

Evaluate agentic repo exploration for localization, where the agent can inspect related source before choosing a patch target. Use a larger held-out set with more projects, file sizes and defect types. Multi-file repair evaluation requires a separate contract.
