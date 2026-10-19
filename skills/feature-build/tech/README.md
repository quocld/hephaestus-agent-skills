# Tech files

One file per technology, loaded by `feature-build` step 1b and `root-cause` section 1 only when the change touches that technology.
They are not skills on purpose: a skill's description costs every session, and knowledge skills often fail to load at the right moment, while these load from a deterministic signal in the repo.

## What a tech file contains, in order

1. `# <Technology>` and one or two lines on why the agent's defaults go wrong for it.
2. `## Before writing code`: how to read the installed version, where the docs for that version live (bundled in `node_modules`, `llms.txt`, `.md` pages), and which project files decide the rules (config, `main.ts`).
3. `## Traps`: only rules an agent gets wrong without being told, one line each with the reason when it is not obvious.
   Nothing the docs or the compiler already enforce, nothing version-specific that the docs step covers better.
4. `## Verify`: the checks this technology adds to `feature-build` step 6, if any.
5. `## Deeper, only when the task is in that area`: links to official long-form rules, fetched on demand, never copied in.

## Rules

- Keep each file under about 60 lines; when it grows, cut the weakest trap rather than adding a section.
- Security, UI states, environments, and deploys have owners (`security-pass`, `fe-guardrails`, `environments`); point to them, never restate them.
- Every trap comes from the technology's official docs or official agent skills, or from a failure seen in a real session; record new upstream sources in `SOURCES.md`.
- Adding a file: add its row to the signals table in `feature-build` step 1b, and run the `knowledge-placement` skill test with a scenario that should load it.
