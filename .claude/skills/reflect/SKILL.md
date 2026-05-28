---
name: reflect
description: Review this conversation for wasted steps and update CLAUDE.md User preferences. Use when user types /reflect or asks to "retrospect", "optimise my workflow", or "update preferences from this session".
argument-hint: [optional: focus area e.g. "planning", "debugging", "agents"]
allowed-tools: Read, Edit, Glob, Grep
---

# Reflect — Conversation Self-Optimisation

Scan the current conversation for inefficiency patterns, derive preference rules, and append approved rules to the `### User preferences` section of `.claude/CLAUDE.md`.

## Arguments

Optional focus area passed by the user: $ARGUMENTS

If a focus area is provided (e.g. "planning", "agents", "debugging"), limit the scan to patterns in that domain. Otherwise scan the whole conversation.

---

## Step 1 — Read the existing rules

Read `.claude/CLAUDE.md` and extract every bullet from these five sections:
- `### User preferences`
- `### Speed & focus`
- `### Debugging approach`
- `### Diagnostic shortcuts`
- `### Past failures`

Keep this list in working memory. Any candidate rule that is already covered (same *behaviour*, even different wording) must be discarded in Step 3.

---

## Step 2 — Scan the conversation for inefficiency signals

Go through every turn in the current conversation. Flag turns that match any of these patterns:

| Signal | What to look for |
|--------|-----------------|
| **Unnecessary agent** | An Explore or Plan agent was spawned for a file/function that was already mentioned or obviously known |
| **Over-reading** | Files were read that turned out to be irrelevant to the final fix |
| **Late clarification** | A clarifying question was asked *after* multiple tool calls — the question could have been first |
| **Repeated work** | The same file was read twice, or the same approach was tried and reverted |
| **Misdiagnosis chain** | A multi-turn detour caused by diagnosing the wrong root cause before asking what the actual symptom was |
| **Plan mode overkill** | Plan mode was entered for a change that was obviously a 1–5 line fix |
| **Broad search when targeted** | `Grep`/`Glob` was run across the whole repo when the relevant file was already known |

For each flagged turn, note:
- The turn number or summary of what happened
- Which signal it matches
- What the faster path would have been

---

## Step 3 — Derive candidate rules

For each flagged signal, write a candidate preference rule in the project's existing format:

```
- **<Short imperative title>** — <one sentence: when this applies and why it's faster>
```

Optionally append a parenthetical with a concrete example from this session:
```
- **<Title>** — <sentence>  (e.g. this session: <brief example>)
```

**Discard** any candidate whose *behaviour* is already covered by an existing rule from Step 1.

If no new candidates remain after deduplication, output:

> ✅ No new patterns found — existing rules already cover this session's workflow.

Then stop.

---

## Step 4 — Present candidates to the user

Output a preview block showing exactly how the rules will appear in CLAUDE.md:

```
### Proposed additions to `### User preferences`

- **<Rule 1 title>** — <rule 1 body>
- **<Rule 2 title>** — <rule 2 body>
...

Reply with the numbers to keep (e.g. "1 3"), "all", or "none".
```

Wait for the user's selection before proceeding.

---

## Step 5 — Apply approved rules

For each approved rule, append it to the `### User preferences` section of `.claude/CLAUDE.md`.

Use the Edit tool with this exact `old_string` anchor (the last bullet already in the section):

```
- **Ask clarifying questions early in plan mode** — before settling on an approach, use `AskUserQuestion` to confirm the actual goal. One question upfront saves multiple fix-and-revert cycles.
```

Replace it with itself **plus** the new bullet(s) appended immediately after, one per line:

```
- **Ask clarifying questions early in plan mode** — before settling on an approach, use `AskUserQuestion` to confirm the actual goal. One question upfront saves multiple fix-and-revert cycles.
- **<New rule>** — <body>
```

If `### User preferences` has already been extended beyond the original bullet (i.e. a previous `/reflect` run already added rules), anchor on the **last bullet currently in that section** instead — grep for the section header and identify the final bullet before the next `###` heading.

After editing, confirm to the user:

> ✅ Added X rule(s) to `### User preferences` in `.claude/CLAUDE.md`.
