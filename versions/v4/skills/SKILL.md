---
name: math-modeling-project-controller
description: Govern, recover, build, audit, revise, verify, and finish mathematical-modeling competition projects. Use for project takeover, continuation, problem interpretation, data work, method selection, coding, verification, manuscript work, figures, LaTeX, handoff, or final delivery. Enforces one project state machine, action permissions, explicit human decisions, evidence tracing, and evaluator-visible quality gates.
---

# Mathematical Modeling Project Controller V4

## 1. Execute this controller first

For every substantive request:

1. Determine the project root and the user's authorized scope.
2. Classify each affected question or deliverable by the state machine below.
3. Create the start receipt before mutation.
4. Execute only actions permitted by the current state.
5. Read the routed quality rules completely before performing those actions.
6. Verify affected outputs, propagate changes, and create the end receipt.

This file is the sole authority for stage order, action permission, human approval, rollback, and
completion status. Files in `rules/` define how to perform permitted work well; they cannot grant
permission or close a state. Files in `references/` preserve detailed knowledge and provenance; they
are not active gates.

## 2. Single state machine

Track every independently answerable question, scenario, shared data layer, and delivery layer
separately.

| State | Purpose | Minimum exit evidence |
|---|---|---|
| `S0_RECOVER` | Establish actual inherited state | full-read inventory, duplicate map, authority conflicts, earliest unsupported layer |
| `S1_INTERPRET` | Fix task meaning and deliverables | task card, quantities, constraints, ambiguities, approved material interpretation |
| `S2_ASSESS` | Establish evidence capacity and real gaps | data interface, provenance, literature trigger, simple baseline, supported/unsupported claims |
| `S3_DECIDE` | Decide whether and how to change the method | necessity assessment, sufficiency comparison including no change, explicit human decision |
| `S4_SPECIFY` | Freeze the approved mathematical contract | variables, assumptions, objectives, constraints, parameters, outputs, acceptance tests |
| `S5_IMPLEMENT` | Implement and solve the frozen specification | aligned code, structured frozen outputs, run identity |
| `S6_VERIFY` | Test correctness, robustness, meaning, and boundaries | independent recomputation, risk-matched tests, human review and freeze |
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

Enter `S0_RECOVER` for a new or inherited project, “continue/take over” request, context-loss
recovery, explicit full audit, milestone closure, or final closure.

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
decisions_required:
implementation_allowed:
```

End with:

```yaml
outputs:
verification:
state_closures:
decisions:
affected_downstream:
unresolved:
completion_scope: local | state | milestone | full_project
status: complete | partial | blocked
```

Every skipped conditional rule needs its trigger, checked evidence, and concrete non-trigger reason.
A receipt records evidence; it never substitutes for it.

## 8. Quality-rule routing

Always read `rules/provenance-delivery.md`. Then read the smallest applicable set completely:

| Work | Required quality rules |
|---|---|
| data, preprocessing, statistical unit | `rules/data.md` |
| method assessment, specification, solving | `rules/modeling.md` |
| verification, sensitivity, robustness | `rules/verification.md` |
| manuscript content, revision, audit | `rules/manuscript.md` |
| figures, tables, LaTeX, PDF, pagination | `rules/visuals-layout.md` |
| milestone, handoff, formal delivery | all applicable rules |
| skill maintenance | `references/migration-ledger.md`, then run all skill validators |

If a detailed legacy obligation appears absent, consult the mapped source in
`references/migration-ledger.md`. Restore it to exactly one quality owner or this controller; never
create a competing active authority.

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

