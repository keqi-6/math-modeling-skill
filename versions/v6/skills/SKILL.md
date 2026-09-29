---
name: math-modeling-project-controller
description: Govern, recover, build, audit, revise, verify, and finish mathematical-modeling competition projects. Use for project takeover, continuation, problem interpretation, data work, method selection, coding, verification, manuscript work, scientific figures, engineering drawings, tables, LaTeX, handoff, final delivery, or Skill migration. Integrates V1's complete detailed workflow with one state machine, explicit permissions and decisions, mechanically verified recovery evidence, progressive loading, and behavioral regressions.
---

# Mathematical Modeling Project Controller V6

## 1. Execute this controller first

For every substantive request:

1. Determine the project root and the user's authorized scope.
2. Classify each affected question or deliverable by the state machine below.
3. Create and mechanically validate the start receipt before mutation.
4. Execute only actions permitted by the current state.
5. Read the routed quality rules completely before performing those actions.
6. Verify affected outputs, propagate changes, and create the end receipt.

This file is the sole authority for stage order, action permission, human approval, rollback, and
completion status. Files in `rules/` define how to perform permitted work well and how to test its
minimum acceptance criteria; they cannot grant permission or close a state. Files `01`–`17` preserve
detailed V1/V2 procedures, files `18`–`20` preserve V3 execution gates, files `21`–`29` preserve V3
stable-ID quality criteria, files `30`–`35` preserve V4's concise cross-checks, file `36` owns V6
uncertainty/error analysis, and file `37` owns V6 scientific-figure and engineering-drawing design. Where a detailed
procedure and an acceptance file overlap, execute the detailed procedure and satisfy the acceptance
file; neither may weaken the other. Files in `references/` preserve migration evidence and
provenance; they are not active gates.

Resolve all Skill resources from the directory containing this `SKILL.md`, never from the current
working directory or the package folder name. In integrated detailed modules, legacy `skills/`
paths are compatibility aliases:

- `skills/SKILL.md` means `<skill-root>/SKILL.md`;
- `skills/scripts/<name>` means `<skill-root>/scripts/<name>`;
- `skills/NN-<name>.md` means `<skill-root>/rules/NN-<name>.md`.

Run `scripts/validate_internal_paths.py` during Skill maintenance. A literal compatibility alias is
acceptable only when it resolves by these rules; newly written controller text must use
`<skill-root>` or a direct package-relative path.

## 2. Single state machine

Track every independently answerable question, scenario, shared data layer, and delivery layer
separately. Store these component records as the authority; derive the project summary mechanically
from the earliest open required component. A single hand-written `current_stage` is not authoritative.

| State | Purpose | Minimum exit evidence |
|---|---|---|
| `S0_RECOVER` | Establish actual inherited state | full-read inventory, duplicate map, authority conflicts, earliest unsupported layer |
| `S1_INTERPRET` | Fix task meaning and deliverables | task card, quantities, constraints, ambiguities, approved material interpretation |
| `S2_ASSESS` | Establish evidence capacity and real gaps | data interface, provenance, literature trigger, simple baseline, supported/unsupported claims |
| `S3_DECIDE` | Decide whether and how to change the method | necessity assessment, sufficiency comparison including no change, explicit human decision |
| `S4_SPECIFY` | Freeze the approved mathematical contract | variables, assumptions, objectives, constraints, parameters, outputs, acceptance tests, intended-use uncertainty plan |
| `S5_IMPLEMENT` | Implement and solve the frozen specification | aligned code, structured frozen outputs, run identity |
| `S6_VERIFY` | Test correctness, uncertainty, robustness, meaning, and boundaries | independent recomputation, risk-matched error/uncertainty evidence, sensitivity or robustness where triggered, human review and freeze |
| `S7_PUBLISH` | Build evaluator-visible delivery | traceable manuscript, compiled PDF, page inspection, compliance and explicit promotion |

The project-wide state is a summary only. It cannot be later than the earliest open state of any
required component.

## 3. Action permissions

| State | Allowed | Prohibited |
|---|---|---|
| `S0` | enumerate, hash, read, extract, render, inspect, compare | accept old status, mutate project evidence, claim current-state completeness |
| `S1` | restate, map tasks, expose ambiguity, request interpretation decision | select a formal method, code, solve |
| `S2` | audit data, search when triggered, build simple baseline, identify gaps | recommend one formal method as decided, change production artifacts |
| `S3` | assess necessity, compare sufficiency and candidates, run isolated reversible probes, request decision | formal specification, production code, frozen conclusions, authoritative prose |
| `S4` | write the approved mathematical specification and acceptance tests | change approved modeled reality, implement against a moving specification |
| `S5` | code, solve, freeze outputs, create manifests | promote results to final claims before independent verification |
| `S6` | independently recompute, stress test, explain, review, freeze | conceal a failure by weakening prose, publish unapproved claims |
| `S7` | draft, revise, compile, inspect, package and synchronize | introduce a new method, parameter policy, result, or claim beyond frozen evidence |

An action is permitted only when all are true:

```text
action_allowed =
  action is allowed in current state
  AND required exit evidence from earlier states exists
  AND required human decision is explicit and compatible
  AND the user's request authorizes the action
```

When false, stop before the action, report the missing condition, and continue any safe work still
permitted in the current state.

## 4. Recovery and full-read gate

Choose the least recovery level that proves continuity:

- `R0_INCREMENTAL_CHECKPOINT`: same uninterrupted session, a current checkpoint identity, and an
  explicit changed-path set. Inspect the changed paths and their consumers; the full-read gate is
  `not_triggered`.
- `R1_HASH_DELTA_RECOVERY`: a new window or context recovery with a recent verified baseline
  manifest. Verify the baseline hash, inventory the live project, fully inspect every added or
  changed canonical item, and verify unchanged items by hash. The gate closes only when the delta
  and all affected consumers are resolved.
- `R2_FULL_RECOVERY`: unknown provenance, missing or stale baseline, explicit full audit, milestone
  closure, or final closure. Enter `S0_RECOVER` and execute the full-read contract below.

The words “continue”, “pause”, or “finish for today” do not by themselves force R2. Choose R2 only
when its evidence trigger exists. Until the selected recovery level closes, only its permitted
read/checkpoint-evidence actions are allowed.

- Treat handoffs, state files, READMEs, plans, logs, prior audits, and summaries as navigation
  hypotheses.
- Enumerate the entire project.
- Read every unique text, code, and configuration file completely.
- Inspect every Office sheet, PDF page, image, structured dataset, and relevant binary using its
  native representation.
- Prove duplicates by content hash before reading one canonical copy.
- Classify archives, mirrors, caches, locks, build intermediates, and unknown files.
- Reconstruct the chain from original inputs through current delivery.

Do not mutate project artifacts or claim whole-project status before this gate closes. Report
unreadable or unresolved material explicitly.

### Recovery evidence contract

The gate has only three legal values: `not_triggered`, `in_progress`, and `closed`. No custom
phrase, inherited claim, prior audit, or summary may stand for `closed`.

For every R2 trigger, create a current `recovery_manifest.json` outside the recovered project
or in a pre-existing audit location whose use does not alter project evidence. Generate its inventory
with `scripts/recovery_manifest.py inventory`, then record inspection evidence for every canonical
item. The manifest must contain:

- project root and inventory timestamp;
- every current file's relative path, byte size, SHA-256, representation class, and duplicate group;
- one canonical item for each duplicate group;
- for text/code/configuration: exact line count, contiguous read ranges covering line 1 through EOF,
  and `truncated: false`;
- for PDF, Office, image, structured data, archive, cache, lock, build, binary, and unknown items:
  the representation-specific inspection method, inspected units, completion state, and findings;
- unresolved items and inventory/inspection counts.

Run `scripts/recovery_manifest.py verify` against the live project and the completed manifest.
`full_read_gate: closed` is legal only when that verifier passes, the receipt identifies the manifest
path and SHA-256, all current files are represented, every canonical item is complete, duplicate
hashes agree, no read range is missing or marked truncated, and `unresolved` is empty.

The manifest proves inventory and recorded coverage, not private cognition. Therefore closure still
requires the executing agent to perform the inspections during the current recovery. A manifest
copied from an earlier run is invalid when its inventory identity, timestamp, or content hash does
not match.

While `S0_RECOVER` is open, the only write allowed by this Skill is creation or completion of the
temporary/external recovery receipt and manifest. Project evidence, project rules, handoffs, plans,
code, outputs, paper, and delivery mirrors remain read-only. If no external or already-designated
audit location is writable, keep evidence in the tool session and do not mutate the project merely
to document why mutation is prohibited.

## 5. Decision gate

Use one decision package for every material interpretation, data treatment, model, parameter policy,
objective priority, evaluation criterion, claim scope, or formal promotion:

```yaml
decision:
  id:
  type: interpretation | data_treatment | model | parameter | objective | criterion | claim | promotion
  component:
  current_approach:
  observed_gap:
  evidence_for_gap:
  necessity:
    status: not_assessed | unnecessary | necessary | disputed
    consequence_if_unchanged:
  options:
    - id: keep_current
      assumptions:
      outputs:
      verification:
      risks:
      downstream_cost:
    - id: minimal_change
    - id: major_change
  recommendation:
  user_decision: not_requested | awaiting | approved | rejected
  approved_scope:
  prohibited_scope:
  implementation_allowed: false
```

For a method change, `options` must include the genuine `keep_current` alternative. Add other
options only when they are materially distinct; do not invent models to fill a quota.

Set `implementation_allowed: true` only when:

```text
necessity.status is necessary
AND keep_current was evaluated
AND credible alternatives were compared
AND the user explicitly approved one option
AND approved_scope covers the intended action
```

Understanding a method does not approve it. Approval of a method does not approve parameters,
implementation, claims, manuscript wording, or formal promotion unless `approved_scope` says so.
Silence, “继续”, “可以”, successful execution, official examples, literature convention, existing
code, and prior AI recommendations are not approval.

### External-guidance boundary

Official rubrics, examples, excellent papers, and literature may reveal required questions, review
risks, or candidate methods. They do not select a model automatically. For any method-like external
statement, distinguish:

1. the substantive question it expects answered;
2. the method it merely suggests or exemplifies;
3. whether the current approach already answers that question;
4. whether project data identify the suggested method;
5. the consequence of not adopting it.

Return to `S3_DECIDE` before any resulting method change.

## 6. Rollback and propagation

Repair the earliest unsupported layer:

`statement → interpretation → data/evidence → decision → specification → implementation → frozen
output → verification → manuscript → rendered delivery`

Rollback mapping:

| Change or defect | Return to |
|---|---|
| task meaning, official requirement, material interpretation | `S1` |
| raw data identity, preprocessing, provenance, evidence capacity | `S2` |
| model family, objective, criterion, claim scope | `S3` |
| variables, formulas, constraints, parameters, acceptance tests | `S4` |
| code or solver implementation with unchanged specification | `S5` |
| result, verification, robustness, explanation | `S6` |
| expression, figure placement, typesetting, packaging only | `S7` |

List direct and transitive consumers. Mark them regenerated, still valid with evidence, provisional,
or invalid. Downstream artifacts cannot prove a skipped upstream state.

## 7. Receipts

Start every substantive task with:

```yaml
receipt_kind: start
task:
scope:
components:
state_before:
earliest_open_state:
required_inputs:
routed_rules:
allowed_actions:
prohibited_actions:
full_read_gate: not_triggered | in_progress | closed
recovery_level: R0_INCREMENTAL_CHECKPOINT | R1_HASH_DELTA_RECOVERY | R2_FULL_RECOVERY
recovery_evidence:
  manifest_path:
  manifest_sha256:
  inventory_file_count:
  canonical_item_count:
  completed_canonical_count:
  unresolved_count:
decisions_required:
implementation_allowed:
substantive_analysis: true | false
artifact_plan:
  - content:
    disposition: provisional | current_authority | frozen_evidence | external_recovery_evidence | no_project_artifact
    path:
    promotion_requires:
    reason:
```

`substantive_analysis` is true whenever the turn forms a task card, concept audit, data treatment,
candidate comparison, interpretation, specification, verification conclusion, claim boundary, or
other content that can affect later project work. Such content must have at least one planned
project or external-evidence artifact; it may not use `no_project_artifact` as its only disposition.
Before approval, write it to the project's provisional analysis area and mark it non-authoritative;
do not confuse “not approved for promotion” with “must remain only in chat.” A genuinely transient
or read-only turn may use `no_project_artifact`, but must give a concrete reason.

End with a distinct `receipt_kind: end` contract:

```yaml
outputs:
verification:
state_closures:
decisions:
affected_downstream:
unresolved:
completion_scope: local | state | milestone | full_project
status: complete | partial | blocked
artifact_disposition:
  - content:
    disposition:
    path:
    realized: true | false
    authority_status: provisional | approved | frozen | external_only | not_applicable
    evidence:
```

The receipt validator must dispatch by `receipt_kind`; it must never validate an end receipt against
the start fields. Maintain separate start/end schemas or an equivalent discriminated union.

Skill maintenance is never implied by project work or daily closure. Without an explicit `skill_change` approval,
record only a candidate issue or patch outside the active Skill. After
approval, modify only the approved Skill scope and run the relevant structural, migration,
behavioral, and forward tests.

Every skipped conditional rule needs its trigger, checked evidence, and concrete non-trigger reason.
A receipt records evidence; it never substitutes for it. Before ending, map every substantive item
produced in chat or analysis to its planned artifact and authority status. A `complete` end receipt
cannot leave a planned provisional, authority, frozen, or external-evidence artifact unrealized.

Validate a JSON form of the receipt with `scripts/validate_receipt.py`. When recovery is triggered,
the validator must also receive `--project-root` and verify the referenced manifest. A receipt that
omits recovery evidence, invents another gate value, reports inconsistent counts, contains unresolved
items, or points to stale evidence fails. Validator success is necessary but does not itself prove
that the recorded human/agent inspection was honestly performed.

## 8. Detailed-rule routing

V6 owns its detailed rules directly under `rules/`; it does not route back to another Skill version.
Read every file listed for the current trigger completely:

| Trigger | Required V6 detailed rules |
|---|---|
| every substantive task | `rules/18-execution-receipt.md` |
| takeover or recovery | select R0/R1/R2 first, then read `rules/00-project-orchestration.md`, `rules/01-contest-project-pattern.md`, `rules/14-session-handoff.md`, `rules/15-pipeline-methodology.md`, `rules/19-project-lifecycle.md` to the extent required by that level |
| project structure, initialization, code/output conventions | `rules/01-contest-project-pattern.md`; use `scripts/bootstrap_project.py` only after controller authorization |
| data audit or preprocessing | `rules/16-data-audit-methodology.md`, `rules/24-assumptions-data-acceptance.md`, `rules/30-data-minimum.md` |
| model assessment, algorithm comparison, specification, solving | `rules/07-algorithm-reference.md`, `rules/15-pipeline-methodology.md`, `rules/25-model-results-acceptance.md`, `rules/31-modeling-minimum.md`, `rules/36-uncertainty-error-analysis.md` when result credibility may depend on uncertain inputs, numerical approximation, non-exact solving, or model form |
| literature or external-evidence work | `rules/08-literature-search.md`, `rules/12-source-audit-and-provenance.md`, `rules/26-conclusion-references-acceptance.md`, `rules/28-evidence-acceptance.md` |
| verification, robustness, artifact or manuscript audit | `rules/05-audit-protocol.md`, `rules/09-robustness-checker.md`, `rules/25-model-results-acceptance.md`, `rules/32-verification-minimum.md`, `rules/36-uncertainty-error-analysis.md` |
| structured outputs or machine lineage | `rules/10-json-handoff.md` |
| manuscript drafting, revision, or content audit | `rules/03-paper-content-rules.md`, `rules/06-weiwei-norms.md`, `rules/13-excellent-paper-expression.md`, `rules/17-reader-first-manuscript-audit.md`, `rules/20-execution-gates.md`, `rules/21-global-manuscript-acceptance.md`, `rules/22-front-matter-acceptance.md`, `rules/23-background-analysis-acceptance.md`, `rules/24-assumptions-data-acceptance.md`, `rules/25-model-results-acceptance.md`, `rules/26-conclusion-references-acceptance.md`, `rules/33-manuscript-minimum.md`, `rules/36-uncertainty-error-analysis.md` when a result's credibility or boundary depends on its evidence |
| figures or tables | `rules/04-figure-generator.md`, `rules/27-visual-layout-acceptance.md`, `rules/34-visuals-minimum.md`, `rules/37-scientific-figure-design.md`; use `scripts/validate_figure_assets.py` for mechanical asset checks after controller authorization |
| LaTeX, fonts, compilation, PDF, pagination | `rules/02-latex-setup.md`, `rules/27-visual-layout-acceptance.md`, `rules/34-visuals-minimum.md` |
| formal assembly, submission, or packaging | `rules/11-paper-finalizer.md`, `rules/12-source-audit-and-provenance.md`, `rules/28-evidence-acceptance.md`, `rules/29-governance-acceptance.md`, `rules/35-provenance-delivery-minimum.md` |
| handoff or checkpoint | `rules/14-session-handoff.md`, `rules/29-governance-acceptance.md`, `rules/35-provenance-delivery-minimum.md`; use `scripts/session_checkpoint.py` only after controller authorization |
| milestone or final closure | every Markdown file in `rules/` |
| Skill maintenance or V1–V6 coverage claim | every file in `rules/`, `references/v1-integration-map.json`, `references/version-delta-map.json`, `references/migration-ledger.md`, `agents/openai.yaml`, `scripts/validate_skill.py`, `scripts/test_regressions.py`, and all other validators |

### Every manuscript mutation round

Treat each new user instruction that authorizes a manuscript change as a new manuscript mutation
round, including a follow-up that expands, corrects, rolls back, or propagates an earlier edit. Before
the first write in that round to any manuscript or manuscript-draft source, figure, table,
bibliography, compiled PDF, or evaluator-visible mirror, read every rule listed in the `manuscript
drafting, revision, or content audit` row completely from line 1 through EOF. Record a current-round
ID, current hashes, exact line counts, contiguous read ranges, and `truncated: false` in the start
receipt or its linked audit evidence. A previous round's or previous window's read, recovery
manifest, navigation summary, search hit, or the fact that only one sentence appears to need editing
cannot satisfy this gate. Do not use progressive routing to bypass this reread for a later manuscript
mutation in the same window.

In every mutation round, read every rule listed in the `manuscript drafting, revision, or content audit` row completely before writing.

For any edit that propagates wording or structure across two or more first-level sections, create a
pre-mutation propagation matrix with `source claim`, `target section`, `section duty`, `permitted
information density`, `prohibited detail`, and `planned evidence`. Preserve an exact changed-path
baseline or patch identity before writing. After editing, run a chapter-duty regression against the
matrix and record every target as `retained`, `reverted`, or `revised`; compilation and receipt-schema
validation cannot substitute for this semantic check.

The detailed modules preserve V1's full project knowledge and V2's reader-first gate. The exact
acceptance modules preserve V3's stable-ID criteria and V4's concise cross-checks without relying on
semantic-compression claims, while this controller adds the V4–V6 component state, approval,
recovery-evidence, and regression protections. Resolve conflicts in this order:
official/current user requirements and mathematical truth; this controller's permission and state
rules; the detailed rule. A detailed rule may strengthen quality within an allowed action but cannot
grant permission, close a state, or override a newer verified safety repair.

Run `scripts/validate_v1_migration.py` during Skill maintenance and before claiming V1 coverage.
The validator must prove that all 17 V1 authorities and both tools are integrated in V6's active
paths, match their source hashes, and are routed here. A future semantic compression needs an atomic
mapping and failure regression before replacing any exact integrated module.
Run `scripts/validate_version_deltas.py --history-root <history-root>` before claiming V1–V6
coverage. Every V2–V4 delta must have a source hash, active owner, treatment, route, and reason;
rejected stale paths and superseded compressed rules remain explicit ledger entries.
The validator must also prove every V3 stable-ID quality file and every V4 quality file has an exact,
routed active owner. Run `scripts/test_version_deltas.py` so missing, altered, unrouted, downgraded,
or falsely semantic-only integrations fail before any coverage claim.

## 9. Completion

Claim only the scope actually checked. A successful script, compile, local edit, or selected-file
audit is not a state, milestone, or whole-project pass.

Formal delivery requires:

- every required component at `S7`;
- current frozen evidence and independent verification;
- evaluator-visible evidence chains;
- compiled and visually inspected pages;
- official compliance checks;
- explicit human promotion.
