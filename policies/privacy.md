# Privacy policy

This policy covers the documentation site at hephaestus-skills-docs.vercel.app and the Hephaestus Skills plugin.
Last change: see the [history of this file](https://github.com/quocld/hephaestus-agent-skills/commits/main/policies/privacy.md).

## The docs site

- It is a static site: no accounts, no forms, no comments, no analytics, no advertising, and no tracking cookies.
- Hosting: [Vercel](https://vercel.com) serves the site and, like any web host, processes request data such as your IP address and browser user agent to deliver pages and protect the service. See the [Vercel privacy policy](https://vercel.com/legal/privacy-policy).
- Fonts: pages load fonts from [Google Fonts](https://fonts.google.com), so your browser sends a request, including your IP address, to Google. See the [Google privacy policy](https://policies.google.com/privacy).
- The About page shows the maintainer's avatar, which your browser loads from GitHub. See the [GitHub privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).
- Search: the site is registered with Google Search Console, which reports aggregated search statistics (queries, clicks) to the maintainer. It adds no tracking to the pages.
- Your theme choice (light, dark, auto) is kept in your browser's local storage and never leaves your device.

## The plugin

- The skills, hooks and scripts run on your machine, inside your coding agent.
- They send no telemetry and have no server of their own.
- `harness-map` reads your local setup to draw its report, writes that report to a local file, and never prints a secret value.
- Some skills call services you connect yourself (GitHub, Jira, Vercel, Better Stack and others), with your own credentials; those services' own policies apply.

## Contact

Questions about this policy: open an [issue](https://github.com/quocld/hephaestus-agent-skills/issues) or contact the maintainer, [Ryan Le (@quocld)](https://github.com/quocld).
