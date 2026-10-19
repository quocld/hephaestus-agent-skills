---
name: fe-guardrails
description: >
  Use before writing or reviewing React or Next.js code that fetches data, renders pickers, selects, or tables, submits forms, or shows errors, and when building or wiring a screen ("build màn", "wire API vào màn", "nối API").
user-invocable: false
---

# fe-guardrails

## Before building a screen

- **Search the repo first.** Many screens already exist (often on mock data with a "swap for the real API later" comment).
  `ls` the routes and grep the module name before concluding a screen or design is missing; the job is often to wire the API into an existing screen, not build a new one.
- Only when no route exists, get the design from the design source (e.g. Figma MCP); if it is unavailable, ask instead of inventing a layout.
- Match the design exactly.
  Deviate only where the spec requires it, and record each deviation and why.
  Do not "improve" existing UI without permission.
- **Shared components first.** Any repeated element (input, field, card, dialog, table, badge) lives in the shared UI folder; pages only compose.

## Loading, empty, and error states

- Every async UI has a loading state (spinner, skeleton, disabled while pending) and an empty-state placeholder.
- **Never `query.data ?? []` in a picker/select/table without an `isError` branch.**
  It collapses 200-empty, 403, and 500 into the same empty list with an enabled control, and the user never learns why.
  A read error stays on screen (inline alert or error section), not in a toast.
- A query with `enabled: false` is not pending; do not render "Loading..." forever.
- Disable submit while pending; a double click must not create two rows.

## Form errors: exactly three groups

1. **Message about one field** -> inline under that field, `aria-invalid` on the control, stays until the user edits that field.
   Includes client-side gates and backend rejections whose key maps to a field rendered on screen.
2. **Message not about any rendered field** -> one error toast (no key, unknown key, 403/404/409 without a field, 500, network).
   Split mixed rejections: field parts inline, the rest in the toast; never show the same sentence in both, never drop one.
3. **Action result** (Created/Updated/Deleted successfully) -> toast, never inline.

Rules:

- Map backend keys to field ids **only from evidence** (contracts, schemas, service code); never guess, never map to a conditionally rendered field.
  Unmappable messages go to the toast.
- **The data layer must keep the error body.**
  `throw new Error(messageOf(body))` flattens it before the form can see the keys, and every inline wiring above becomes dead code.
  Throw a typed error that carries `status` and `body`.
- Use the project's single error-parsing helper; never write a second parser or humanizer.
- Show the backend's message verbatim; write your own only when the backend sends none.
- Do not close a dialog on validation errors; never swallow a rejection with an empty `.catch()`.
- Multi-step wizards navigate to the step of the first error; long forms scroll the first error into view.
- Keep existing client-side validation conditions exactly; changing what is enforced is a spec change, so ask.
- `<Alert>`/banners remain for non-submit states (load errors, missing permission, static guidance); toasts disappear and cannot hold persistent state.
- Add a structural test that scans forms and fails when a new form neither uses the shared inline-error path nor is allowlisted with a reason.

## Copy

- Prefer the exact copy from the design or spec; the rules below apply only to copy you write yourself.
- Sentence case, plain English, no raw schema text ("Country must be 100 characters or fewer", not "String must contain at most 100 character(s)").
- Use the user's words, not system terms: "Notifications", not "Webhook config".
- An action keeps one name through the whole flow: a Publish button leads to a "Publish post?" dialog and a "Published" toast, never Submit, Save, or Done.
- An error you write states what happened and what to do next, and never apologizes ("Couldn't save the invoice. Check your connection and try again.", not "Oops, something went wrong").
- An empty state names the next action and offers it ("No clients yet" plus an "Add client" button), not just "No data".
- Avoid these AI tells in copy and layout:
  - em dashes and "Word - fragment" labels;
  - slop words (seamlessly, effortlessly, unlock, empower, elevate, streamline) and filler taglines that sell instead of explain;
  - meta strings joined by middle dots ("A · B · C");
  - an arrow appended to link or button text ("View all →");
  - all-caps labels and eyebrows.
