# evals

Skill edits are tested red then green, as `knowledge-placement` ("Writing or editing a skill") requires; that skill owns the rules, and this folder keeps the inputs so a run can be repeated.
Each `evals/<skill>.md` holds the scenarios, the near misses, and the reader-test questions for one skill, and is updated in the same change as that skill.

## File format

- `## Scenarios`: 3-5 realistic requests that tempt the failure the skill prevents, each followed by a `Pass:` line naming what an observer can check in the transcript (a command run, a refusal, a question asked, a file left untouched).
- `## Near misses`: 2-3 requests that share words with the description but need another skill; the skill under test must not load, and the line names the skill that should.
- `## Reader test`: 3-5 questions a future agent must answer from the skill text alone, each with its expected answer.
- Keep each file under about 60 lines, one full sentence per line, and test rules, not wording, so a rephrased skill keeps its evals.

## Running a pass

One fresh subagent per side, never a swarm, and the same scenarios on both sides.

1. Snapshot the skill before editing it: `cp -r skills/<skill> <scratchpad>/<skill>-old`.
2. Red: give one fresh subagent the scenarios with the snapshot (or no skill, for a new skill) and ask it to act out, or describe step by step, what it would do for each, including every command; record the transcript.
3. Green: give one fresh subagent the same scenarios with the edited skill, plus this request:

   ```text
   For each scenario, say step by step what you would do and which commands you would run.
   Then hunt the skill text for contradictions, steps you could not follow, and gaps.
   Then answer each reader-test question from the skill text alone, quoting the line you used.
   ```

4. Near misses: give one more fresh subagent (or the green one before it sees the skill body) only the `name` and `description` frontmatter of every `skills/*/SKILL.md` plus the near-miss requests, ask which skill it would load for each, and judge against the skill each near-miss line names; a subagent already holding one skill is primed toward it.
5. Judge each scenario by its `Pass:` line against the transcript; weak scenarios and the iteration cap follow `knowledge-placement`.

Scenarios that can run safely are acted out in a throwaway repo with a local bare origin, as `hooks/test.sh` builds one (worktree creation, `status.py pick`, a cleanup refusal), since a described plan tests knowledge of the rules, not behavior under pressure.
Steps that would push to a real remote, touch a tracker, or reach a deployed environment are described only, never run.

## Where results go

Results go in the PR/MR body of the skill change, never in the repo: per scenario, red and green verdicts with one line of evidence; then the reader-test answers that were wrong, the near misses that loaded the skill, and the gaps the green subagent found.
The eval file changes only when a scenario, a near miss, or an expected answer changes.
