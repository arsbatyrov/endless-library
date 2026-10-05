# Activation and deactivation

The kit is **inactive** while it lives in `docs/agent-team/`. Activating means copying files to the places where
Claude Code loads them. Every step needs the owner's approval; nothing here is done automatically.

## Before you activate: readiness checklist

- [ ] The owner has reviewed and accepted [process/bug-triage.md](process/bug-triage.md) (bug priority rules: Critical, High, Mid, Low).
- [ ] The owner has reviewed the role prompts in [agents/](agents) and the skills in [skills/](skills).
- [ ] The first feature to try (the **pilot**) is chosen: small, described in words by the owner, NOT the authentication epic.
- [ ] The owner accepts the cost: every role is a separate model run, so one ticket through the full pipeline uses noticeably
      more of the usage limit than a normal session.
- [ ] Nothing important is mid-flight (open PRs are merged or parked), so the pilot starts from a clean `main`.

## Activation steps

1. **Create a branch** `chore/activate-agent-team` from an up-to-date `main`.
2. **Copy the files** (PowerShell, from the repository root):

   ```powershell
   New-Item -ItemType Directory -Force .claude | Out-Null
   Copy-Item -Recurse -Force docs\agent-team\agents .claude\agents
   Copy-Item -Recurse -Force docs\agent-team\skills .claude\skills
   Copy-Item docs\agent-team\CLAUDE.md.draft CLAUDE.md
   ```

3. **Extend the project-board Status options** (project "Endless Library", field Status) to:
   `Idea, Analysis, Ready, Design, Test plan, In progress, In review, QA, Ready to merge, Done, Blocked`.
   (Board settings are an external change: the owner approves it; it can be done in the web UI or with the GraphQL
   `updateProjectV2Field` mutation, the same way the current options were set.)
4. **Check the bug labels**: `bug` and the four priority labels `priority:critical`, `priority:high`, `priority:mid`,
   `priority:low` exist (created together with the bug issue template, `.github/ISSUE_TEMPLATE/bug.yml`).
5. **Review the merge permissions.** In the ticket workflow the orchestrator merges only after the owner's explicit "yes".
   The personal file `.claude/settings.local.json` (git-excluded) may keep `gh pr *` allowed; the skills themselves
   enforce the approval. If the owner wants a hard stop, move `gh pr merge *` from `allow` to `ask` (the owner approves the
   change to their own permission file).
6. **Commit and open a PR** with the copied files; merge after the required checks pass.
7. **Update the project memory**: the agent team is active since <date>, the pilot ticket, and any rule changes.
8. **Restart the Claude Code session** so that agents, skills and `CLAUDE.md` are picked up.
9. **Run the pilot**: `/idea <describe a small feature in your own words>`. Keep notes on what felt slow, wrong or costly.

## Deactivation (switch the team off)

```powershell
Remove-Item -Recurse -Force .claude\agents, .claude\skills
Remove-Item CLAUDE.md
```

Then commit the removal. The kit in `docs/agent-team/` stays as the source of truth, so the team can be re-activated
later. Board Status options can stay as they are.

## After the pilot (iteration 2)

- Record lessons learned in [process/agent-workflow.md](process/agent-workflow.md).
- Decide whether to add the enforcement hook (a `PreToolUse` hook that denies a role writes outside its scope).
- Decide whether to add autonomous runs in GitHub Actions (`anthropics/claude-code-action`, triggered by the owner only).

## Rollback if something misbehaves during the pilot

Stop the session, run the deactivation commands above, and review what the agents changed with `git status` and
`git diff`; nothing is merged without the owner's approval, so the worst case is a branch you delete.
