---
name: push
description: Commit and push the current Anvero changes to GitHub, following the project's "before ending a session" checklist. Use when the user asks to push, commit and push, sync changes up, or wants to end a session.
---

Commit and push the current changes, following `CLAUDE.md`'s "Before ending
a session" rule: the docs must still describe reality before anything goes
up.

1. Run `git status` and `git diff` to see everything unstaged and staged.
   Run `git log -5 --oneline` to match this repo's commit message style.
2. Look at what actually changed and check whether it invalidates anything
   in `docs/AI_START_HERE.md`, `docs/AI_HANDOFF.md`, or
   `docs/PROJECT_STATUS.md` (e.g. "Not yet verified" items that got proven,
   new endpoints/tables not yet reflected, setup steps that changed). Update
   those files if reality moved; skip this only for genuinely trivial
   changes (typo fixes, formatting).
3. If backend or frontend test files changed, consider running
   `.\scripts\anvero.ps1 sync-tests` to refresh the test-count numbers in
   the docs above — then review its diff before committing, per
   `CLAUDE.md`.
4. If this is a real decision (architecture, contract change, trade-off),
   record it in `docs/DECISIONS.md`; if it's a milestone, add it to
   `CHANGELOG.md` per `docs/PROJECT_RULES.md`.
5. Stage specific files by name (never `git add -A` / `git add .`) and
   re-check `git status` after staging — flag anything that looks like a
   secret or credential before it's committed.
6. Draft a concise commit message focused on *why*, matching the repo's
   existing style. Show it to the user before committing if there's any
   ambiguity about scope; otherwise proceed.
7. Commit, ending the message with:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
   (name the model that actually did the work, if it is a different one)
8. Push. Never force-push. If the push is rejected (remote has new commits),
   stop and tell the user rather than force-pushing or auto-merging.
9. Confirm success with a one-line summary of what was pushed.

Use full paths / `cd` explicitly before each command rather than chaining
with `&&` — this is Windows PowerShell 5.1. Only commit what the user has
actually asked to commit — don't sweep up unrelated in-progress work.
