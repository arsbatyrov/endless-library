---
name: status
description: Show where tickets are in the agent pipeline, who acts next, open bugs and PR check status. Usage - /status [ticket number]. Read-only.
argument-hint: "[ticket number]"
disable-model-invocation: true
---

# /status: where is everything

Read-only. Chat in **Russian**. Ticket: `$ARGUMENTS` (optional; without it show all tickets that are not `Done`).

## What to read

- Board items and Status: `gh project item-list 1 --owner arsbatyrov --format json`.
- For each shown ticket: `gh issue view N --comments` (last comment per role), linked PR and its checks
  (`gh pr view`, `gh pr checks`), open bugs linked to the ticket (`gh issue list --label bug --search "#N"`).

## What to show

A compact table per ticket:

| Ticket | Status | Last action (role, when) | Who acts next | Waiting for the owner? | Open bugs (severity) | PR and checks |
|---|---|---|---|---|---|---|

Then, for a single ticket, add: the acceptance-criteria count, which are verified by tests, and the exact next command
(for example `/next 52`) or the question awaiting the owner.

## Rules

- Do not change anything: no comments, no status moves, no labels.
- If data is missing or contradictory (for example Status says `QA` but there is no PR), say so instead of guessing.
