# Contributing

Thanks for helping improve Hephaestus Skills.
Issues and pull requests are welcome at [github.com/quocld/hephaestus-agent-skills](https://github.com/quocld/hephaestus-agent-skills).
By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Bugs and small fixes: open a pull request directly, or an issue first if you are not sure it is a bug.
- A new skill, a new hook, or a change to `AGENTS.md`: open an issue first, so we agree on where the rule belongs before you write it.
- Security problems: do not open a public issue; use a [private security advisory](https://github.com/quocld/hephaestus-agent-skills/security/advisories/new).

## Making a change

1. Fork the repo and branch from `main`.
2. For a skill, follow `skills/knowledge-placement` first: it says where a rule belongs and how to write a skill that agents actually follow.
   A new skill needs `name` and `description` frontmatter and a place in `skills/harness-map/assets/lifecycle.json`.
3. Keep the house style: plain `-` instead of an em dash, one sentence per line in Markdown, and no co-author lines for AI agents in commits.
4. Write commit subjects as [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:`, `refactor:`, ...).
   Releases are cut by hand (`.claude/skills/release`) and pick the version from these types: `feat` is a minor bump, a `!` after the type or a `BREAKING CHANGE:` footer is major, anything else is a patch.

## Checks

Run what CI runs (`.github/workflows/checks.yml`) before you open the pull request:

```bash
python3 .github/scripts/check_skill_refs.py
bash hooks/test.sh
bash skills/feature-status/scripts/test_status.sh
python3 skills/harness-map/scripts/test_harness_map.py
python3 skills/project-init/scripts/test_doctor.py
```

A test only counts if it fails without your change; say in the pull request how you proved that.

## Pull requests

- One topic per pull request, into `main`.
- Describe why, what changed, and how you verified it (the commands above and their results).
- By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
