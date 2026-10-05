---
name: triage
description: Apply the bug triage policy to a bug - check the report, confirm or propose its priority (Critical, High, Mid, Low) with reasoning, decide whether it blocks the pull request, and after the owner agrees set the labels and the ticket state. Usage - /triage <bug issue number>
argument-hint: "<bug issue number>"
disable-model-invocation: true
---

# /triage: priority and blocking decision for a bug

You are the **process manager** in the main session. Bug issue: `$ARGUMENTS`. Chat in **Russian**; labels and comments **English**.
Read `docs/agent-team/process/bug-triage.md` before you start; it is the policy. Bugs have **one** rating, **Priority**
(Critical, High, Mid, Low), normally set by the tester in the bug form.

## Steps

1. Read the bug (`gh issue view N --comments`), the linked ticket and PR, the failing test or reproduction steps.
2. **Validate the report** against the bug form: reproduction steps, expected vs actual, environment, requirement ID,
   evidence, "how found" and "regression". If something is missing, ask the reporter role (usually QA) to complete it, or
   list what is missing.
3. **Check duplicates** (`gh issue list --label bug --search`). If it duplicates one, link it; do not close anything without the owner.
4. **Check the tester's priority** against the policy table. Confirm it, or propose a different one with reasoning. Decide
   **whether the bug blocks the PR** (policy table).
5. **Ask the owner** (`AskUserQuestion`) to confirm when: the priority is `Critical`, you disagree with the tester, the
   decision is ambiguous, or "won't fix" is proposed. Otherwise apply the policy and tell the owner what you applied.
6. After agreement set labels (`gh issue edit N --add-label priority:<level>,area:<area>`, remove `needs-triage`), add the bug
   to the board, link it to the ticket, and:
   - **blocking**: the ticket goes back to `In progress` for the developer with the bug linked; post a comment with the decision;
   - **non-blocking**: leave it in the backlog with its priority; mention it in the "ready to merge" message.
7. Report (Russian): the decision, its reasoning in two or three lines, and what happens next.

## Rules

- Never lower a priority to unblock a PR. Priority describes impact and urgency, not convenience.
- Security issues and data loss are always `Critical`.
- Do not fix the bug yourself and do not close it; the developer fixes it, QA verifies and closes after a regression test exists.
