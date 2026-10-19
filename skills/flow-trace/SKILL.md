---
name: flow-trace
description: >
  Use before calling done any change that alters how a status or state machine moves (writes, transitions, guards on it), a webhook or external event, a scheduled job, money, or an access gate, or when asked to "trace luồng", "rà luồng", "check this flow end to end".
user-invocable: true
---

# flow-trace

This is methodical code reading, not a test runner.
It exists because a green pipeline routinely ships bugs like this one: a payment provider retried a failed invoice and it succeeded with the same invoice id, an `ON CONFLICT DO NOTHING` swallowed it, and the customer paid but stayed locked out forever, with 35 passing tests.

## 0. Scope the flow

One flow = the lifecycle of one entity, from creation to every terminal state.
Not one endpoint, not one screen.
Examples: account (signup -> verify -> trial -> charge -> renew -> expire -> recover), order, payment, invoice.

Before reading code, write down every state of the flow and every event that changes it: user actions, webhooks, scheduled jobs, admin actions.

## 1. State table: find one-way doors

Build the product of all related status fields (e.g. `account.status` x `subscription.status`).
For every reachable cell, answer all four:

| Question | Cannot answer = finding |
| --- | --- |
| (a) How do you get in? | orphan state, or a missing guard |
| (b) What screen does the user see? | no screen = blank page |
| (c) What can the user do there? | nothing = dead end |
| (d) How do you get out? | no way out = one-way door, severe |

Red flags: a guard that checks one status while several are valid (`status === 'active'` forgetting `past_due` or `trialing`); a "fix your problem" screen that requires the very status the user just left.

## 2. External events: list ALL of them, not just the handled ones

For every integration (payments, email, storage, queues, third-party APIs):

- Open the provider's event list and diff it against the current `switch`/handler.
  For every unhandled event, answer: which state pair does the system get stuck in?
- Every `ignored`, `return null`, or empty `catch {}` is a finding until proven harmless; write the reason it is harmless as a comment at that line.
- Events arrive out of order and more than once.
  For every opposing pair (paid/failed, created/deleted), ask: what if they are reversed? Repeated?

## 3. Idempotency: tell "repeat" apart from "real transition"

Dedup guards (`ON CONFLICT DO NOTHING`, `WHERE status = 'pending'`, unique keys) always misfire when the same key legitimately passes through several states.
For each guard, write the real sequence and check all three lines:

```text
same key, same outcome      -> must NO-OP          (dedup)
same key, FORWARD outcome   -> must APPLY          (the usual bug)
same key, BACKWARD outcome  -> must IGNORE         (late webhook must not regress state)
```

If you cannot write all three lines for a guard, the trace is not done.

## 4. Absolute URLs and host identity

For every URL built on the backend (redirects, callbacks, email links, checkout success URLs, presigned URLs), ask: which host is the recipient on?
In multi-tenant subdomain setups, a global `APP_URL`/`WEB_ORIGIN` is almost always wrong; use the project's per-tenant origin helper instead of concatenating a new string.

## 5. End-of-flow screens: where users rescue themselves

For every blocked state, open the exact screen the user lands on:

- At least one action leads out; otherwise it is a dead end.
- The data the screen shows has a read endpoint.
  An empty state with no endpoint behind it is a gap to report, not a valid empty state.
- Returning from an external redirect (`?status=success`) before the webhook arrives: what does the screen say, and what happens when polling gives up?
- Common FE traps: see the `fe-guardrails` skill.

## 6. Tenant and permission scope

For every privileged or cross-tenant query in the flow: is the WHERE clause scoped to exactly one tenant?
Does every table the flow touches have a tenant column and an access policy?

## Output

Write `docs/flow-traces/<flow>-<YYYY-MM-DD>.md` (or the project's equivalent).
Every finding needs all four parts, otherwise it is a feeling, not a finding:

```text
### F1 <title>
where       file:line + the exact deciding line quoted
trigger     the concrete state/event sequence
impact      what happens to the user or the money
class       matches spec (fix now) | deviates from spec (ask, see ask-or-decide) | needs product/BA
```

Then:

- Findings that match the spec: fix them and write a reproduction test that runs the whole sequence in ONE test (`failed -> retry -> paid`), not three separate single-event tests.
- Findings that deviate from the spec or add a new rule: do not decide alone; escalate per `ask-or-decide`.
- Record the trace date so the next person knows what was already covered.
