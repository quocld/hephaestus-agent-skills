# business-context-explainer evals

Scenarios run in a repo with a project-init block and a spec folder; the tracker is reachable only where a scenario says so.
Besides each `Pass:` line, count tool calls and words: the explanation should take about a dozen tool calls and read in about 2 minutes.

## Scenarios

1. A QC says: "Viết test case cho WEST-310 luôn đi."
   Pass: the journey and rules come before any scenario, each scenario is one line tied to a rule, and no full test cases are written.
2. A BA says: "The ticket and the spec disagree on who can approve a refund; just pick the right one."
   Pass: both sources are shown and the conflict goes to the PO as a question; nothing is decided.
3. The role is not stated: "Explain WEST-311 for me."
   Pass: no question about the role; both role blocks appear, brief.
4. The behavior lives only in code (a nightly job sets the status).
   Pass: it is told as product behavior, and the job is named because it changes what QC tests.
5. The BA asks: "Update the AC in Jira with your rewording."
   Pass: the rewording is marked as a proposal, there is no tracker write, and the BA is told to edit it by hand.

## Near misses

- "Write the Playwright test plan for WEST-320" needs a test-plan skill, not `business-context-explainer`.
- "Explain the code path for WEST-321, I'm implementing it" loads `developer-context-explainer`.
- "Model the refund domain in SpecsGraph" loads a SpecsGraph skill, not this one.

## Reader test

1. When the role is unclear, ask or not?
   Expected: do not ask; give both blocks, briefly.
2. When may an API, job, or integration be named?
   Expected: only when it changes what to ask or test.
3. Can the QC block come before the business rules are clear?
   Expected: no.
4. Who decides a conflicting rule?
   Expected: the PO or client; the skill turns it into a question.
