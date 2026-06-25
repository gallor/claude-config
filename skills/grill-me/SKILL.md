---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
user-invocable: true
argument-hint: <topic or plan description>
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase or reading documentation (CLAUDE.md, README, design docs, existing skill/agent files), do that first and present the finding as context rather than asking the user. Only ask the user when the answer requires a decision or preference that can't be derived from existing material.
