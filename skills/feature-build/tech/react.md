# React

React 19 changed refs, forms, and data loading, and the React Compiler changes whether manual memoization is wanted at all, so the version and the compiler decide the rules.
Loading, empty, error, and form states belong to `fe-guardrails`; this file covers the component code itself.

## Before writing code

1. Version: the lockfile entry for `react`, or `pnpm list react` (the repo's package manager) after install.
2. React Compiler on? `babel-plugin-react-compiler` in `package.json`, or `reactCompiler` in `next.config.*`.
3. Read how the project already fetches data (TanStack Query, SWR, server components, loaders) and copy that; never add a second way.
4. Docs: the page's `.md` URL on react.dev (`https://react.dev/reference/react/useActionState.md`); index at `https://react.dev/llms.txt`.

## Traps

- Derive values during render; do not mirror props or other state into `useState` and sync them with an effect.
- Logic caused by a user action goes in the event handler, not in an effect that watches state.
- An effect exists only to sync with something outside React (a subscription, a timer, the DOM); give it a cleanup.
- Data fetching uses the project's data layer, never a bare `useEffect` + `fetch` with no cancellation or error state.
- Never define a component inside another component; it remounts and loses state on every render.
- List keys are stable ids from the data, never the array index for lists that reorder, filter, or insert.
- `{count && <X />}` renders `0`; use a boolean or a ternary.
- Updates based on the previous value use the function form (`setItems(prev => ...)`).
- Expensive initial state uses the lazy form (`useState(() => build())`).
- Hydration: nothing in render may differ between server and browser (`Date.now()`, `Math.random()`, `window`, locale formatting); move it into an effect or render it on the client only.
- Compiler on: do not add `useMemo`, `useCallback`, or `memo` by hand.
  Compiler off: add them only where a measured re-render or a referential dependency needs them.
- React 19: `ref` is a normal prop (no new `forwardRef`), forms can use actions with `useActionState` and `useOptimistic`; match what the codebase already uses before introducing them.
- Components with many boolean props that switch behavior: split into explicit variants or compound components instead of adding another boolean.
- Shared state used by siblings lives in a provider or the nearest common parent, not duplicated in each child.

## Deeper, only when the task is in that area

- Performance: Vercel's rules at `https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/react-best-practices/rules/<rule>.md` (prefixes `async-`, `bundle-`, `rerender-`, `rendering-`; index in the skill's `SKILL.md`, one folder up from `rules/`).
- Component API design: `https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/composition-patterns/SKILL.md`.
