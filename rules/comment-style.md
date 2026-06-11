# Comment & Review Style

Applies to GitHub PR review comments, issue comments, and issue bodies posted via `gh` / the GraphQL reviews API. Used by `/review`, `/pr-pipeline`, and the `@code-reviewer` agent.

## Format: theme first, details collapsed

Every posted comment leads with a **1-3 sentence high-level point or theme**. All supporting detail (file:line evidence, code snippets, mechanism walk-throughs, multi-step plans, tradeoff tables) goes inside a collapsible `<details>` block.

```markdown
<one to three sentences stating the point, recommendation, or conclusion>

<details>
<summary>Details</summary>

<supporting evidence: file:line refs, snippets, reasoning, plans>

</details>
```

### Rules
- The top line(s) must stand alone: a reader who never expands the details should still get the verdict and the recommended action.
- Lead with the conclusion, not the investigation. "Switching to new message types — optional fields don't help here" beats three paragraphs that arrive at that.
- One `<summary>` label that names what's inside (e.g. "Evidence", "Mechanism", "Rollout plan"), not a generic "Details" when something more specific fits.
- Don't split one point across multiple collapsibles; one theme = one comment = one details block.
- If a comment has no supporting detail worth hiding (a one-liner nit), skip the collapsible entirely — don't manufacture filler.
- Code review findings still follow `rules/claims-vs-hypotheses.md`: verify before posting. This rule governs *formatting*, not whether a finding is sound.

### Why
Reviewers skim. A wall of prose buries the actionable point and makes threads hard to scan. Theme-first lets a reader triage in one line and drill in only when they need the evidence.
