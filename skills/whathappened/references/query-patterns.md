# X query patterns for /whathappened

Use with `x_keyword_search` (and time filters where supported). Combine sparingly;
over-constrained queries return empty.

## Core operators

| Operator | Use |
|----------|-----|
| `"exact phrase"` | Product names, multi-word events |
| `OR` | Aliases (must be uppercase OR) |
| `from:user` | First-party posts |
| `to:user` / `@user` | Replies and mentions about someone |
| `since:YYYY-MM-DD` | Lower bound for adaptive window |
| `until:YYYY-MM-DD` | Upper bound if needed |
| `filter:replies` / `-filter:replies` | Include or cut pure reply noise |
| `filter:quote` | Quote-tweet debate surface |
| `filter:has_engagement` | Drop zero-engagement spam when Latest is noisy |
| `min_faves:N` / `min_replies:N` / `min_retweets:N` | Raise signal floor on busy topics |
| `-is:retweet` if supported in host query dialect | Prefer originals when available |

If an operator errors or returns nothing, simplify rather than invent syntax.

## Lane recipes

### Pulse (Latest, short window)

```text
"{Primary Entity}" OR {Alias} since:{today}
```

Mode: `Latest`. Keep limit modest (5–10).

### Top consensus

```text
"{Primary Entity}" OR {Alias}
```

Mode: `Top`. Same entity terms as pulse for comparability.

### First-party

```text
from:{official} ("{Entity}" OR launched OR shipping OR announce OR releasing)
```

If the account only posts about itself, bare `from:{official}` in-window is fine.

### About a person (not only their tweets)

```text
("{Person Name}" OR @{handle}) -from:{handle}
```

Plus a separate `from:{handle}` lane so first-party is not drowned out.

### Debate / backlash surface

```text
("{Entity}") (scam OR overhyped OR "not that" OR mid OR disappointing OR cope OR "actually good" OR "game changer")
```

Or:

```text
"{Entity}" (filter:quote OR filter:replies) min_faves:5
```

Tune controversy lexicon to the domain (tech vs politics vs sports). Do not force
hostile keywords onto calm topics.

### Semantic lane

`x_semantic_search` query should be natural language:

```text
what people think about {Entity} after {event}
```

```text
reactions and debates about {Entity}
```

Use `from_date` / `to_date` when the tool supports them to match the committed window.

## Adaptive `since:` guidance

- **Breaking:** `since:` today (and mentally filter to last hours when reading timestamps)
- **Same-day:** today and yesterday
- **Story:** ~last 7 days
- **Background:** up to ~30 days; still sort attention to newest coherent cluster

When Latest is flooded with bots, raise `min_faves` or switch emphasis to Top + threads.

## Entity hygiene

- Always keep the primary entity token in keyword queries.
- Add 1–3 aliases max (official name, short name, codename).
- For collisions (common words, shared surnames), prefer `"Exact Product"` and
  `from:official` rather than bare tokens.
- Drop results that only share a token and discuss something else.

## Thread selection

Prefer fetching threads for posts that are:

1. Announcement / origin
2. Official clarification
3. Highest engagement in-window summary
4. Clearest camp A and camp B posts
5. Corrective posts that change the narrative ("actually the weights drop on…")

Avoid spending the whole thread budget on near-duplicate dunks.
