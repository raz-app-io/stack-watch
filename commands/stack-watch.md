---
description: Run stack-watch on a repo. Bootstrap builds STACK.md; probe checks vendor changelogs and advisories for changes that affect the stack.
argument-hint: "[bootstrap|probe] [repo-path]"
---

Run the stack-watch skill now, following its SKILL.md exactly.

Arguments: `$ARGUMENTS`

- First word `bootstrap`: run bootstrap mode even if `STACK.md` already exists (rebuild it; the hand-confirmed section is preserved).
- First word `probe`, or no mode word: normal mode selection (bootstrap when there is no `STACK.md`, probe otherwise).
- Any remaining argument is the repo path. Default is the current working directory.

Stop where the skill says to stop: after presenting STACK.md on a bootstrap run, and after printing the proposal table on a probe run. Never create tickets until the user has replied with item numbers.
