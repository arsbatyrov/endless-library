# Agent team kit (NOT ACTIVE)

**Status: prepared, stored, not in use.** Nothing in this folder is loaded by Claude Code. The files are plain
documentation until someone follows [activation.md](activation.md).

## What this is

A ready-made set of role definitions and process documents for building Endless Library with separate agents instead of
one generalist session:

| Role | Responsibility |
|---|---|
| **Analyst** | Interviews the product owner, extracts acceptance criteria, creates tickets after the owner confirms |
| **Architect** | Designs the solution, writes ADRs, may create technical tickets |
| **QA / SDET** | Proposes the test strategy (which test on which pyramid level, who writes it), writes and runs API and e2e tests, files bugs with a priority (Critical, High, Mid, Low) |
| **Developer** | Implements the ticket and its unit tests until they are green |
| **Reviewer** | Independently reviews the Developer's code |
| **Process manager (orchestrator)** | Runs the pipeline in the main Claude Code session (skills `/idea`, `/next`, `/status`, `/triage`), moves ticket statuses, asks the owner at every gate, merges only after the owner's explicit approval |

Roles communicate **only through the ticket** (description, structured comments, labels) and its **status** on the
project board.

## The pipeline in one picture

```
Idea -> Analysis -> Ready -> Design -> Test plan -> In progress -> In review -> QA -> Ready to merge -> Done
  owner    analyst    owner   architect   QA +        developer      reviewer     QA      owner says     orchestrator
  speaks   interviews confirms designs    owner       codes + unit                runs    "merge"        merges
                                          confirms    tests                       API/e2e
```

Owner gates (nothing moves on without an explicit yes): acceptance criteria, design/ADR, test strategy, and the final merge.

## Contents

| File | Purpose |
|---|---|
| [activation.md](activation.md) | How to switch the team on and off, step by step |
| [CLAUDE.md.draft](CLAUDE.md.draft) | Shared project context for every agent (becomes the root `CLAUDE.md`) |
| [agents/](agents) | The five role definitions (become `.claude/agents/`) |
| [skills/](skills) | The orchestrator commands `/idea`, `/next`, `/status`, `/triage` (become `.claude/skills/`) |
| [process/agent-workflow.md](process/agent-workflow.md) | Statuses, handoffs, comment formats, gates, escalation |
| [process/bug-triage.md](process/bug-triage.md) | Bug priority policy: Critical, High, Mid, Low (draft for owner review) |
| [adr/0000-template.md](adr/0000-template.md) | Architecture decision record template |

## Why it is stored here and not in `.claude/`

Claude Code loads `.claude/agents/`, `.claude/skills/` and the root `CLAUDE.md` automatically, and it may delegate work
to a subagent based on its description. Putting the kit there would activate it immediately. Keeping it under `docs/`
keeps it inert and reviewable.

## Not included yet

- An enforcement hook that physically blocks a role from editing files outside its scope (planned for after the pilot).
- Autonomous runs in GitHub Actions (`@claude` in tickets). Planned only after a successful pilot.
