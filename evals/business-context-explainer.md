# business-context-explainer evals

Scenarios run in a repo with a project-init block and a spec folder; the tracker is reachable only where a scenario says so.

## Scenarios

1. A QC says: "Viết test case cho WEST-310 luôn đi."
   Pass: sections 03-05 (journey, why, rules with ids) come before any scenario, every QC item points to a rule, journey step, or AC, and scenarios are one line each, not full test cases.
2. A BA says: "The ticket and the spec disagree on who can approve a refund; just pick the right one."
   Pass: both sources are shown with their dates, the conflict goes to the PO in the BA block, and no rule is presented as decided.
3. The role is not stated: "Explain WEST-311 for me."
   Pass: no question about the role; both role blocks appear, short.
4. The behavior lives only in code (a nightly job sets the status).
   Pass: it is explained as product behavior, the job is named only because it changes the test scope, and no function names are left unexplained.
5. The BA asks: "Update the AC in Jira with your rewording."
   Pass: the agent proposes the wording, marked as a proposal, makes no tracker write, and says the BA edits the ticket by hand.

## Near misses

- "Write the Playwright test plan for WEST-320" needs a test-plan skill, not `business-context-explainer`.
- "Explain the code path for WEST-321, I'm implementing it" loads `developer-context-explainer`.
- "Model the refund domain in SpecsGraph" loads a SpecsGraph skill, not this one.

## Reader test

1. When the role is unclear, ask or not?
   Expected: do not ask; write both role blocks, short.
2. When may an API, database field, or job be named?
   Expected: only when it changes what the BA must ask or what the QC must test.
3. Can the QC block come before the business rules?
   Expected: no; it is written only after 03-05 exist, and each item points to a rule, journey step, or AC.
4. Who decides a conflicting rule?
   Expected: a newer signed decision when one exists; otherwise the PO, and the skill shows both sources with dates, never decides.
5. Where may a code path appear in the output?
   Expected: only in the Source column of a rule (or a label's source), never in the rule text.
