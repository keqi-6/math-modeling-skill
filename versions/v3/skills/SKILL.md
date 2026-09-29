---
name: math-modeling-project-bootstrap
description: Build, recover, audit, revise, and finish end-to-end mathematical-modeling competition projects. Use for project takeover, full-file recovery, problem and data interpretation, literature-backed model selection, per-question formulation and coding, verification, robustness, manuscript drafting or revision, figures, LaTeX, handoff, and final submission. Enforces non-skippable evidence, human-decision, per-question stage, execution-receipt, and reader-first manuscript gates.
---

# Mathematical Modeling Project Bootstrap V3

## Execute the kernel first

For every substantive request:

1. Classify the task using the routing matrix below.
2. Read every listed active rule completely before acting.
3. Create the start receipt defined in `rules/01-execution-receipt.md`.
4. Identify the earliest incomplete or invalidated stage.
5. Perform only actions allowed by that stage and the user's request.
6. Verify affected outputs and create the end receipt before claiming completion.

Do not use `references/rule-sources/` as an active-rule substitute. It preserves provenance and
details for migration or exceptional investigation. Active obligations live in this file and
`rules/`.

## Non-negotiable kernel

### K-01 Evidence over summaries

Treat handoffs, READMEs, plans, logs, prior audits and chat summaries as navigation hypotheses.
Establish facts from original inputs, current code, frozen outputs, verification, manuscript and
rendered deliverables.

### K-02 Full-read gates

At new-project activation, inherited-project recovery, context-loss recovery, milestone closure,
final-paper closure, or explicit full-project audit:

- enumerate the current project again;
- read every unique text, code and configuration file completely;
- inspect Office/PDF/image/structured/binary material using its native representation;
- prove duplicate equality by hash before reading one canonical copy;
- classify caches, locks, archives, mirrors and unknown files;
- report unreadable or unresolved material instead of silently skipping it.

Do not claim current state, synchronization or whole-project completion before this gate closes.

### K-03 Earliest-invalid-layer

Use this evidence chain:

`statement → interpretation → data → evidence/design → specification → implementation → frozen
output → independent verification → manuscript → rendered delivery`

Repair the earliest unsupported layer and invalidate all affected downstream artifacts. Do not fix
model or implementation defects only by changing prose.

### K-04 Human decision and understanding

AI may inspect, calculate, compare, draft provisional alternatives and perform reversible work.
Before promoting an interpretation, material data treatment, model family, parameter policy,
objective priority, claim scope or evaluator-visible draft into project authority:

- explain the question, evidence, alternatives, trade-offs and recommendation in ordinary language;
- provide a minimal worked example when the user may not know the method;
- record what confirmation approves and does not approve;
- require explicit user confirmation. Silence, “继续”, existing code or an AI draft is not approval.

Previously approved decisions may be inherited only after compatibility is checked.

### K-05 No stage jumping

For each independently answerable question, subquestion or scenario, preserve these functions:

`task interpretation → data interface → literature trigger/orientation → evidence re-review →
simple baseline → candidate/sufficiency comparison → human method decision → mathematical
specification → implementation/solve → independent verification → robustness/explanation →
human review/freeze/manuscript mapping`

Simple tasks may close several functions in one interaction, but each needs separate closing
evidence. Existing downstream work cannot retroactively close a skipped upstream function.
Over-jump artifacts remain provisional and cannot become authority.

### K-06 No unproved skip

Every required rule is either executed or listed in the receipt with a concrete non-trigger reason.
“Not relevant”, “already handled”, “time is limited”, or absence of user objection is insufficient
without evidence.

### K-07 Evaluator-visible completeness

Technical correctness is not manuscript completeness. For every question, the evaluator-visible
paper must contain a findable chain:

`problem conflict → model choice and alternative → object mapping → assumptions/variables →
objective/constraints → solution logic → result → evidence/validation → direct answer →
applicability boundary`

Internal documents, code, logs and chat do not substitute for this chain.

## Mandatory routing matrix

Read `rules/00-execution-gates.md` and `rules/01-execution-receipt.md` for every substantive task.
Then read all files in the matching row.

| Task | MUST_READ active rules |
|---|---|
| takeover, “continue”, recovery, full audit | `05-project-lifecycle.md`, `40-evidence-provenance.md`, `50-governance-handoff.md` |
| statement interpretation, planning, task mapping | `05-project-lifecycle.md`, `40-evidence-provenance.md` |
| data audit or preprocessing | `05-project-lifecycle.md`, `40-evidence-provenance.md` |
| model choice, coding, solving, verification, robustness | `05-project-lifecycle.md`, `23-model-solution-results.md`, `40-evidence-provenance.md` |
| manuscript drafting, revision, comparison or audit | `10-global-manuscript-rules.md`, the applicable `20`–`24` section rules, `40-evidence-provenance.md` |
| figures, tables, LaTeX, PDF or pagination | `30-figures-tables-layout.md`, `40-evidence-provenance.md` |
| handoff, milestone, finalization or delivery | `05-project-lifecycle.md`, `10-global-manuscript-rules.md`, `20`–`24`, `30`, `40`, `50` |
| rule migration or skill maintenance | `rule-ownership-map.md`, `references/migration-ledger.md` |

When a row names a numeric range, read every file in that range completely. If the task spans rows,
take the union. State which skill rule caused any action or pause.

## Work protocol

### Start

- Write the start receipt before mutation.
- Resolve project root, task scope, authority sources and current stage.
- For recovery triggers, close K-02 before accepting prior status.
- Inspect current files before creating new structure.

### Execute

- Keep original evidence immutable.
- Freeze conclusion-producing results in structured outputs.
- Keep method, code, result and claim identities aligned.
- Use independent verification that does not merely reread the primary implementation's summary.
- Reopen K-04 when new evidence changes a material choice.
- Record change propagation from the earliest changed layer.

### Close

- Reinspect changed artifacts and their consumers.
- Compile or run proportionate checks.
- Inspect rendered evaluator-visible outputs when applicable.
- Complete the end receipt with outputs, checks, unresolved issues and downstream status.
- Never convert partial or local checks into a whole-project pass.

## Manuscript quality

Use the reader-first active rules as the canonical manuscript specification:

- `10`: global paragraph, terminology, causal-strength and continuous-reading rules;
- `20`: title, abstract and keywords;
- `21`: background, restatement and problem analysis;
- `22`: assumptions, symbols and data;
- `23`: per-question model, solve, result and direct-answer chain;
- `24`: evaluation, conclusion and references;
- `30`: figures, tables, LaTeX, PDF and layout;
- `40`: evidence, provenance and claim traceability.

Apply a light paragraph audit to ordinary transitions and descriptions. Apply the full paragraph
audit to the abstract, problem analysis, model choice, assumptions, key formulas, numeric
comparisons, causal claims, optimality/validity claims, robustness and conclusion.

Verified candidate work must be reconsidered for manuscript admission by information gain. Do not
leave it permanently excluded merely because it began in a candidate directory.

## Stop and report

Stop before the affected action when:

- an original input is unreadable or has uncertain provenance;
- task identity, statement and derived task map conflict;
- a missing interpretation would materially change the answer;
- required human approval is absent;
- a result cannot be reproduced or independent verification contradicts it;
- the manuscript exceeds what its evidence proves;
- the receipt cannot identify required inputs, skipped rules or closing evidence.

## Historical sources

Use `references/rule-sources/` only to investigate provenance, recover detail omitted during
migration, or adjudicate a suspected lost rule. Read the selected source completely. If it contains
an active independent obligation missing from `rules/`, record it in
`references/migration-ledger.md` and restore it to an active owner before claiming the skill
migration complete.
