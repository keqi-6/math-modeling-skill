---
name: math-modeling-project-bootstrap
description: Build, audit, revise, verify, and finalize mathematical-modeling competition projects and papers. Use for project recovery, statement and data interpretation, model design, reproducible solving, manuscript writing, full-Skill auditing, reader-comprehension repair, LaTeX layout, evidence tracing, or submission preparation.
---

# Mathematical Modeling Project Bootstrap

## Authority

The concise manuscript rules in `rules/` are the daily authority for evaluator-visible writing and
paper auditing. Each concise rule has one owner listed in `rules/rule-ownership-map.md`.

The routed modules in `source-portfolios/` remain executable authorities only for non-manuscript
project recovery, engineering, data, literature, robustness, source governance, human decision
gates, submission and other responsibilities not owned by `rules/`. For evaluator-visible
manuscript writing, figures, tables, LaTeX and paper auditing, `rules/` is the sole everyday
execution authority. A source portfolio may expose an omitted manuscript rule, but that rule must
first be migrated to exactly one owner in `rules/`; do not execute it directly as a competing paper
authority. Read every selected source module completely before using it for migration or
non-manuscript work.

`source-portfolios/legacy-SKILL.md` preserves the pre-refactor orchestration contract. Use it for
migration-completeness audits and omitted-rule recovery, not as a second everyday entry point.

When a rule in `rules/` conflicts with an official requirement, current user decision or mathematical
truth, stop and resolve the conflict at its source. Do not decide by file count.

## Rule force and migration governance

Classify rules independently of their source:

| Class | Meaning | Execution |
|---|---|---|
| A | Official, mathematical, truthful or approved-governance hard rule | Must execute |
| B | Checkable general quality rule | Execute unless a documented exception applies |
| C | Conditional rule | Verify its trigger before execution |
| D | Heuristic or diagnostic | Consider; omission alone cannot fail an artifact |
| E | Unsafe, conflicting, overbroad or unverified item | Preserve for review; do not enforce |

Do not silently delete a rule during refactoring. A rewrite that preserves the full independent
meaning may proceed with a recorded mapping. Before a pure deletion, or a merge/move that would erase
an independent meaning or competing version, present the stable rule identity, prior wording,
classification, reason, retained coverage and consequence to the user. Keep unapproved deletions in
a visible pending register. Follow `source-portfolios/12-source-audit-and-provenance.md` for a
source or Skill migration audit.

## Mandatory project recovery and closure

At a new session, inherited workspace, context-loss recovery, user request to “continue”, milestone
closure or final-project closure:

1. Read `source-portfolios/14-session-handoff.md` and
   `source-portfolios/01-contest-project-pattern.md` completely.
2. Treat `HANDOFF.md`, `project_state.json`, README files, logs and chat summaries only as navigation
   hypotheses.
3. Inventory the entire project before making a current-state, completion, synchronization or
   next-action claim.
4. Read every unique active text, code and configuration file completely. Inspect every sheet, page,
   diagram, table and embedded object in office inputs; visually inspect evaluator-visible PDFs and
   images; inspect structured or binary data by schema, dimensions, ranges, producer and key
   invariants.
5. Hash identical mirrors and duplicates, read one canonical copy completely and prove equality.
   Inspect archives, caches, locks and build intermediates for role and freshness without treating
   them as independent evidence.
6. Reconstruct the state from original statements and attachments through planning, method, code,
   frozen outputs, independent verification and paper; only then compare it with handoff claims.

Do not modify project artifacts before this recovery gate closes. The fatal recovery anti-pattern is
to infer the project from handoff files, recent timestamps, existing code, selected outputs or the
current PDF and begin editing.

At milestone or final closure, repeat the inventory after changes, trace every change through its
consumers, compare mirrors by content and record intentional non-updates. A copy command, successful
compile or status-file edit is not synchronization proof.

## Mandatory manuscript start

For every manuscript writing, rewriting or audit task:

1. Read `rules/00-execution-gates.md` completely.
2. Read `rules/10-global-manuscript-rules.md` completely.
3. Read the applicable chapter-specific rule files completely.
4. Read `rules/40-evidence-provenance.md`.
5. If files, PDF layout, status or formal promotion may change, also read
   `rules/30-figures-tables-layout.md` and `rules/50-governance-handoff.md`.
6. Record the complete-reading evidence required by `00`.

A truncated tool result is not complete reading. Search output, summaries and old audit records do
not substitute for the selected rule files.

When manuscript work begins during a recovered or inherited session, both the project-recovery gate
and manuscript-reading gate apply. Completing one never substitutes for the other.

## Rule routing

| Work object | Required files after `00` and `10` |
|---|---|
| Title, abstract, keywords | `20-front-matter.md`, `40-evidence-provenance.md` |
| Problem background, restatement, analysis | `21-background-restatement-analysis.md`, `40-evidence-provenance.md` |
| Assumptions, symbols, data preprocessing | `22-assumptions-symbols-data.md`, `40-evidence-provenance.md` |
| Model building, solving, results, validation, direct answers | `23-model-solution-results.md`, `40-evidence-provenance.md` |
| Evaluation, improvement, conclusion, references | `24-evaluation-conclusion-references.md`, `40-evidence-provenance.md` |
| Figures, tables, fonts, LaTeX, pagination | `30-figures-tables-layout.md` |
| Draft/formal boundary, approval, state, handoff | `50-governance-handoff.md` |

For a whole-paper audit, read every file in `rules/` completely. Do not audit one chapter at a time
until the whole-paper structure gate passes.

## Non-negotiable manuscript workflow

`complete reading → structure gate → global paragraph rules → chapter rules → evidence tracing
→ plain-reader restatement → compile and inspect every affected page → human review`

Key consequences:

- Missing problem background is a structure failure.
- A term without nearby ordinary-language explanation is a paragraph failure.
- A number without an explanation of what it establishes and how it answers the task is a result
  failure.
- Correct code, formulas, verification counts and pagination do not repair unreadable prose.
- A structural or generalizable failure invalidates affected downstream pass states.
- Do not create or promote a formal manuscript until the user has manually audited and explicitly
  approved the draft.

## Project workflow

Maintain the evidence chain:

`official statement and inputs → task interpretation → data audit → baseline and candidate methods
→ human method decision → mathematical specification → implementation → independent verification
→ robustness and boundaries → draft manuscript → human audit → formal assembly`

Fix defects at the earliest faulty layer and regenerate all dependents. Do not weaken paper wording
to hide a model or implementation defect.

For each original question and independently deliverable subquestion or scenario, instantiate this
chain separately:

`task meaning and quantities → approved data interface → literature orientation when triggered →
simple baseline → candidate and sufficiency comparison → informed human method decision →
mathematical specification → implementation → independent verification → robustness and boundaries
→ human review and freeze → paper mapping`

Existing downstream code, figures, verification or prose cannot close a skipped upstream
interpretation, decision or specification gate. Use `source-portfolios/15-pipeline-methodology.md`
for stage execution and inherited-decision compatibility; use the applicable construction module for
the current work object.

## Human decision and comprehension gates

The user decides task meaning, assumptions, metrics, model family, material parameters, baselines,
claim scope and formal promotion. Before asking for a material decision, explain:

`question → smallest worked example → project data structure → method role → result meaning →
identifiable and non-identifiable claims → credible alternatives → decision consequence`

Persist this plain-language layer in the relevant planning or method document; chat alone is not a
project artifact. Close the understanding gate only after explicit confirmation. “Continue”,
“okay”, silence, existing code and an AI-authored draft do not confirm understanding or approve a
method. Understanding approval also does not approve parameters, implementation, manuscript wording
or final promotion.

Read `source-portfolios/15-pipeline-methodology.md` completely for a material method decision or
stage transition, and `source-portfolios/12-source-audit-and-provenance.md` completely for AI-use,
source, rule-migration or human-control questions.

## Authorization boundary

Match actions to the user's requested stage. For a request to inspect, review, audit, compare or
report, make only read-only observations and proposed changes. Modify project artifacts only when the
user asks to build, repair, revise, implement or otherwise authorizes changes. Even with revision
authority, return to the user before changing modeled reality, evaluation criteria, mathematical
specification, claim scope, official compliance interpretation or formal-delivery status.

## Source portfolios

Consult `source-portfolios/` when:

- provenance, rule classification or historical wording must be checked;
- the concise executable rule points to a detail not reproduced in `rules/`;
- a migration completeness audit compares new owners with legacy content;
- official submission, literature, algorithms, machine handoff or raw-data methodology requires
  the longer source treatment.

For non-manuscript work, the selected module is an executable authority and must be read completely:

| Responsibility | Detailed source portfolio |
|---|---|
| Project structure and pipeline | `01-contest-project-pattern.md`, `15-pipeline-methodology.md` |
| Session recovery, continuation and closure | `14-session-handoff.md`, `01-contest-project-pattern.md` |
| Algorithm-family reference | `07-algorithm-reference.md` |
| Literature search | `08-literature-search.md` |
| Robustness-test design | `09-robustness-checker.md` |
| Structured machine outputs | `10-json-handoff.md` |
| Submission assembly | `11-paper-finalizer.md` |
| Source and rule provenance | `12-source-audit-and-provenance.md` |
| Raw-data audit methodology | `16-data-audit-methodology.md` |

Resolve each filename relative to `source-portfolios/` and read the selected file completely.

For LaTeX, figures, tables and manuscript layout, execute `rules/30-figures-tables-layout.md`.
Consult `02-latex-setup.md` or `04-figure-generator.md` only during a migration-completeness or
historical-provenance audit; migrate any still-useful independent requirement into `rules/30`
before applying it.

When a useful legacy manuscript rule is missing from the concise layout, migrate it to exactly one
owner in `rules/`, update `rule-ownership-map.md`, validate the Skill and add a regression check.
When a missing rule belongs to a routed non-manuscript responsibility, restore it to that
`source-portfolios/` owner or promote only its unavoidable orchestration gate into this entry file.
Record the old-to-new mapping and do not restore competing everyday authorities.
