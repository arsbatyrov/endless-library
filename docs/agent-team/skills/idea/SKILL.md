---
name: idea
description: Start a new feature. The analyst role interviews the owner about an idea described in words, extracts Given/When/Then acceptance criteria, and after the owner confirms creates the ticket(s). Usage - /idea <what you want to build>
argument-hint: "<describe the feature in your own words>"
disable-model-invocation: true
---

# /idea: from an idea to a confirmed ticket

You are the **process manager** in the main session. The owner has described a feature in their own words:

> $ARGUMENTS

If `$ARGUMENTS` is empty, ask the owner what they want to build, then continue. Chat with the owner in **Russian**;
tickets and documents are **English**. Read `CLAUDE.md` and `docs/agent-team/process/agent-workflow.md` first.

## Step 1: understand and restate

Restate the idea in one sentence (Russian) and check the repository for related existing behaviour and tickets
(`gh issue list --search`, `Grep` the code). If the idea overlaps an existing ticket, say so and ask whether to extend it.

## Step 2: interview (this must happen in the main session)

Subagents cannot ask the owner questions, so you run the interview yourself, acting as the analyst:

- Ask focused questions with `AskUserQuestion`, at most four per round, each with sensible options and a recommended default.
- Cover: who uses it (which role) and why; the trigger and the main flow; business rules and limits; validation and error
  cases; empty states; permissions; both interface languages; data and persistence; what is explicitly **out of scope**;
  the platforms (api, web, android); and how the owner will recognise that it works.
- Stop when you could write a Given/When/Then criterion for every flow. Usually 2-3 rounds. Do not ask what the code or
  existing docs already answer.

## Step 3: draft the ticket

Delegate drafting to the `analyst` subagent (Agent tool, `subagent_type: analyst`). Pass: the owner's words, all answers,
related tickets, and the requirement ID prefix you suggest. Ask it to return the draft in the structure of
`.github/ISSUE_TEMPLATE/feature.yml`, the Definition of Ready table and open questions. If open questions remain, go back to
Step 2 for those only.

## Step 4: owner confirmation (gate 1)

Show the owner a short Russian summary of the criteria plus the full English draft. Ask with `AskUserQuestion`:
**Confirm and create the ticket**, **Change something**, or **Cancel**. Do not create anything before an explicit confirmation.

## Step 5: create

After explicit confirmation, have the analyst (or yourself) create the issue(s) with `gh issue create`: English title
`[REQ-ID] short title`, body in the template structure, labels `feature`, `area:*`, a priority label (`P1`-`P3`, ask the owner
if unclear), add to the project board "Endless Library" with Status `Ready`. If the work was split, create the parent first and
list the children in it.

## Step 6: report and stop

Report (Russian): ticket numbers and links, the criteria in short, and the next step: `/next <number>` starts the design.
Do **not** start the design automatically.

## Rules

- No ticket, label, board change or comment before the owner's explicit confirmation in Step 4.
- Never invent requirements: unknown means ask, or record it as an open question with a proposed default.
- Keep the owner's language for the interview, English for artifacts.
