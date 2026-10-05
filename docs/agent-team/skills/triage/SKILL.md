---
name: triage
description: Apply the bug triage policy to a bug - propose severity and priority with reasoning, decide whether it blocks the pull request, and after the owner agrees set the labels and the ticket state. Usage - /triage <bug issue number>
argument-hint: "<bug issue number>"
disable-model-invocation: true
---

# /triage: severity, priority and blocking decision for a bug

You are the **process manager** in the main session. Bug issue: `$ARGUMENTS`. Chat in **Russian**; labels and comments **English**.
Read `docs/agent-team/process/bug-triage.md` before you start; it is the policy.

## Steps

1. Read the bug (`gh issue view N --comments`), the linked ticket and PR, the failing test or reproduction steps.
2. **Validate the report**: reproduction steps, expected vs actual, environment, requirement ID, evidence. If the report is
   incomplete, ask the reporter role (usually QA) to complete it, or list what is missing.
3. **Check duplicates** (`gh issue list --label bug --search`). If it duplicates one, link and close nothing without the owner.
4. **Propose** with reasoning from the policy: severity (`sev:critical|major|minor|trivial`), priority (`P1|P2|P3`),
   area, and **whether it blocks the PR** (policy table).
5. **Ask the owner** (`AskUserQuestion`) to confirm when: severity is `critical`, the priority is `P1`, the decision is
   ambiguous, or you propose "won't fix". Otherwise apply the policy defaults and tell the owner what you applied.
6. After agreement set labels (`gh issue edit N --add-label ...`), add the bug to the board, link it to the ticket, and:
   - **blocking**: the ticket goes back to `In progress` for the developer with the bug linked; post a comment with the decision;
   - **non-blocking**: leave it in the backlog with the priority; note it in the "ready to merge" message.
7. Report (Russian): the decision, its reasoning in two or three lines, and what happens next.

## Rules

- Never lower a severity to unblock a PR. Severity describes impact, not convenience.
- Security issues and data loss are always `critical` and `P1`.
- Do not fix the bug yourself and do not close it; the developer fixes it, QA verifies and closes after a regression test exists.
