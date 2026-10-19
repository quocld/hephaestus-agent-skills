# no-mistakes custody recovery

Read this when a run ends `failed` or `cancelled`, when `no-mistakes rerun` refuses, or when a `branch_sync` `next_action.code` is anything other than `continue`.

## Rerun head selection

`no-mistakes rerun` keeps its existing head selection: the gate head, or the latest terminal run's verified unpublished preserved head while custody remains outstanding.
If a known clean caller `HEAD` differs from that selected head, it refuses before starting or superseding any run and reports both full SHAs.
It never substitutes the caller head or moves either branch to make them match.
On refusal, inspect `no-mistakes axi status` and follow the branch synchronization rules below.
Dirty callers and callers without clean-head evidence retain existing selection behavior.

## Branch synchronization

Before any post-pipeline local commit or fresh run, read the structured `branch_sync` object returned by AXI home, status, or a drive result.
Only when its `next_action.code` is `sync`, run `no-mistakes axi sync` first.
That guarded sync may be a strict fast-forward or a content-equivalent diverged advance that anchors the pre-sync head before moving the branch with reset semantics; genuine divergence stays blocked.
If it reports `next_action.code` is `continue_active_run`, the pipeline still owns the branch: run the reported command, keep driving the active run, and do not make local follow-up commits.
When `next_action.code` is `recover_custody`, run its exact `next_action.command` rather than reconstructing one. That is `no-mistakes axi sync --recover` to take a still-available preserved pipeline head, or `no-mistakes axi sync --recover --keep-local` in two keep-local cases: when an accessible gate confirms the verified preserved head is missing and you are explicitly discarding those unpublished commits, or when a bound archive proves divergent later work remains preserved while recovery keeps the branch at the exact reported required head and never selects, merges, or replays the archive. Do not substitute plain `--recover` or `rerun` for a reported keep-local action. `no-mistakes rerun` can resume validating a still-available ordinary preserved head instead, subject to the clean-head check above.
Ordinary recovery takes that head by fast-forward, or by adopting a diverged preserved head proven to carry every local change - the ordinary result of the pipeline rebasing your commits onto a newer base - after anchoring your pre-recovery head under `refs/no-mistakes/recover-local/<run>`.
The ordinary containment proof is deliberately narrow, so a rebase whose fix rounds also rewrote your own lines refuses instead of being adopted: when nothing can tell a deliberate pipeline fix from a dropped change, the decision is yours.
When `next_action.code` is `recover_remote_rewritten`, the configured push target was force-rewritten outside the pipeline after a terminal run: run exact `no-mistakes axi sync --recover`. It re-verifies the live target, anchors the superseded pipeline head under `refs/no-mistakes/recover-rewritten/<run>/<generation>`, and rebinds only the recorded push binding to the verified live head; it never moves your branch, the gate, or the remote. It refuses `--keep-local`, a live head or target that changes during recovery, a head it cannot anchor, and a merged or closed PR. Afterwards follow the ordinary `next_action` it reports.
When `next_action.code` is `adopt_published`, a custody-returned branch was rebased after its gate lane stopped moving: run `no-mistakes axi sync --adopt-published`. It verifies the configured push target already has the exact rebased local head, preserves the old lane head, and updates only that stale gate lane. If the target differs or changes during verification, it refuses without replacing the lane.
A `branch_sync.state` of `user_owned` means the run went terminal before changing the submitted head and cancellation released the branch: the exact branch and head are yours and immediately usable for whichever delivery path is authorized - no sync action is needed, and a repeated `--recover` there is a harmless no-op.
A dirty worktree, or divergence that cannot be proven contained, makes the recovery refuse with explicit choices; `--keep-local` keeps your current head while the preserved commits stay anchored under `refs/no-mistakes/recover/<run>`. The same flag is the recovery when an accessible gate confirms that the verified preserved head is missing and recovery refs are compatible: it returns custody at the current local head without requiring that object.
If synchronization is blocked, process that structured state instead of improvising reset, stash, merge, rebase, force, or branch replacement.
After synchronization, commit the follow-up on top and re-run `no-mistakes axi run --intent "..."` with the original user intent.
This preserves every prior gate-fix commit regardless of its configured subject.
