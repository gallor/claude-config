# CI calibration tags — the hidden `kaa-*` HTML tags

Emitted **only in CI mode** (`/review --ci`) so the calibration + analytics loops can audit reviews. Interactive `/review` never emits these. Referenced from SKILL.md step 7 (calibration-metadata).

**All tags are single-line JSON in an HTML comment.** Each wraps one JSON object so a reader parses any tag with a single extraction idiom: `grep -oP '(?<=<!-- kaa-{name}: ).*(?= -->)' | jq`. Emit compact JSON (`jq -c` shape) on one line — no pretty-printing, no newlines (they'd break the `-->` terminator). The one exception is legacy `kaa-lesson` (a bare int in old writes); see the registry note.

## Registry — every `kaa-*` tag

This is the complete set. "Consumed by" names **every** tool that parses the tag today — the calibrators (`/calibrate-review`, `/calibrate-lessons`) and/or the local analytics read-model (`fetch.py` → `events.jsonl` → dashboard/`classify_reviews.py`); the two are independent consumers, so a tag can feed one and not the other (e.g. `kaa-coverage` feeds `/calibrate-review` but is not yet in the read-model). A tag marked *(none)* is collected-but-unread by any tool (emitted now so the data accrues; wiring a reader is a later change — never the reverse).

| Tag | Scope (per-) | Emitter | Consumed by |
|-----|--------------|---------|-------------|
| `kaa-aspects` | review body | `/review` | `/calibrate-review`, dashboard |
| `kaa-agent` (+ `kpop`) | inline comment | `/review` | `/calibrate-review`, dashboard |
| `kaa-coverage` | review body | `/review` | `/calibrate-review` (Signal C) — *not the `events.jsonl` analytics read-model yet* |
| `kaa-timing` | review body | `/review` (every round) | `fetch.py` → `events.jsonl`, dashboard, `classify_reviews.py` |
| `kaa-loaded` | review body | `/review` | *(none yet — human-auditable only)* |
| `kaa-gate` | review body | `/review` (completeness gate) | *(none yet — `/calibrate-categories` reads gate state in-run, not via this tag)* |
| `kaa-reviewing` | review body (ephemeral banner) | review-bot workflow | *(none — removed at review end)* |
| `kaa-lesson` (+ `prs`/`superseded_by`) | CLAUDE.md entry | `/lessons-learned` | `/calibrate-lessons` |

The three tags `/calibrate-review` extracts are `kaa-aspects`, `kaa-agent`, `kaa-coverage`; the rest feed the local analytics (`kaa-timing`) or are diagnostics awaiting a consumer. `kaa-lesson` is documented in the `/lessons-learned` skill (Provenance section), not here — it rides on CLAUDE.md entries, not review bodies.

---

## The `/calibrate-review` tags (aspects, agent, coverage)

1. **`kaa-aspects` (review body footer)** — aspects spawned for the whole review; lets `/calibrate-review` tell a trigger gap from an agent-instruction gap:
```
<!-- kaa-aspects: {"aspects":["code","tests","compat"]} -->
```
Aspect names actually spawned (`code`, `tests`, `compat`, `perf`, `security`, `docs`, `simplify`, `rust`). Trivial-diff mode (no agents): `{"aspects":["code-inline"]}`.

2. **`kaa-agent` (per-inline-comment)** — appended to every inline comment, naming the agent(s) that produced it; a synthesized finding lists all contributors:
```
<!-- kaa-agent: {"agents":["code-reviewer"]} -->
<!-- kaa-agent: {"agents":["code-reviewer","migration-specialist"]} -->
```
Always append to every inline comment including suggestions. Hidden in the GitHub UI. This resolves a comment to its **agent** — the useful granularity. There is no rule-level ID (the agent prompts are reasoning guidelines, not an enumerated rulebook); `/calibrate-review` opens the named agent's prompt and narrows to the relevant **section header** by reading the finding against the prompt's sections. Agent → section is the achievable path; agent → rule-ID is not, by design.

3. **`kaa-coverage` (review body footer)** — records the *negative* results of **search-based checks** so a miss is auditable. A search-based check searches a space where finding nothing is a load-bearing claim (external-consumer, new-required-parameter callers, cross-repo). Diff-local checks (silent-failure, strict-access) are NOT traced — the diff is fully in view, there's no search space to miss.
```
<!-- kaa-coverage: {"sha":"abc1234","external-consumer":{"dumps":0,"get_explicit_packer":2},"new-required-param-callers":{"process":0}} -->
```
- `sha` = the PR head SHA reviewed (`github.event.pull_request.head.sha`) — the temporal anchor `/calibrate-review` uses to distinguish "was 0 at review time, consumer added later" (kaa right) from "was 0 at review time, consumer already existed" (kaa missed it).
- Per-symbol counts (not an aggregate) — a miss is per-symbol.
- Only include checks that actually ran. A skipped check (aspect not spawned, symbol filtered as internal) is omitted — absence means "not checked," distinct from a `0` meaning "checked, found nothing." Emit no `kaa-coverage` tag at all if no search-based check ran.

**Inline-kpop provenance rides `kaa-agent` (a `kpop` key), not a new tag.** When the inline-kpop cycle actually fired for a finding — a medium-confidence bug suspicion run down before posting, *or* a citation verified from the needle (the two callers of the 5-tool budget in `agent-prompts.md`) — add a `kpop` object to that finding's existing `kaa-agent` tag. **The signal originates in the agent, not here:** the investigating agent reports `{trigger, tools_used, outcome}` with its finding (per the "Report the kpop cycle when you ran one" rule in `agent-prompts.md`); this step's job is to *fold that report into* the finding's `kaa-agent` tag when assembling it. If an agent ran a repro/trace to confirm a finding but you have no report, the tag is silently lost — the #247 failure mode (kaa reproduced two `[critical]`s against real SQLAlchemy but emitted plain `kaa-agent` tags with no `kpop` key). Do not fabricate a `kpop` for a finding no agent reported investigating. It's the same per-inline-comment provenance surface and the same JSON, so no new extraction idiom or consumer field-family is needed. This is the **only** way the cycle is observable: a suspicion kpop *confirms* upgrades to a plain `[issue]`/`[critical]` shaped identically to a direct read, so without the marker its frequency/cost/hit-rate is invisible in the read-model by construction.
```
<!-- kaa-agent: {"agents":["code-reviewer"],"kpop":{"trigger":"bug-suspicion","tools_used":3,"outcome":"resolved"}} -->
<!-- kaa-agent: {"agents":["code-reviewer"],"kpop":{"trigger":"citation","tools_used":1,"outcome":"disproved"}} -->
```
- `trigger` — which caller armed it: `bug-suspicion` (the Medium-confidence gate) or `citation` (cite-don't-adopt needle check).
- `tools_used` — tool calls the cycle spent (1–5); answers "does the 5-cap ever bind?" without a separate budget metric.
- `outcome` — `resolved` (verified within budget: a bug suspicion confirmed, or a cited claim confirmed against the needle → posted at earned severity) | `escalated` (hit the cap → posted `[question]` + `/kpop` handoff) | `disproved` (citation-only: needle contradicted the claim → one-shot finding).
- Add the `kpop` key only when the cycle fired; a plain `{"agents":[...]}` (no `kpop`) = direct finding, no investigation. Most findings are the plain form — the cycle is rare by design.
- **Known gap — `dropped` (investigated, found nothing → suppressed) has no comment to tag**, so a fire that produces no finding can't ride `kaa-agent`. It is left unmeasured for now rather than adding a body-footer aggregate tag: the resolved/escalated/disproved fires are observable via `kaa-agent.kpop`; the missing `dropped` denominator only matters once the observable fires are non-zero (they are ~0 today). Revisit with a `dropped` count only if the tag shows the cycle actually firing at volume.

---

## Diagnostic tags (analytics + self-reporting, not `/calibrate-review` inputs)

These four also emit in CI. They feed the local analytics read-model (`kaa-timing`) or are self-reporting diagnostics awaiting a consumer. Same single-line-JSON contract.

4. **`kaa-timing` (review body footer)** — per-phase elapsed in seconds, measured on a **monotonic** clock (not wall-clock timestamps — no tz/skew, and phases sum). Emitted on **every** review, first pass and every re-review, so follow-up-round durations and round-churn cost are in the corpus (first-pass-only would bias it). Consumed by `fetch.py` into `events.jsonl` and the dashboard.
```
<!-- kaa-timing: {"review_index": 1, "gather_s": 11, "aspects_s": 198, "aspects_n": 8, "gate_s": 94, "post_s": 18, "total_s": 321} -->
```
- `review_index` — 1-based ordinal of this review among kaa's reviews on the PR (`(prior srv-chippy reviews)+1`); a re-review is `2`, `3`, … so re-runs are distinguishable from first passes.
- `gather_s` / `aspects_s` / `gate_s` / `post_s` — elapsed in each phase (context-gather, aspect fan-out, completeness gate, posting); `total_s` — whole run.
- `aspects_n` — number of aspect agents spawned (`0` on a trivial-diff or bare re-verify pass, where `aspects_s` is absent).
- **Reconcile with `kaa-gate`:** `gate_s` is the same measurement `kaa-gate`'s `work_min` reports, in seconds — one source, two views (seconds here, minutes there). Do not measure the gate twice.

5. **`kaa-loaded` (review body footer)** — which `skills/review/*.md` supplements the run actually read; lives in the **core** (always loaded) so a skipped supplement is self-reporting (failing to read one cannot also suppress the evidence of the failure).
```
<!-- kaa-loaded: {"supplements":["agent-prompts.md","cpp-agent-instructions.md","ci-calibration-tags.md"]} -->
```
- List only what was read: `agent-prompts.md` always; `rust-agent-instructions.md` only with `.rs`; `cpp-agent-instructions.md` only with `.cpp`/`.hpp`/`.h`; `compat-agent-instructions.md` only when the `compat` aspect fired; `directed-review.md` whenever the completeness gate ran; `ci-calibration-tags.md` always in CI.
- If a supplement that *should* have loaded is absent on a posted review, the pointer-follow broke. **Human-auditable only** — no tool parses it yet; do not describe it as automatically enforced.

6. **`kaa-gate` (review body footer)** — the completeness (directed-review) gate's own result: did it run, and if so what did it cost/yield.
```
<!-- kaa-gate: {"ran": false} -->
<!-- kaa-gate: {"ran": true, "refs_followed": 2, "findings_added": 0, "work_min": 2} -->
```
- `ran` — whether the gate fired at all (a broad-but-no-references PR arms nothing → `{"ran": false}`, costs ~0).
- `refs_followed` / `findings_added` / `work_min` — references chased, findings the gate added, and its elapsed minutes. Keep "armed-but-returned-clean" (`ran:true, findings_added:0`) distinct from "never-armed" (`ran:false`) — that distinction is `/calibrate-categories`'s signal. `/calibrate-categories` reads gate *state* during its own run, not this tag; the tag is the durable record.
- `refs_unreachable` / `refs_offallowlist` (optional, omit when empty) — the two `refs_*` list buckets for references kaa *wanted* but didn't read: `refs_unreachable` = tried, couldn't reach (`[{target,reason}]`, the `/blob/`-resolver signal); `refs_offallowlist` = allowlist forbade the attempt (`[{url,host}]`, the evidence-driven allowlist-candidate feed). Full semantics + the framing-not-domain gate live in `directed-review.md` (single source — do not restate the rules here, just register the keys).

7. **`kaa-reviewing` (ephemeral start banner)** — posted by the review-bot workflow when a review *starts* (so a long review shows progress), then **removed** by the workflow's "Remove reviewing banner" step once the real review posts. It does **not** persist in final review bodies, so no analytics consumes it — it exists only for in-flight UX. Documented here for completeness; do not treat its absence from a finished review as a gap.
