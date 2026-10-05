---
name: next
description: Advance a ticket by exactly one stage of the agent pipeline (design, test plan, implementation, review, QA verification, ready to merge) according to its board Status, stopping at every owner gate. Usage - /next <ticket number>
argument-hint: "<ticket number>"
disable-model-invocation: true
---

# /next: run the next pipeline stage for a ticket

You are the **process manager** in the main session. Ticket: `$ARGUMENTS` (a GitHub issue number). If empty, run the
`/status` logic and ask which ticket to advance. Chat in **Russian**, artifacts in **English**. Read `CLAUDE.md` and
`docs/agent-team/process/agent-workflow.md` before you start.

## Always first

1. Read the issue and **all comments** (`gh issue view N --comments`) and its board Status
   (`gh project item-list 1 --owner arsbatyrov --format json`).
2. Only one ticket is in progress at a time. If another ticket is in `In progress`, `In review` or `QA`, tell the owner and ask.
3. Check the entry criteria in the table below. If they are not met, say what is missing and stop.

## Stage table (advance **one** stage per call, then stop)

| Current Status | You do | Next Status | Owner gate |
|---|---|---|---|
| `Ready` | Run subagent `architect` (design, ADR if needed). Post its `## Architect` comment. Set Status `Design`. Summarise the design in Russian. | `Design` | **Gate 2**: ask the owner to confirm the design/ADR. On "yes", post `Owner confirmed design`, set `Test plan`. On "changes", rerun the architect with the feedback. |
| `Test plan` | Run subagent `qa-engineer` in **Stage A** (test strategy and who writes what). Post `## QA` test plan. | `Test plan` | **Gate 3**: owner confirms the test plan. On "yes", post `Owner confirmed test plan`, set `In progress`. |
| `In progress` | Run subagent `developer` (branch, unit tests first, code, PR). Post `## Developer`. | `In review` | none; the Reviewer is next. |
| `In review` | Run subagent `reviewer` on the PR. Post `## Reviewer`. | `QA` if Approve; back to `In progress` if Changes requested | If Changes requested: rerun the developer with the findings (max 3 review loops, then ask the owner). |
| `QA` | Run subagent `qa-engineer` in **Stage B** (write and run API/contract/e2e/smoke tests, exploratory pass, file bugs per `bug-triage.md`). Post `## QA`. | `Ready to merge` if pass; back to `In progress` if blocking bugs | Bugs: apply the `/triage` rules. Blocking bugs go to the developer. |
| `Ready to merge` | Verify that all required CI checks on the PR are green and all review findings are resolved. Tell the owner **"ready to merge"** with the PR link, a short summary, test results and open non-blocking bugs. | `Done` | **Gate 4**: wait for the owner's explicit "yes" in this session. Only then run `gh pr merge N --merge --delete-branch`, move the ticket to `Done`. If "no", ask what to change. |

Statuses `Idea`, `Analysis` belong to `/idea`. `Blocked`: ask the owner what unblocks it.

## How to run a subagent

Use the Agent tool with the matching `subagent_type` (`architect`, `qa-engineer`, `developer`, `reviewer`). Give it: the ticket
number, the Status, a pointer to read the issue and its comments, the relevant PR or branch, and any owner feedback. The subagent
returns a report; **you** post the handoff comment on the ticket (format in `process/agent-workflow.md`) and move the Status.
If a subagent returns open questions, relay them to the owner with `AskUserQuestion` before continuing.

## Reporting to the owner (Russian)

After every stage: what was done, the result in two or three lines, what you verified (commands and results, never claims),
the new Status, and the single next step.

## Rules

- Never skip a gate; never merge without the explicit "yes" at Gate 4; never mark a ticket Done by yourself.
- If a subagent reports a blocker, a failing check or unclear criteria, stop and ask the owner.
- If tests fail or CI is red, do not move forward; send the work back to the responsible role.
- Do not edit code yourself in this skill; delegate to the roles.
